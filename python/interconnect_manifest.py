#!/usr/bin/env python3
"""
interconnect_manifest.py -- reader API for the interconnect PDK manifest.

Single source of truth for interconnection methods (Cu pillars, solder
bumps, microbumps). Tools across the suite (hyp_to_gds.py, bump_mirror.py,
chiplet_writer.py, the KiCad plugin) import this instead of hardcoding
cupillar_opt1/2/3 tables.

Pure standard library (json + pathlib + os) so it imports cleanly inside
KiCad's bundled Python. No third-party dependencies.

Discovery order for the manifest (when no explicit path is given):
  1. $INTERCONNECT_PDK_ROOT/manifest/interconnect_methods.json
  2. ../manifest/interconnect_methods.json relative to this file
  3. walk parent directories for interconnect_pdk/manifest/interconnect_methods.json
     (locates the sibling repo, mirroring how hyp_to_gds discovers gds_to_kicad)
"""

import json
import os
from collections import OrderedDict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_MANIFEST_NAME = "interconnect_methods.json"
_cache: Dict[str, dict] = {}


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

    here = Path(__file__).resolve().parent
    cand = here.parent / "manifest" / _MANIFEST_NAME
    if cand.exists():
        return cand

    for base in [here, *here.parents]:
        cand = base / "interconnect_pdk" / "manifest" / _MANIFEST_NAME
        if cand.exists():
            return cand
    return None


def load_manifest(path: Optional[str] = None) -> dict:
    """Load and cache the manifest. Raises FileNotFoundError if not found."""
    if path is None:
        found = find_manifest_path()
        if found is None:
            raise FileNotFoundError(
                "interconnect_methods.json not found. Set INTERCONNECT_PDK_ROOT "
                "to the interconnect_pdk repo root, or pass an explicit path."
            )
        path = str(found)
    path = str(path)
    if path not in _cache:
        with open(path, "r") as f:
            _cache[path] = json.load(f)
    return _cache[path]


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
    entry = m["layer_registry"][name]
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
            "layers": method["connection_stack"]["layers"],
        }
    return out


def get_connection_stack(method_id: str, manifest: Optional[dict] = None) -> dict:
    """{description, layers} for one method (used when emitting a single stack)."""
    method = get_method(method_id, manifest)
    return {
        "description": method["description"],
        "layers": method["connection_stack"]["layers"],
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
