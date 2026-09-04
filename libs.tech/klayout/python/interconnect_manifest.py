#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""
interconnect_manifest.py -- reader API for the interconnect PDK manifest.

Single source of truth for interconnection methods (Cu pillars, solder
bumps, microbumps). Consumers import this instead of hardcoding the
cupillar_opt1/2/3 tables: the KiCad plugin's hyp_to_gds.py and
chiplet_writer.py, this repo's bump_lef_generator.py, and the vendorx demo.
(The interposer's bump_mirror.py imports bump3d_generator for the 3D bodies
but never loads the manifest, so it is not gated by anything here.)

Pure standard library (json + pathlib + os + warnings) so it imports cleanly
inside KiCad's bundled Python. No third-party dependencies.

The manifest's ``schema_version`` is gated on load with the shared ecosystem
version policy (see SUPPORTED_SCHEMA_VERSION). The policy is implemented here
rather than imported, because this repository deliberately depends on nothing;
``interconnect_tests/test_version_policy.py`` freezes the semantics as a truth
table and, when a chiplet-spec checkout happens to be importable, additionally
asserts parity against ``chiplet_format_io.check_contract_version``.

Discovery order for the manifest (when no explicit path is given):
  1. $INTERCONNECT_PDK_ROOT/manifest/interconnect_methods.json
  2. the repo's own manifest/ relative to this file
     (this file lives at libs.tech/klayout/python/, the manifest at the root)
  3. walk parent directories for a sibling checkout named interconnect_pdk/ or
     IHP-Interconnect-IntM4TM2/ holding manifest/interconnect_methods.json
     (locates the sibling repo, mirroring how hyp_to_gds discovers gds_to_kicad)
"""

import hashlib
import json
import os
import warnings
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

_MANIFEST_NAME = "interconnect_methods.json"

#: The manifest contract version this reader understands.
#:
#: This is NOT a membership test. WHICH versions are accepted is the shared
#: version policy the schema's own ``schema_version`` description points at:
#: same major with a minor at or below this one is accepted silently, same major
#: with a HIGHER minor is accepted with a warning (the manifest may carry
#: additions this reader does not understand), a different major is refused, and
#: PATCH is ignored throughout. An exact-match tuple would refuse "1.0.1" and
#: "1.1", both of which the schema promises a consumer must accept.
SUPPORTED_SCHEMA_VERSION = "1.0"


class ManifestVersionError(ValueError):
    """The manifest declares a schema_version this reader must not read.

    Subclasses ValueError, not KeyError, on purpose. Consumers wrap manifest
    access in ``except KeyError`` to mean "unknown method" and fall back to a
    default or to an empty result, so a refusal raised as KeyError would be
    swallowed by that handler and the run would finish at exit 0 with the bump
    bodies missing.

    Stated as a shape and not as a list of call sites: any caller that reads
    KeyError as "not in the registry" turns a version refusal into missing
    geometry. This docstring named two such functions until a consumer checked
    them and found one of the two wrong. They live in repositories this one does
    not control, so nothing here can keep such a list true.

    Scope: this closes that path for the VERSION only. A manifest that declares
    a supported version but is structurally broken still reaches the same
    handlers; structural validation is a separate change.
    """


class ManifestVersionWarning(UserWarning):
    """The manifest is a same-major newer minor than this reader supports."""


# Warn-once keys, (name, normalized version). Mirrors the reference reader so a
# long-lived host (the KiCad plugin) does not repeat one warning per call.
_WARNED_VERSIONS = set()


def _reset_version_warnings() -> None:
    """Clear the warn-once dedup set (test hook, mirroring the reference)."""
    _WARNED_VERSIONS.clear()


def _parse_contract_version(value: Any) -> Optional[Tuple[int, int]]:
    """Parse "MAJOR.MINOR" or "MAJOR.MINOR.PATCH" into (major, minor).

    Returns None if the value is not a well-formed version string. PATCH is
    parsed only to be discarded: a patch never changes what a consumer may
    assume, so it must never change a verdict either.

    A non-string is NOT coerced. The manifest is JSON, where an unquoted 1.10 is
    the number 1.1 with no way back, so a bare number is malformed here. (The
    chiplet-spec reader does coerce, because .chiplet is YAML and an unquoted
    1.0 is a legitimate spelling there. JSON has no such spelling, so the
    tolerance would buy nothing here and would only widen what this accepts.)
    """
    if not isinstance(value, str):
        return None
    # No .strip(). This briefly kept one to match chiplet-spec's sidecar parser,
    # which tolerated padding deliberately; SPEC-2 then resolved in the STRICT
    # direction (chiplet-spec 5fa0ced) and the padding tolerance went away on
    # that side, so parity now requires dropping it here too. The schema pattern
    # always refused a padded value, so this is the third implementation joining
    # the two that already agreed, the same shape as the ASCII-digit fix below.
    parts = value.split(".")
    if len(parts) not in (2, 3):
        return None
    # ASCII digits only, checked BEFORE int(). int() is far more permissive than
    # the schema pattern: it takes a sign, underscore separators, surrounding
    # whitespace and non-ASCII digits, so "+1.0", "1.0_0", "1. 0", " 1.0 " and
    # "1.\u0660" all parsed as (1, 0). That was never a tolerance anyone chose;
    # it was int()'s behaviour leaking through a check that never looked. The
    # schema pattern and chiplet-spec's C++ reader always required plain ASCII
    # digits, so accepting these made a document that loads here throw in a C++
    # host. chiplet-spec's Python reader was tightened to match at 79ab98f; this
    # keeps the third implementation on the same side.
    if not all(part.isascii() and part.isdigit() for part in parts):
        return None
    numbers = [int(p) for p in parts]
    return (numbers[0], numbers[1])


def check_schema_version(value: Any, supported: Optional[str] = None, *,
                         name: str = _MANIFEST_NAME,
                         on_warn: Optional[Callable[[str], None]] = None) -> str:
    """Apply the shared version policy; return the normalized "MAJOR.MINOR".

    Same rule every governed sidecar in the ecosystem uses, and the same one the
    schema's ``schema_version`` description names: a quoted MAJOR.MINOR or
    MAJOR.MINOR.PATCH string; same major with a minor at or below ``supported``
    accepted silently; same major with a higher minor accepted with a warning; a
    different major (higher OR lower), a missing value or a malformed one
    refused with :class:`ManifestVersionError`; PATCH ignored throughout.

    ``supported`` defaults to :data:`SUPPORTED_SCHEMA_VERSION` and is resolved
    per call, so a host that rebinds the constant is honoured. ``on_warn``
    receives every warning event undeduped, mirroring the reference reader, so a
    caller can take this verdict while keeping its own warning channel.
    """
    if supported is None:
        supported = SUPPORTED_SCHEMA_VERSION
    sup = _parse_contract_version(supported)
    if sup is None:
        raise ValueError(
            "supported version %r for %s is not a \"MAJOR.MINOR\" string"
            % (supported, name))
    sup_major, sup_minor = sup
    if value is None:
        raise ManifestVersionError(
            "%s: missing required key: schema_version" % name)
    parsed = _parse_contract_version(value)
    if parsed is None:
        raise ManifestVersionError(
            "%s: malformed schema_version %r; expected a quoted "
            "\"MAJOR.MINOR\" or \"MAJOR.MINOR.PATCH\" string" % (name, value))
    major, minor = parsed
    if major != sup_major:
        raise ManifestVersionError(
            "%s: unsupported schema_version %r; this reader supports major %d "
            "(e.g. %r)" % (name, value, sup_major, supported))
    normalized = "%d.%d" % (major, minor)
    if minor > sup_minor:
        msg = ("%s: schema_version %r is newer than this reader's %r (same "
               "major %d); reading it as %r and ignoring unknown additions"
               % (name, value, supported, major, supported))
        if on_warn is not None:
            on_warn(msg)
        key = (name, normalized)
        if key not in _WARNED_VERSIONS:
            # Warn FIRST, record the key only once the warning has been
            # delivered. Recording first looks equivalent and is not: under a
            # host that escalates warnings, warnings.warn RAISES, and with the
            # key already recorded every later read skips the warn entirely and
            # returns the version silently. So the first read refused and the
            # rest accepted, which is worse than either verdict on its own.
            # This ordering makes an escalating host refuse every read and a
            # normal host still warn exactly once.
            warnings.warn(msg, ManifestVersionWarning, stacklevel=2)
            _WARNED_VERSIONS.add(key)
    return normalized
# Keyed by (path, sha256 of the file's bytes), NOT by mtime. An mtime key is
# not sound here: cp -p, rsync -a, tar -x and a second-resolution filesystem all
# reproduce a changed file under an unchanged mtime, and the reader would then
# serve the previous content -- including its previous schema_version, which
# silently defeats the gate below. Hashing costs one read of a ~6 KB file and
# the cache still saves the parse, which is the expensive half.
_cache: Dict[tuple, dict] = {}


# ---------------------------------------------------------------------------
# Discovery + loading
# ---------------------------------------------------------------------------

def find_manifest_path() -> Optional[Path]:
    """Locate interconnect_methods.json without loading it. Returns None if absent."""
    env = os.environ.get("INTERCONNECT_PDK_ROOT")
    if env:
        cand = Path(env) / "manifest" / _MANIFEST_NAME
        if cand.exists():
            return cand

    # libs.tech/klayout/python/ -> repo root is three levels up.
    here = Path(__file__).resolve().parent
    cand = here.parents[2] / "manifest" / _MANIFEST_NAME
    if cand.exists():
        return cand

    # Accept both the canonical ecosystem name and the upstream repository name,
    # matching bump_mirror._get_bump3d so the two discovery paths agree.
    for base in [here, *here.parents]:
        for name in ("interconnect_pdk", "IHP-Interconnect-IntM4TM2"):
            cand = base / name / "manifest" / _MANIFEST_NAME
            if cand.exists():
                return cand
    return None


def load_manifest(path: Optional[str] = None) -> dict:
    """Load and cache the manifest, gated on the version policy.

    Raises FileNotFoundError if not found, and ManifestVersionError if the
    manifest declares a schema_version this reader must not read.

    The cache is keyed by (path, mtime), so editing the manifest on disk in a
    long-lived host (e.g. the KiCad plugin) is picked up instead of serving the
    stale first-loaded copy.
    """
    if path is None:
        found = find_manifest_path()
        if found is None:
            raise FileNotFoundError(
                "interconnect_methods.json not found. Set INTERCONNECT_PDK_ROOT "
                "to the interconnect_pdk repo root, or pass an explicit path."
            )
        path = str(found)
    path = str(path)
    with open(path, "rb") as f:
        raw = f.read()
    key = (path, hashlib.sha256(raw).hexdigest())
    if key not in _cache:
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse manifest {path}: {e}") from e
        except UnicodeDecodeError as e:
            raise ValueError(f"Manifest {path} is not valid UTF-8: {e}") from e
        _cache[key] = parsed
    manifest = _cache[key]
    # A JSON document that is not an object has no schema_version to read, so
    # the gate refuses it here rather than letting `.get` raise AttributeError
    # from inside the reader.
    if not isinstance(manifest, dict):
        raise ManifestVersionError(
            "%s: manifest must be a JSON object, got %s"
            % (path, type(manifest).__name__))
    # Checked on every call, not only on a cache miss. Combined with the
    # content-addressed key above, the verdict depends on what is on disk now
    # and never on what this process happened to read earlier.
    check_schema_version(manifest.get("schema_version"), name=path)
    return manifest


def clear_cache() -> None:
    """Drop the manifest cache (useful in tests that swap manifests)."""
    _cache.clear()


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def list_methods(manifest: Optional[dict] = None) -> List[str]:
    """All method ids defined in the manifest (declaration order)."""
    m = manifest or load_manifest()
    return list(m["methods"].keys())


def default_method(manifest: Optional[dict] = None) -> str:
    m = manifest or load_manifest()
    return m["default_method"]


def get_method(method_id: str, manifest: Optional[dict] = None) -> dict:
    """Return the full method dict. Raises KeyError if unknown."""
    m = manifest or load_manifest()
    try:
        return m["methods"][method_id]
    except KeyError:
        raise KeyError(
            "Unknown interconnect method '%s'. Known methods: %s"
            % (method_id, ", ".join(m["methods"].keys()))
        )


def get_layer(name: str, manifest: Optional[dict] = None) -> Tuple[int, int]:
    """(gds_layer, gds_datatype) for a 3D layer name. Raises KeyError if unknown."""
    m = manifest or load_manifest()
    try:
        entry = m["layer_registry"][name]
    except KeyError:
        raise KeyError(
            "Unknown 3D layer '%s'. Known layers: %s"
            % (name, ", ".join(m["layer_registry"].keys()))
        )
    return entry["gds_layer"], entry["gds_datatype"]


def layers_3d(method_id: str, manifest: Optional[dict] = None) -> List[Tuple[str, int, int]]:
    """[(name, gds_layer, gds_datatype), ...] for a method's 3D bodies."""
    m = manifest or load_manifest()
    method = get_method(method_id, m)
    out = []
    for name in method["layers_3d"]:
        layer, datatype = get_layer(name, m)
        out.append((name, layer, datatype))
    return out


def get_connection_library(manifest: Optional[dict] = None) -> "OrderedDict[str, dict]":
    """
    Ordered {method_id: {description, layers}} for the default bump library.

    This is what the .chiplet `connection_stacks:` block is built from. Order
    and membership come from `default_connection_library`, so the emitted block
    is deterministic and excludes non-default methods (e.g. the vendorx demo).
    """
    m = manifest or load_manifest()
    out: "OrderedDict[str, dict]" = OrderedDict()
    for mid in m["default_connection_library"]:
        method = get_method(mid, m)
        out[mid] = {
            "description": method["description"],
            # Copy the layers (list + dicts) so a caller editing/sorting them in
            # place cannot poison the cached manifest for the next reader.
            "layers": [dict(layer) for layer in method["connection_stack"]["layers"]],
        }
    return out


def get_connection_stack(method_id: str, manifest: Optional[dict] = None) -> dict:
    """{description, layers} for one method (used when emitting a single stack)."""
    method = get_method(method_id, manifest)
    return {
        "description": method["description"],
        # Copy so a caller cannot mutate the cached manifest in place.
        "layers": [dict(layer) for layer in method["connection_stack"]["layers"]],
    }


def body_diameter(method_id: str, manifest: Optional[dict] = None) -> float:
    """Cu-pillar / bump body diameter (um) for a method."""
    return float(get_method(method_id, manifest)["body_diameter_um"])


def pitch_rules(method_id: str, manifest: Optional[dict] = None) -> Dict[str, float]:
    """{IXN_spacing, IXN_pitch} (um) for a method."""
    return dict(get_method(method_id, manifest)["pitch_rules"])


def fab_params(method_id: str, manifest: Optional[dict] = None) -> Dict[str, float]:
    """{passiv_opening_um, tm2_enclosure_um, ...} -- fab anchor params (stay on interposer)."""
    return dict(get_method(method_id, manifest)["fab_params"])


def adapter_for(method_id: str, manifest: Optional[dict] = None) -> str:
    """ADK interconnect adapter basename for a method."""
    return get_method(method_id, manifest)["adapter"]
