#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""
Freeze the manifest version policy as a truth table.

The schema's `schema_version` description states a policy: quoted MAJOR.MINOR or
MAJOR.MINOR.PATCH; same major at or below supported accepted silently; same
major with a HIGHER minor accepted with a warning; a different major, a missing
value or a malformed one refused; PATCH ignored. Before this file existed the
policy was prose only, and prose is implementable in both wrong directions at
once: an exact-match version list refuses "1.0.1" and "1.1", which the schema
promises are acceptable, while no gate at all accepts "2.0", the one case the
policy says must be refused. Both have happened in this ecosystem. This table is
what makes either impossible to reintroduce quietly.

The cases are asserted directly rather than by importing chiplet-spec's
reference reader, because this repository's CI deliberately installs no sibling
checkout, and a test that skips is not a gate. `test_parity_with_reference`
additionally checks the live reference WHEN it happens to be importable, so a
change on that side is caught where a developer can see it; it is a bonus, not
the contract.
"""

import json
import os
import sys
import warnings
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve()
_PKG = _HERE.parents[1] / "python"
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

import interconnect_manifest as im  # noqa: E402

SUPPORTED = im.SUPPORTED_SCHEMA_VERSION


@pytest.fixture(autouse=True)
def _clean_warn_state():
    im._reset_version_warnings()
    yield
    im._reset_version_warnings()


# (value, supported, expected_normalized) -- accepted with NO warning.
ACCEPT_SILENT = [
    ("1.0",     "1.0", "1.0"),   # the shipped manifest
    ("1.0.0",   "1.0", "1.0"),   # PATCH ignored
    ("1.0.5",   "1.0", "1.0"),   # PATCH ignored, any value
    ("1.0.99",  "1.0", "1.0"),
    (" 1.0 ",   "1.0", "1.0"),   # padded: laxer than the schema pattern on
                                 # purpose, matching chiplet-spec (SPEC-2)
    ("1.1",     "1.2", "1.1"),   # same major, LOWER minor
    ("1.0",     "1.2", "1.0"),
    ("2.3",     "2.3", "2.3"),   # supported need not be 1.x
]

# (value, supported, expected_normalized) -- accepted WITH one warning.
ACCEPT_WARN = [
    ("1.1",   "1.0", "1.1"),
    ("1.9",   "1.0", "1.9"),
    ("1.1.3", "1.0", "1.1"),   # PATCH dropped from the normalized result
    ("1.10",  "1.0", "1.10"),  # minor 10 > 1, not a float comparison
]

# (value, supported) -- refused with ManifestVersionError.
REFUSE = [
    (None,        "1.0"),   # missing
    ("2.0",       "1.0"),   # different major, higher
    ("0.9",       "1.0"),   # different major, LOWER -- also refused
    ("2.0.1",     "1.0"),
    ("",          "1.0"),   # malformed
    ("1",         "1.0"),   # one component
    ("1.0.0.0",   "1.0"),   # four components
    ("1.x",       "1.0"),
    ("v1.0",      "1.0"),
    ("1.-1",      "1.0"),   # negative
    ("-1.0",      "1.0"),
    (1.0,         "1.0"),   # a bare JSON number is NOT coerced
    (10,          "1.0"),
    (True,        "1.0"),
    (["1.0"],     "1.0"),
    ({"v": "1"},  "1.0"),
    # int() accepts all of these and the schema pattern accepts none. They are
    # here because a reader that took them made a document load in Python and
    # throw in a C++ host, which is a reader-parity divergence, not a tolerance.
    # See test_no_int_permissivity_survives below for why they get their own
    # guard as well as a row here.
    ("+1.0",      "1.0"),   # sign
    ("1.0_0",     "1.0"),   # PEP 515 underscore separator
    ("1. 0",      "1.0"),   # inner whitespace
    ("1.\u0660",  "1.0"),  # ARABIC-INDIC DIGIT ZERO
    ("\uff11.\uff10", "1.0"),  # FULLWIDTH DIGIT ONE / ZERO
]


@pytest.mark.parametrize("value,supported,expected", ACCEPT_SILENT)
def test_accepted_silently(value, supported, expected):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert im.check_schema_version(value, supported, name="t") == expected
    assert [w for w in caught
            if issubclass(w.category, im.ManifestVersionWarning)] == []


@pytest.mark.parametrize("value,supported,expected", ACCEPT_WARN)
def test_accepted_with_warning(value, supported, expected):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert im.check_schema_version(value, supported, name="t") == expected
    hits = [w for w in caught
            if issubclass(w.category, im.ManifestVersionWarning)]
    assert len(hits) == 1, [str(w.message) for w in caught]
    assert repr(value) in str(hits[0].message)


@pytest.mark.parametrize("value,supported", REFUSE)
def test_refused(value, supported):
    with pytest.raises(im.ManifestVersionError):
        im.check_schema_version(value, supported, name="t")


def test_refusal_is_not_a_keyerror():
    """Consumers wrap manifest access in `except KeyError` to mean "unknown
    method". A version refusal caught by that handler would be downgraded into a
    silently empty result, which is how a bad manifest reaches a GDS."""
    assert issubclass(im.ManifestVersionError, ValueError)
    assert not issubclass(im.ManifestVersionError, KeyError)
    try:
        im.check_schema_version("2.0", "1.0", name="t")
    except KeyError:  # pragma: no cover - the bug this guards
        pytest.fail("version refusal was catchable as KeyError")
    except im.ManifestVersionError:
        pass


def test_warning_is_emitted_once_per_version():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        for _ in range(4):
            im.check_schema_version("1.1", "1.0", name="same")
        im.check_schema_version("1.2", "1.0", name="same")
    hits = [w for w in caught
            if issubclass(w.category, im.ManifestVersionWarning)]
    assert len(hits) == 2, [str(w.message) for w in hits]


def test_distinct_artifacts_do_not_suppress_each_other():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        im.check_schema_version("1.1", "1.0", name="a.json")
        im.check_schema_version("1.1", "1.0", name="b.json")
    hits = [w for w in caught
            if issubclass(w.category, im.ManifestVersionWarning)]
    assert len(hits) == 2


def test_supported_argument_must_itself_be_wellformed():
    with pytest.raises(ValueError) as exc:
        im.check_schema_version("1.0", "not-a-version", name="t")
    assert not isinstance(exc.value, im.ManifestVersionError)


def test_shipped_manifest_declares_a_supported_version():
    root = _HERE.parents[3]
    declared = json.loads(
        (root / "manifest" / "interconnect_methods.json").read_text()
    )["schema_version"]
    with warnings.catch_warnings():
        warnings.simplefilter("error")   # the shipped manifest must not warn
        assert im.check_schema_version(declared) == SUPPORTED


def test_load_manifest_refuses_a_different_major(tmp_path):
    """The gate is on the loader, not only on the helper: a consumer that never
    calls check_schema_version still cannot read an incompatible manifest."""
    root = _HERE.parents[3]
    manifest = json.loads(
        (root / "manifest" / "interconnect_methods.json").read_text())
    manifest["schema_version"] = "2.0"
    # A plausible major-2 change: micrometres become nanometres.
    manifest["methods"]["cupillar_opt2"]["body_diameter_um"] = 49000
    bad = tmp_path / "interconnect_methods.json"
    bad.write_text(json.dumps(manifest))

    im.clear_cache()
    with pytest.raises(im.ManifestVersionError):
        im.load_manifest(str(bad))
    im.clear_cache()


def test_cache_cannot_serve_a_stale_manifest(tmp_path):
    """The gate must not be defeatable by the cache.

    An mtime-keyed cache is unsound here: cp -p, rsync -a, tar -x and a
    second-resolution filesystem all produce changed content under an unchanged
    mtime, and the reader would then serve the earlier document -- including its
    earlier schema_version, which silently bypasses the gate. This reproduces
    exactly that sequence and requires the refusal.
    """
    root = _HERE.parents[3]
    good = json.loads(
        (root / "manifest" / "interconnect_methods.json").read_text())
    path = tmp_path / "interconnect_methods.json"
    path.write_text(json.dumps(good))
    stat_before = path.stat()

    im.clear_cache()
    assert im.load_manifest(str(path))["schema_version"] == SUPPORTED

    bad = json.loads(json.dumps(good))
    bad["schema_version"] = "2.0"
    # The plausible major-2 change: micrometres become nanometres.
    bad["methods"]["cupillar_opt2"]["body_diameter_um"] = 49000
    path.write_text(json.dumps(bad))
    os.utime(path, ns=(stat_before.st_atime_ns, stat_before.st_mtime_ns))

    with pytest.raises(im.ManifestVersionError):
        im.load_manifest(str(path))
    im.clear_cache()


def test_cache_still_serves_an_unchanged_file(tmp_path):
    """The fix must not turn the cache off: identical bytes reuse the parse."""
    root = _HERE.parents[3]
    path = tmp_path / "interconnect_methods.json"
    path.write_text((root / "manifest" / "interconnect_methods.json").read_text())

    im.clear_cache()
    first = im.load_manifest(str(path))
    second = im.load_manifest(str(path))
    assert first is second, "identical content should hit the cache"
    assert len(im._cache) == 1
    im.clear_cache()


@pytest.mark.parametrize("body", ['["schema_version"]', '"1.0"', '42', 'null'])
def test_non_object_manifest_is_refused_not_an_attributeerror(body, tmp_path):
    """Valid JSON that is not an object has no schema_version to read. The gate
    is the first thing to touch the document, so it must refuse it rather than
    raise AttributeError from inside the reader."""
    path = tmp_path / "interconnect_methods.json"
    path.write_text(body)
    im.clear_cache()
    with pytest.raises(im.ManifestVersionError):
        im.load_manifest(str(path))
    im.clear_cache()


def test_on_warn_receives_every_event_undeduped():
    """The hook a delegating consumer uses to keep its own warning channel."""
    events = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for _ in range(3):
            im.check_schema_version("1.1", "1.0", name="t",
                                    on_warn=events.append)
    assert len(events) == 3, events


def test_supported_is_resolved_per_call():
    """A host that rebinds the constant is honoured, so the default is not
    frozen at definition time."""
    original = im.SUPPORTED_SCHEMA_VERSION
    try:
        im.SUPPORTED_SCHEMA_VERSION = "2.0"
        assert im.check_schema_version("2.0", name="t") == "2.0"
        with pytest.raises(im.ManifestVersionError):
            im.check_schema_version("1.0", name="t")
    finally:
        im.SUPPORTED_SCHEMA_VERSION = original


def test_parity_with_reference():
    """Bonus, not the contract: when a chiplet-spec checkout is importable,
    every case above must get the same verdict AND the same warn-or-silent
    outcome from the reference reader. CI installs no sibling, so this skips
    there; the tables above are the gate.

    Asserting the warn/silent split matters: a reference that warned on
    everything, or on nothing, would pass a return-value-only comparison, and
    that split is the half of the policy most likely to drift.
    """
    cfio = pytest.importorskip(
        "chiplet_format_io",
        reason="chiplet-spec not importable; the truth tables are the gate")
    check = cfio.check_contract_version
    err = cfio.ContractVersionError

    def reference(value, supported):
        """(normalized, warned) from the reference, using its own on_warn."""
        events = []
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            got = check(value, supported, name="parity",
                        on_warn=events.append)
        return got, bool(events)

    for value, supported, expected in ACCEPT_SILENT:
        got, warned = reference(value, supported)
        assert got == expected, "reference verdict differs on %r/%r" % (
            value, supported)
        assert not warned, "reference WARNS on %r/%r where we are silent" % (
            value, supported)

    for value, supported, expected in ACCEPT_WARN:
        got, warned = reference(value, supported)
        assert got == expected, "reference verdict differs on %r/%r" % (
            value, supported)
        assert warned, "reference is SILENT on %r/%r where we warn" % (
            value, supported)

    for value, supported in REFUSE:
        with pytest.raises(err):
            check(value, supported, name="parity")


#: Values `int()` accepts and the schema pattern refuses. This list was
#: originally KNOWN_LAXER_THAN_SCHEMA, asserting that the reader took them: a
#: documented divergence, on the theory that the reader may be kinder than its
#: schema. That theory did not survive counting the parties. The schema pattern
#: and chiplet-spec's C++ `parse_version_parts` had ALWAYS required plain ASCII
#: digits; only the Python readers diverged, so the same document loaded in
#: Python and threw in C++. Both Python readers were tightened. The list is
#: kept, with its assertion inverted, because these are exactly the values a
#: future `int(part)` would silently readmit.
#:
#: A padded " 1.0 " is deliberately NOT here: chiplet-spec's sidecar parser
#: strips on purpose and has a test saying whitespace is not a version change,
#: so both readers stay laxer than the schema pattern there and chiplet-spec
#: tracks the gap as SPEC-2. Tightening it here alone would be the same
#: parity divergence in the other direction.
INT_PERMISSIVITY = ["+1.0", "1.0_0", "1. 0", "1.\u0660", "\uff11.\uff10"]


@pytest.mark.parametrize("value", INT_PERMISSIVITY)
def test_no_int_permissivity_survives(value):
    import re
    pattern = r"^[0-9]+\.[0-9]+(\.[0-9]+)?$"
    assert not re.match(pattern, value), (
        "%r matches the schema pattern; it does not belong in this list" % value)
    with pytest.raises(im.ManifestVersionError):
        im.check_schema_version(value, "1.0", name="t")
