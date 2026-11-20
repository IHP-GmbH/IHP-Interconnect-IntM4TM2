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


def _one(fab_params, method="cupillar_opt2"):
    return {"methods": {method: {"fab_params": fab_params}}}


def _refused(fab_params, **kwargs):
    with pytest.raises(im.FabParamsRefused) as caught:
        im.fab_params("cupillar_opt2", _one(fab_params), where="r.json", **kwargs)
    return caught.value


def test_the_shipped_manifest_states_both_names_with_one_value():
    raw = json.loads(MANIFEST_PATH.read_text())
    assert raw["schema_version"] == "1.2"
    m = im.load_manifest(str(MANIFEST_PATH))
    for mid, method in raw["methods"].items():
        for new, old in PAIRS:
            assert method["fab_params"][new] == method["fab_params"][old], (mid, new)
        assert im.fab_params(mid, m) == method["fab_params"], mid


def test_a_1_1_method_reads_under_both_names():
    got = im.fab_params("cupillar_opt2", _one(
        {"passiv_opening_um": 35.0, "tm2_enclosure_um": 7.5, "other_um": 1.0}))
    assert got == {"passiv_opening_um": 35.0, "tm2_enclosure_um": 7.5, "other_um": 1.0,
                   "passivation_opening_um": 35.0, "pad_metal_enclosure_um": 7.5}


def test_the_result_is_a_copy():
    manifest = _one({"passiv_opening_um": 35.0, "tm2_enclosure_um": 7.5})
    im.fab_params("cupillar_opt2", manifest)["passiv_opening_um"] = 1.0
    assert manifest["methods"]["cupillar_opt2"]["fab_params"] == {
        "passiv_opening_um": 35.0, "tm2_enclosure_um": 7.5}


@pytest.mark.parametrize("new,old", PAIRS)
def test_two_names_with_two_values_are_refused(new, old):
    fab_params = {"passiv_opening_um": 40.0, "tm2_enclosure_um": 7.5}
    fab_params[new] = fab_params[old] + 5.0
    refused = _refused(fab_params)
    assert refused.message_id == "PACKAGE_METHODS_FAB_PARAMS_DISAGREE"
    assert str(refused) == (
        f"PACKAGE_METHODS_FAB_PARAMS_DISAGREE: r.json: method cupillar_opt2 gives "
        f"{old} {fab_params[old]} and {new} {fab_params[new]}. Since interconnect "
        f"methods 1.2 these are two names for one value, so the file has no single "
        f"reading. Make them equal.")


@pytest.mark.parametrize("new,old", PAIRS)
def test_a_method_with_the_new_name_only_is_refused(new, old):
    fab_params = {"passivation_opening_um": 40.0, "pad_metal_enclosure_um": 7.5,
                  "passiv_opening_um": 40.0, "tm2_enclosure_um": 7.5}
    del fab_params[old]
    refused = _refused(fab_params)
    assert refused.message_id == "PACKAGE_METHODS_FAB_PARAMS_MISSING"
    assert str(refused) == (
        f"PACKAGE_METHODS_FAB_PARAMS_MISSING: r.json: method cupillar_opt2 has no "
        f"fab_params.{old}. Interconnect methods 1.x keeps the old name beside {new}, "
        f"so that readers older than 1.2 still find it. Add it with the same value.")


@pytest.mark.parametrize("new,old", PAIRS)
def test_a_method_with_neither_name_is_refused(new, old):
    fab_params = {"passiv_opening_um": 40.0, "tm2_enclosure_um": 7.5}
    del fab_params[old]
    refused = _refused(fab_params)
    assert str(refused) == (
        f"PACKAGE_METHODS_FAB_PARAMS_MISSING: r.json: method cupillar_opt2 has no "
        f"{WORDS[new]}: fab_params.{old} and {new} are both missing. Add both, with "
        f"the same value.")


def test_a_refusal_is_not_an_error_callers_read_as_no_method():
    """Callers catch KeyError, TypeError or ValueError as "no such method" or
    "no manifest"; a pad parameter with no single reading must not look like
    either."""
    assert not issubclass(im.FabParamsRefused, (KeyError, TypeError, ValueError))
    with pytest.raises(KeyError):
        im.fab_params("no_such_method", _one({}))


def test_where_names_the_manifest_or_its_file_name(tmp_path, monkeypatch):
    disagree = {"passiv_opening_um": 40.0, "tm2_enclosure_um": 7.5,
                "passivation_opening_um": 45.0}
    with pytest.raises(im.FabParamsRefused) as given:
        im.fab_params("cupillar_opt2", _one(disagree))
    assert given.value.text.startswith("interconnect_methods.json: method cupillar_opt2 ")

    path = tmp_path / "manifest" / "interconnect_methods.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"schema_version": "1.2", **_one(disagree)}))
    monkeypatch.setenv("INTERCONNECT_PDK_ROOT", str(tmp_path))
    im.clear_cache()
    try:
        with pytest.raises(im.FabParamsRefused) as found:
            im.fab_params("cupillar_opt2")
    finally:
        im.clear_cache()
    assert found.value.text.startswith(f"{path}: method cupillar_opt2 ")


@pytest.mark.needs_sibling_sources
def test_parity_with_reference():
    """The same readings and the same refusals as chiplet-spec's reference
    reader, which gives the new names only."""
    tp = pytest.importorskip(
        "chiplet_format_io.technology_package",
        reason="chiplet-spec not importable; the cases above are the gate")
    if not hasattr(tp, "method_fab_params"):
        pytest.skip("chiplet-spec's reader predates registry 1.2 (no method_fab_params)")
    assert tp.FAB_PARAMS_RENAMED == im.FAB_PARAMS_RENAMED
    m = im.load_manifest(str(MANIFEST_PATH))
    for mid, method in m["methods"].items():
        ours = im.fab_params(mid, m)
        assert tp.method_fab_params(mid, method, where="r.json") == {
            new: ours[new] for new in im.FAB_PARAMS_RENAMED}, mid
    for new, old in PAIRS:
        for fab_params in ({"passiv_opening_um": 40.0, "tm2_enclosure_um": 7.5, new: 1.0},
                           {k: v for k, v in {"passiv_opening_um": 40.0, "tm2_enclosure_um": 7.5,
                                              new: 1.0}.items() if k != old},
                           {k: v for k, v in {"passiv_opening_um": 40.0,
                                              "tm2_enclosure_um": 7.5}.items() if k != old}):
            ours = _refused(fab_params)
            with pytest.raises(tp.TechnologyPackageError) as theirs:
                tp.method_fab_params("cupillar_opt2", {"fab_params": fab_params}, where="r.json")
            assert str(ours) == str(theirs.value), fab_params
