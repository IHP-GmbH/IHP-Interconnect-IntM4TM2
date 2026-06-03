# interconnect_pdk

Interconnection PDK for chiplet-on-interposer assembly. Owns the
**post-fabrication** elements that join a chiplet to an interposer:
Cu pillars, solder bumps, microbumps.

Split out of the interposer PDK so the bumping method can come from **any
vendor**, not only IHP. The interposer says *where* attachment lands (the
UBM openings it fabricates); this PDK says *how* — the 3D bodies, the
connection stacks, and the bump-to-bump pitch/spacing rules.

## What lives here vs. the interposer

| Concern | Owner |
|---|---|
| UBM openings `9/35`, `41/35`, `99/35` (+ `/36`); pad-vs-substrate rules (Padc.a/c/d/f) | **interposer** (it fabricates them) |
| 3D bodies `500/501/502` (+ vendor layers); connection stacks; pitch/spacing rules (Padc.b/e) | **interconnect_pdk** (this repo) |

## Layout

```
manifest/interconnect_methods.json   Single source of truth (methods -> stacks, layers, rules, adapter)
manifest/schema/                     JSON schema for the manifest
python/interconnect_manifest.py      Reader API imported by the tool suite
tech/interconnect.lyp                KLayout layer properties for 500+ bodies
tech/drc/rule_decks/                 layers_def_3d.drc, bump_pitch.drc, interconnect_rules.json
config/stackup_fragments/            3D stackup YAML fragments concatenated by chiplet-studio
scripts/bump3d_generator.py          Generates the 3D bodies (split from interposer bump_mirror.py)
examples/vendorx_on_ihp_interposer/  2nd-vendor (non-IHP) end-to-end demo
```

## How the suite consumes it

Tools import `interconnect_manifest` and resolve a method id (e.g.
`cupillar_opt2`) instead of hardcoding the bump table:

```python
import interconnect_manifest as im
lib = im.get_connection_library()          # ordered default bump library for .chiplet emission
bodies = im.layers_3d("cupillar_opt2")     # [(name, gds_layer, gds_datatype), ...]
rules = im.pitch_rules("vendorx_microbump")
```

Discovery: tools add `interconnect_pdk/python/` to `sys.path`. The manifest
is located via `$INTERCONNECT_PDK_ROOT`, a path relative to the module, or a
sibling-repo search.

## Methods

`cupillar_opt1/2/3`, `sbump_sac305` (IHP/PacTech, default library), and
`vendorx_microbump` (a fictional non-IHP fine-pitch microbump demonstrating
that the method is swappable on the same IHP interposer).

## ADK relationship

The assembly DRC (interposer-agnostic) checks the *method* via a second
adapter axis: `adk/pdk_adapters/interconnect/<method>.drc` supplies the
pitch/spacing parameters; the ADK deck applies them over the abstract
attachment region the interposer adapter exposes. See
`adk/docs/architecture.md`.
