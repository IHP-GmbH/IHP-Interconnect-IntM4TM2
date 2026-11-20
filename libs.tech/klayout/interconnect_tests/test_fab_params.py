#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""
The pad parameters of fab_params under both of their names (manifest 1.2).

Since 1.2 each pad parameter has a name that ties it to no technology, beside
the old one, which every 1.x keeps. fab_params gives both names with the one
value, for a method that states both and for a 1.1 method that states only the
old one, and refuses a method whose names give two values or that lacks the old
name, with chiplet-spec's ids and texts for the same refusals.
"""

import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve()
_PKG = _HERE.parents[1] / "python"
_ROOT = _HERE.parents[3]
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

import interconnect_manifest as im  # noqa: E402

MANIFEST_PATH = _ROOT / "manifest" / "interconnect_methods.json"
PAIRS = sorted(im.FAB_PARAMS_RENAMED.items())
WORDS = {"passivation_opening_um": "passivation opening",
         "pad_metal_enclosure_um": "pad metal enclosure"}

#: A 1.1 method's pad parameters, old names only.
OLD = {"passiv_opening_um": 40.0, "tm2_enclosure_um": 7.5}
#: The same method at 1.2, both names.
BOTH = {**OLD, "passivation_opening_um": 40.0, "pad_metal_enclosure_um": 7.5}


def _without(params, name):
    return {key: value for key, value in params.items() if key != name}


#: (case, fab_params for one pair, the refusal's text after "r.json: method m "),
#: one row per refusal and pair. The local tests assert the texts; the parity
#: test gives the same rows to the reference reader.
REFUSALS = [row for new, old in PAIRS for row in (
    ("disagree %s" % new, {**BOTH, new: OLD[old] + 5.0},
     "PACKAGE_METHODS_FAB_PARAMS_DISAGREE",
     "gives %s %s and %s %s. Since interconnect methods 1.2 these are two names "
     "for one value, so the file has no single reading. Make them equal."
     % (old, OLD[old], new, OLD[old] + 5.0)),
    ("new name only %s" % new, _without(BOTH, old),
     "PACKAGE_METHODS_FAB_PARAMS_MISSING",
     "has no fab_params.%s. Interconnect methods 1.x keeps the old name beside %s, "
     "so that readers older than 1.2 still find it. Add it with the same value."
     % (old, new)),
    ("neither name %s" % new, _without(OLD, old),
     "PACKAGE_METHODS_FAB_PARAMS_MISSING",
     "has no %s: fab_params.%s and %s are both missing. Add both, with the same "
     "value." % (WORDS[new], old, new)),
)]

#: (case, method) for a method with no pad parameters at all: refused as the
#: first pair with neither name, not KeyError (which reads as no such method).
NO_PARAMS = [("no fab_params", {}), ("fab_params not an object", {"fab_params": [40.0]})]
NO_PARAMS_TEXT = ("PACKAGE_METHODS_FAB_PARAMS_MISSING: r.json: method m has no passivation "
                  "opening: fab_params.passiv_opening_um and passivation_opening_um are both "
                  "missing. Add both, with the same value.")

#: (case, fab_params) that read, a 1.1 method among them.
READS = [("old names only", OLD), ("both names", BOTH),
         ("another key passes", {**OLD, "other_um": 1.0})]


def _one(fab_params):
    return {"methods": {"m": {"fab_params": fab_params}}}


def test_the_shipped_manifest_states_both_names_with_one_value():
    raw = json.loads(MANIFEST_PATH.read_text())
    assert raw["schema_version"] == "1.2"
    m = im.load_manifest(str(MANIFEST_PATH))
    for mid, method in raw["methods"].items():
        for new, old in PAIRS:
            assert method["fab_params"][new] == method["fab_params"][old], (mid, new)
        assert im.fab_params(mid, m) == method["fab_params"], mid


@pytest.mark.parametrize("case,fab_params", READS, ids=[row[0] for row in READS])
def test_a_method_reads_under_both_names(case, fab_params):
    got = im.fab_params("m", _one(fab_params))
    assert got == {**fab_params, **{new: fab_params[old] for new, old in PAIRS}}


def test_the_result_is_a_copy():
    manifest = _one(dict(OLD))
    im.fab_params("m", manifest)["passiv_opening_um"] = 1.0
    assert manifest["methods"]["m"]["fab_params"] == OLD


@pytest.mark.parametrize("case,fab_params,message_id,text", REFUSALS,
                         ids=[row[0] for row in REFUSALS])
def test_a_method_without_a_single_reading_is_refused(case, fab_params, message_id, text):
    with pytest.raises(im.FabParamsRefused) as caught:
        im.fab_params("m", _one(fab_params), where="r.json")
    assert caught.value.message_id == message_id
    assert str(caught.value) == "%s: r.json: method m %s" % (message_id, text)


@pytest.mark.parametrize("case,method", NO_PARAMS, ids=[row[0] for row in NO_PARAMS])
def test_a_method_without_pad_parameters_is_refused(case, method):
    with pytest.raises(im.FabParamsRefused) as caught:
        im.fab_params("m", {"methods": {"m": method}}, where="r.json")
    assert str(caught.value) == NO_PARAMS_TEXT


def test_a_refusal_is_not_an_error_callers_read_as_no_method():
    """Callers catch KeyError, TypeError or ValueError as "no such method" or
    "nothing to read"; a pad parameter with no single reading must not look
    like either."""
    assert not issubclass(im.FabParamsRefused, (KeyError, TypeError, ValueError))
    with pytest.raises(KeyError):
        im.fab_params("no_such_method", _one(OLD))


def test_where_names_the_manifest_or_its_file_name(tmp_path, monkeypatch):
    disagree = REFUSALS[0][1]
    with pytest.raises(im.FabParamsRefused) as given:
        im.fab_params("m", _one(disagree))
    assert given.value.text.startswith("interconnect_methods.json: method m ")

    path = tmp_path / "manifest" / "interconnect_methods.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"schema_version": "1.2", **_one(disagree)}))
    monkeypatch.setenv("INTERCONNECT_PDK_ROOT", str(tmp_path))
    im.clear_cache()
    try:
        with pytest.raises(im.FabParamsRefused) as found:
            im.fab_params("m")
    finally:
        im.clear_cache()
    assert found.value.text.startswith(f"{path}: method m ")
    # An empty dict reads the discovered manifest, and names it.
    im.clear_cache()
    try:
        with pytest.raises(im.FabParamsRefused) as empty:
            im.fab_params("m", {})
    finally:
        im.clear_cache()
    assert empty.value.text.startswith(f"{path}: method m ")


@pytest.mark.needs_sibling_sources
def test_parity_with_reference():
    """The same readings and the same refusals as chiplet-spec's reference
    reader, which gives the new names only, over the rows above and the
    shipped manifest. The tiered runner's T1 installs that reader at its pin;
    this repository's own CI installs no sibling, so it skips there, and the
    rows above are the gate. A pinned reader older than registry 1.2 has no
    method_fab_params: the case skips, and pyproject.toml declares that skip
    until the pin moves."""
    tp = pytest.importorskip(
        "chiplet_format_io.technology_package",
        reason="chiplet-spec not importable; the rows above are the gate")
    if not hasattr(tp, "method_fab_params"):
        pytest.skip("chiplet-spec's reader predates registry 1.2 (no method_fab_params)")
    assert tp.FAB_PARAMS_RENAMED == im.FAB_PARAMS_RENAMED
    m = im.load_manifest(str(MANIFEST_PATH))
    readings = [(mid, method["fab_params"]) for mid, method in m["methods"].items()]
    for case, fab_params in [*READS, *readings]:
        ours = im.fab_params("m", _one(fab_params))
        assert tp.method_fab_params("m", {"fab_params": fab_params}, where="r.json") == {
            new: ours[new] for new in im.FAB_PARAMS_RENAMED}, case
    for case, fab_params, _, _ in REFUSALS:
        with pytest.raises(im.FabParamsRefused) as ours:
            im.fab_params("m", _one(fab_params), where="r.json")
        with pytest.raises(tp.TechnologyPackageError) as theirs:
            tp.method_fab_params("m", {"fab_params": fab_params}, where="r.json")
        assert str(ours.value) == str(theirs.value), case
    for case, method in NO_PARAMS:
        with pytest.raises(im.FabParamsRefused) as ours:
            im.fab_params("m", {"methods": {"m": method}}, where="r.json")
        with pytest.raises(tp.TechnologyPackageError) as theirs:
            tp.method_fab_params("m", method, where="r.json")
        assert str(ours.value) == str(theirs.value), case
