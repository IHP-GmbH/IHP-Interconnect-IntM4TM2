#!/usr/bin/env python3
"""
bump3d_generator.py -- 3D interconnect body generator.

Owns the post-passivation 3D bodies (CuPillar 500/35, SnAgCap 501/35, vendor
bodies 510+, ...) that were split out of the interposer's bump_mirror.py. The
fab pad openings (9/35, 41/35, ...) stay with the interposer; this module draws
ONLY the 3D visualization/simulation volumes.

Generic by design: callers pass the bodies to draw as (name, gds_layer,
gds_datatype) tuples, so the same code renders IHP cu-pillars or any vendor's
microbump. The default is the IHP cu-pillar stack, so bump_mirror.py reproduces
its pre-split output byte-for-byte.
"""

import math

try:
    import klayout.db as db
except ImportError:
    db = None


# IHP cu-pillar default bodies. Mirrors the manifest layer_registry entries for
# the IHP methods; kept here so the generator works standalone (no manifest
# import needed for the common case).
IHP_CUPILLAR_3D_LAYERS = (
    ("CuPillar:pillar", 500, 35),
    ("SnAgCap:pillar", 501, 35),
)


def _make_circle(radius, num_points=256):
    return [db.DPoint(radius * math.cos(2 * math.pi * i / num_points),
                      radius * math.sin(2 * math.pi * i / num_points))
            for i in range(num_points)]


def _is_cap(name):
    """A 'cap' body (solder cap) is skipped for wafer-level (no-cap) test."""
    return "Cap" in name or "SnAg" in name


def add_3d_bodies(layout, cell, body_radius_um, bodies=None,
                  with_cap=True, num_points=256):
    """Insert 3D interconnect bodies into ``cell`` as circles of body_radius_um.

    Args:
        layout:        klayout db.Layout the cell belongs to.
        cell:          db.Cell to receive the body shapes.
        body_radius_um: radius of each body circle (um).
        bodies:        iterable of (name, gds_layer, gds_datatype). Defaults to
                       the IHP cu-pillar bodies.
        with_cap:      if False, cap bodies are skipped (wafer-level test).
        num_points:    circle discretization.

    Returns:
        Number of bodies drawn.
    """
    if db is None:
        raise ImportError("klayout package required for 3D body generation.")
    if bodies is None:
        bodies = IHP_CUPILLAR_3D_LAYERS

    drawn = 0
    for name, layer_num, datatype in bodies:
        if not with_cap and _is_cap(name):
            continue
        layer_idx = layout.layer(layer_num, datatype)
        cell.shapes(layer_idx).insert(
            db.DPolygon(_make_circle(body_radius_um, num_points)))
        drawn += 1
    return drawn


def bodies_for_method(method_id, manifest=None):
    """Return [(name, gds_layer, gds_datatype), ...] for a manifest method.

    Convenience bridge for callers that select a method by id (e.g. a vendor
    microbump). Imports the manifest reader lazily so this module has no hard
    dependency on it for the default IHP path.
    """
    import interconnect_manifest as im
    return im.layers_3d(method_id, manifest)
