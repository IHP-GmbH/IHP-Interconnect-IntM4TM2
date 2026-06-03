#!/usr/bin/env python3
"""Tests for bump3d_generator: IHP default bodies, no-cap skip, vendor bodies,
and manifest-method bridge. Requires klayout.db (runs on host)."""

import sys
from pathlib import Path

import pytest

db = pytest.importorskip("klayout.db")

_SCRIPTS = Path(__file__).resolve().parents[1]
_PY = _SCRIPTS.parent / "python"
for p in (str(_SCRIPTS), str(_PY)):
    if p not in sys.path:
        sys.path.insert(0, p)

import bump3d_generator as b3d  # noqa: E402


def _layers_with_shapes(layout, cell):
    found = set()
    for li in layout.layer_indexes():
        if cell.shapes(li).size() > 0:
            info = layout.get_info(li)
            found.add((info.layer, info.datatype))
    return found


def _empty():
    layout = db.Layout()
    layout.dbu = 0.001
    return layout, layout.create_cell("T")


def test_default_ihp_bodies():
    layout, cell = _empty()
    assert b3d.add_3d_bodies(layout, cell, 22.0) == 2
    layers = _layers_with_shapes(layout, cell)
    assert (500, 35) in layers and (501, 35) in layers


def test_no_cap_skips_snag():
    layout, cell = _empty()
    assert b3d.add_3d_bodies(layout, cell, 22.0, with_cap=False) == 1
    layers = _layers_with_shapes(layout, cell)
    assert (500, 35) in layers and (501, 35) not in layers


def test_vendor_bodies():
    layout, cell = _empty()
    bodies = [("VendorXBumpCu", 510, 35), ("VendorXBumpCap", 511, 35)]
    assert b3d.add_3d_bodies(layout, cell, 20.0, bodies=bodies) == 2
    layers = _layers_with_shapes(layout, cell)
    assert (510, 35) in layers and (511, 35) in layers


def test_bodies_for_method_reads_manifest():
    bodies = b3d.bodies_for_method("vendorx_microbump")
    assert {(l, d) for (_, l, d) in bodies} == {(510, 35), (511, 35)}
    cu_bodies = b3d.bodies_for_method("cupillar_opt2")
    assert {(l, d) for (_, l, d) in cu_bodies} == {(500, 35), (501, 35)}
