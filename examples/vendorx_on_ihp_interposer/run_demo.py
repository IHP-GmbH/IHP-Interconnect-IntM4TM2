#!/usr/bin/env python3
"""
End-to-end demo: VendorX fine-pitch microbump on an IHP interposer.

Same geometry, two interconnect adapters, two verdicts -- proving the bumping
method is swappable while the interposer (IHP) adapter is untouched:

    interconnect.adapter = vendorx_microbump (fine pitch)  -> PASS
    interconnect.adapter = ihp_cupillar      (coarse pitch) -> FAIL (IXN.b/IXN.e)

Synthesizes a GDS with real IHP UBM openings (Passiv:pillar 9/35 AND dfpad:pillar
41/35 -- the region the IHP interposer adapter exposes as chiplet_attachment_input)
plus VendorX 3D bodies (510/511) at 50 um pitch, then runs the ADK assembly DRC
twice with the real ihp_sg13g2_interposer adapter.

Run: python3 run_demo.py
"""

import json
import math
import sys
import tempfile
from pathlib import Path

import klayout.db as db

HERE = Path(__file__).resolve()


def _locate():
    """Find interconnect_pdk root and the ADK runner via sibling search."""
    pdk_root = None
    adk_runner = None
    for base in HERE.parents:
        if pdk_root is None and (base / "scripts" / "bump3d_generator.py").is_file():
            pdk_root = base
        if pdk_root is None and (base / "interconnect_pdk" / "scripts"
                                 / "bump3d_generator.py").is_file():
            pdk_root = base / "interconnect_pdk"
        if adk_runner is None:
            cand = base / "adk" / "klayout" / "drc" / "run_drc.py"
            if cand.is_file():
                adk_runner = cand
    return pdk_root, adk_runner


PDK_ROOT, ADK_RUNNER = _locate()
if PDK_ROOT is None or ADK_RUNNER is None:
    sys.exit("Could not locate interconnect_pdk or the ADK runner (sibling repos).")

sys.path.insert(0, str(PDK_ROOT / "scripts"))
sys.path.insert(0, str(PDK_ROOT / "python"))
sys.path.insert(0, str(ADK_RUNNER.parent))
import bump3d_generator as b3d          # noqa: E402
import interconnect_manifest as im      # noqa: E402
from run_drc import get_rules_with_violations  # noqa: E402

PITCH_UM = 50.0       # fine pitch: OK for vendorx (>=50), too tight for IHP (>=75/80)
OPENING_UM = 35.0     # IHP cu-pillar opening (passes the interposer fab side)


def _circle(r, n=256):
    return [db.DPoint(r * math.cos(2 * math.pi * i / n),
                      r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def build_gds(path):
    layout = db.Layout()
    layout.dbu = 0.001
    top = layout.create_cell("TOP")
    passiv = layout.layer(9, 35)
    dfpad = layout.layer(41, 35)
    recog = layout.layer(99, 35)

    pad = layout.create_cell("PAD")
    r = OPENING_UM / 2.0
    for li in (passiv, dfpad, recog):
        pad.shapes(li).insert(db.DPolygon(_circle(r)))   # IHP UBM opening
    # VendorX 3D bodies (510/511) from the manifest, via the PDK generator.
    bodies = b3d.bodies_for_method("vendorx_microbump")
    b3d.add_3d_bodies(layout, pad, im.body_diameter("vendorx_microbump") / 2.0,
                      bodies=bodies)

    for cx in (100.0, 100.0 + PITCH_UM):
        top.insert(db.DCellInstArray(pad, db.DTrans(db.DVector(cx, 100.0))))
    layout.write(str(path))

    manifest = {
        "schema": "adk-boundary-manifest", "version": "1.0.0",
        "generator": "vendorx_demo", "assembly_gds": Path(path).name,
        "dbu_um": 0.001, "top_cell": "TOP",
        "boundaries": [{
            "instance": "U1", "source_die": "VENDORX_DEMO", "class": "chiplet",
            "polygon_dbu": [[0, 0], [300000, 0], [300000, 300000], [0, 300000]],
        }],
    }
    Path(str(path)[:-4] + ".boundaries.json").write_text(json.dumps(manifest, indent=2))


def run_drc(gds, interconnect_adapter, run_dir):
    import subprocess
    report = run_dir / ("report_%s.lyrdb" % interconnect_adapter)
    cmd = [sys.executable, str(ADK_RUNNER),
           "--path", str(gds),
           "--interposer-adapter", "ihp_sg13g2_interposer",
           "--interconnect-adapter", interconnect_adapter,
           "--report", str(report), "--run_dir", str(run_dir)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if not report.is_file():
        sys.stderr.write(proc.stdout + proc.stderr)
        return None
    return get_rules_with_violations(report)


def main():
    work = Path(tempfile.mkdtemp(prefix="vendorx_demo_"))
    gds = work / "vendorx_demo.gds"
    build_gds(gds)

    print("VendorX fine-pitch microbump on IHP interposer")
    print("  geometry: 2 pads, opening %.0f um, pitch %.0f um, bodies 510/511"
          % (OPENING_UM, PITCH_UM))
    print("  interposer adapter (fixed): ihp_sg13g2_interposer")
    print()

    v_vendor = run_drc(gds, "vendorx_microbump", work)
    v_ihp = run_drc(gds, "ihp_cupillar", work)

    def verdict(v):
        if v is None:
            return "ERROR (no report)"
        return "PASS" if not v else "FAIL %s" % sorted(v)

    print("  interconnect.adapter = vendorx_microbump -> %s" % verdict(v_vendor))
    print("  interconnect.adapter = ihp_cupillar      -> %s" % verdict(v_ihp))
    print()

    ok = (v_vendor == set()) and (v_ihp and v_ihp >= {"IXN.b", "IXN.e"})
    print("DEMO %s: same geometry, the method (adapter) decides the verdict."
          % ("PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
