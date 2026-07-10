#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 IHP GmbH
"""Per-method bump LEF generator for OpenROAD multi-die flows.

Renders a minimal LEF ``MACRO`` (``CLASS COVER BUMP``) for one interconnect
method, sized from the method manifest (``body_diameter_um``). The manifest
stays the single source of truth for the numbers; the caller supplies the
name of the routing layer the pad PORT sits on, because the layer name
belongs to the *consumer's* technology: OpenROAD requires a bump master's
library to live in the same technology object as the chip that instantiates
it, so the same method renders against a different layer name per die
technology. No static LEF files ship with this PDK for the same reason.

Callers are responsible for writing the rendered text to a filename that is
unique per (method, consumer technology): OpenROAD dedupes LEF libraries
globally by filename, so reusing one filename across technologies binds the
library to whichever technology loaded it first.

Typical use::

    from bump_lef_generator import bump_macro_name, render_bump_lef
    lef_text = render_bump_lef("cupillar_opt1", "TopMetal2")

Runs inside any Python (stdlib + the sibling manifest reader only).
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_MANIFEST_PYTHON = _HERE.parents[2] / "klayout" / "python"
if str(_MANIFEST_PYTHON) not in sys.path:
    sys.path.insert(0, str(_MANIFEST_PYTHON))

import interconnect_manifest  # noqa: E402

__all__ = ["bump_macro_name", "render_bump_lef", "write_bump_lef"]


def bump_macro_name(method_id: str) -> str:
    """Deterministic LEF macro name for a method (also the .bmap cell type)."""
    return "BUMP_%s" % method_id.upper()


def _fnum(value: float) -> str:
    text = ("%.6f" % float(value)).rstrip("0").rstrip(".")
    return text if text else "0"


def render_bump_lef(method_id: str, layer_name: str, *,
                    macro_name: str = None, manifest=None) -> str:
    """Render the bump macro LEF for ``method_id`` on ``layer_name``.

    ``layer_name`` must exist as a routing layer in the technology the LEF
    will be loaded into. ``macro_name`` overrides :func:`bump_macro_name`.
    """
    if not layer_name:
        raise ValueError("layer_name is required (consumer technology layer)")
    method = interconnect_manifest.get_method(method_id)  # raises on unknown
    del method  # existence check; the diameter accessor re-reads the manifest
    diameter = _fnum(interconnect_manifest.body_diameter(method_id))
    macro = macro_name or bump_macro_name(method_id)
    return (
        "# Bump macro for interconnect method %s (body diameter %s um);\n"
        "# generated from the interconnect_pdk manifest, do not edit.\n"
        "VERSION 5.8 ;\n"
        "BUSBITCHARS \"[]\" ;\n"
        "DIVIDERCHAR \"/\" ;\n"
        "MACRO %s\n"
        "  CLASS COVER BUMP ;\n"
        "  ORIGIN 0 0 ;\n"
        "  SIZE %s BY %s ;\n"
        "  SYMMETRY X Y R90 ;\n"
        "  PIN PAD\n"
        "    DIRECTION INOUT ;\n"
        "    USE SIGNAL ;\n"
        "    PORT\n"
        "      LAYER %s ;\n"
        "        RECT 0 0 %s %s ;\n"
        "    END\n"
        "  END PAD\n"
        "END %s\n"
        "END LIBRARY\n"
        % (method_id, diameter, macro, diameter, diameter, layer_name,
           diameter, diameter, macro)
    )


def write_bump_lef(method_id: str, layer_name: str, path, *,
                   macro_name: str = None) -> Path:
    """Write the rendered LEF to ``path`` and return it."""
    path = Path(path)
    path.write_text(render_bump_lef(method_id, layer_name,
                                    macro_name=macro_name), encoding="utf-8")
    return path


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Render a per-method bump LEF from the interconnect "
                    "manifest.")
    parser.add_argument("method_id", help="interconnect method id")
    parser.add_argument("layer_name",
                        help="routing layer name in the consumer technology")
    parser.add_argument("--out", default=None,
                        help="output file (default: stdout)")
    args = parser.parse_args(argv)
    text = render_bump_lef(args.method_id, args.layer_name)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(args.out)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
