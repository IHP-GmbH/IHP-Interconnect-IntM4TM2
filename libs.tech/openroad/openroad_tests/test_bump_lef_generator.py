#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 IHP GmbH
"""Tests for the per-method bump LEF generator."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "python"))
sys.path.insert(0, str(HERE.parents[2] / "klayout" / "python"))

import interconnect_manifest  # noqa: E402
from bump_lef_generator import (  # noqa: E402
    bump_macro_name, render_bump_lef, write_bump_lef)


def test_macro_name_is_deterministic():
    assert bump_macro_name("cupillar_opt1") == "BUMP_CUPILLAR_OPT1"
    assert bump_macro_name("vendorx_microbump") == "BUMP_VENDORX_MICROBUMP"


def test_every_manifest_method_renders():
    for method_id in interconnect_manifest.list_methods():
        text = render_bump_lef(method_id, "TopMetal2")
        diameter = interconnect_manifest.body_diameter(method_id)
        d = ("%.6f" % diameter).rstrip("0").rstrip(".")
        assert "MACRO %s" % bump_macro_name(method_id) in text
        assert "CLASS COVER BUMP ;" in text
        assert "SIZE %s BY %s ;" % (d, d) in text
        assert "LAYER TopMetal2 ;" in text
        assert "RECT 0 0 %s %s ;" % (d, d) in text
        assert text.endswith("END LIBRARY\n")


def test_layer_name_is_verbatim():
    text = render_bump_lef("cupillar_opt1", "metal5")
    assert "LAYER metal5 ;" in text
    assert "TopMetal2" not in text


def test_macro_name_override():
    text = render_bump_lef("cupillar_opt1", "TopMetal2", macro_name="BUMP")
    assert "MACRO BUMP\n" in text
    assert "END BUMP\n" in text


def test_unknown_method_raises():
    try:
        render_bump_lef("no_such_method", "TopMetal2")
    except Exception:
        pass
    else:
        raise AssertionError("unknown method id must raise")


def test_empty_layer_raises():
    try:
        render_bump_lef("cupillar_opt1", "")
    except ValueError:
        pass
    else:
        raise AssertionError("empty layer_name must raise")


def test_write_bump_lef(tmp_path=None):
    import tempfile
    base = Path(tempfile.mkdtemp()) if tmp_path is None else tmp_path
    out = write_bump_lef("sbump_sac305", "TopMetal2",
                         base / "sbump_sac305__demo.lef")
    assert out.is_file()
    assert "SIZE 80 BY 80 ;" in out.read_text()


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS %s" % name)
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print("FAIL %s: %s" % (name, exc))
    raise SystemExit(1 if failures else 0)
