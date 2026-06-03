#!/usr/bin/env python3
"""
Validate interconnect_methods.json: schema, cross-field invariants, and
byte-exact reproduction of the IHP connection-stack literals that the suite
currently hardcodes (the 0-regression contract).

Runnable two ways:
  pytest interconnect_pdk/python/tests/test_manifest.py
  python3 interconnect_pdk/python/tests/test_manifest.py
"""

import json
import sys
from pathlib import Path

_PKG = Path(__file__).resolve().parents[1]          # interconnect_pdk/python
_ROOT = _PKG.parent                                  # interconnect_pdk
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

import interconnect_manifest as im  # noqa: E402

MANIFEST_PATH = _ROOT / "manifest" / "interconnect_methods.json"
SCHEMA_PATH = _ROOT / "manifest" / "schema" / "interconnect_methods.schema.json"


# ---------------------------------------------------------------------------
# Golden literals -- transcribed verbatim from the pre-split hardcoded tables
# (chiplet_kicad_plugin/writers/chiplet_writer.py:275-293). If the manifest
# stops reproducing these, the byte-exact .chiplet gate would break.
# ---------------------------------------------------------------------------
EXPECTED_LIBRARY = {
    "cupillar_opt1": {
        "description": "PacTech Cu Pillar, Table 6.1 Option 1 (35um opening)",
        "layers": [
            ("CuPillar", "Cu", 28.0, 44.0),
            ("SnAgCap", "SnAg", 16.0, 44.0),
        ],
    },
    "cupillar_opt2": {
        "description": "PacTech Cu Pillar, Table 6.1 Option 2 (40um opening)",
        "layers": [
            ("CuPillar", "Cu", 32.0, 49.0),
            ("SnAgCap", "SnAg", 16.0, 49.0),
        ],
    },
    "cupillar_opt3": {
        "description": "PacTech Cu Pillar, Table 6.1 Option 3 (45um opening)",
        "layers": [
            ("CuPillar", "Cu", 42.0, 54.0),
            ("SnAgCap", "SnAg", 19.0, 54.0),
        ],
    },
    "sbump_sac305": {
        "description": "PacTech SAC305 solder bump (80um ball)",
        "layers": [
            ("SolderBall", "SAC305", 80.0, 80.0),
        ],
    },
}
EXPECTED_LIBRARY_ORDER = ["cupillar_opt1", "cupillar_opt2", "cupillar_opt3", "sbump_sac305"]


def _manifest():
    im.clear_cache()
    return im.load_manifest(str(MANIFEST_PATH))


def test_schema_validation():
    """Manifest validates against the JSON schema (skipped if jsonschema absent)."""
    try:
        import jsonschema
    except ImportError:
        print("SKIP schema validation: jsonschema not installed")
        return
    manifest = json.loads(MANIFEST_PATH.read_text())
    schema = json.loads(SCHEMA_PATH.read_text())
    jsonschema.validate(instance=manifest, schema=schema)


def test_layer_registry_unique_and_in_range():
    m = _manifest()
    seen = {}
    for name, entry in m["layer_registry"].items():
        assert entry["gds_layer"] >= 500, "%s uses reserved layer < 500" % name
        assert entry["gds_datatype"] in (35, 36), "%s bad datatype" % name
        key = (entry["gds_layer"], entry["gds_datatype"])
        assert key not in seen, "GDS collision %s: %s vs %s" % (key, seen[key], name)
        seen[key] = name


def test_method_references_resolve():
    m = _manifest()
    registry = set(m["layer_registry"].keys())
    anchors = set(m["fab_anchors"].keys())
    for mid, method in m["methods"].items():
        assert method["fab_anchor"] in anchors, "%s: bad fab_anchor" % mid
        for ln in method["layers_3d"]:
            assert ln in registry, "%s: layers_3d %s not in registry" % (mid, ln)
        for layer in method["connection_stack"]["layers"]:
            assert layer["name"] in registry, \
                "%s: connection_stack layer %s not in registry" % (mid, layer["name"])
        assert method["adapter"], "%s: empty adapter" % mid
        pr = method["pitch_rules"]
        assert pr["IXN_pitch"] >= pr["IXN_spacing"], "%s: pitch < spacing" % mid


def test_default_pointers_valid():
    m = _manifest()
    methods = set(m["methods"].keys())
    assert m["default_method"] in methods
    for mid in m["default_connection_library"]:
        assert mid in methods, "default_connection_library entry %s missing" % mid


def test_connection_library_byte_exact_spec():
    """The default library must reproduce the pre-split hardcoded literals."""
    m = _manifest()
    lib = im.get_connection_library(m)
    assert list(lib.keys()) == EXPECTED_LIBRARY_ORDER, \
        "library order drift: %s" % list(lib.keys())
    for mid, expected in EXPECTED_LIBRARY.items():
        got = lib[mid]
        assert got["description"] == expected["description"], "%s description drift" % mid
        got_layers = [
            (l["name"], l["material"], float(l["height"]), float(l["diameter"]))
            for l in got["layers"]
        ]
        assert got_layers == expected["layers"], "%s layer drift: %s" % (mid, got_layers)


def test_vendorx_demo_present_but_not_in_default_library():
    """The 2nd-vendor demo exists as a method but is excluded from the default lib."""
    m = _manifest()
    assert "vendorx_microbump" in m["methods"]
    assert "vendorx_microbump" not in m["default_connection_library"]
    vx = im.get_method("vendorx_microbump", m)
    # Reuses the IHP cu-pillar fab anchor (same 9/35 + 41/35 openings).
    assert vx["fab_anchor"] == "ihp_cupillar_anchor"
    # Its own 3D layers, outside the IHP 500-502 range.
    assert {l for (l, _, _) in im.layers_3d("vendorx_microbump", m)} == {
        "VendorXBumpCu", "VendorXBumpCap"
    }
    # Finer pitch than any IHP cu-pillar option.
    assert im.pitch_rules("vendorx_microbump", m)["IXN_pitch"] < 75.0


def test_loader_api():
    m = _manifest()
    assert im.default_method(m) == "cupillar_opt2"
    assert ("CuPillar", 500, 35) in im.layers_3d("cupillar_opt2", m)
    assert im.body_diameter("cupillar_opt2", m) == 49.0
    assert im.adapter_for("sbump_sac305", m) == "ihp_sbump"
    assert im.fab_params("cupillar_opt1", m)["passiv_opening_um"] == 35.0


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS %s" % name)
            except Exception as e:  # noqa: BLE001
                failures += 1
                print("FAIL %s: %s" % (name, e))
    sys.exit(1 if failures else 0)
