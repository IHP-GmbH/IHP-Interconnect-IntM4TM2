# IHP-Interconnect-IntM4TM2

Interconnection PDK for chiplet-on-interposer assembly. It owns the
**post-fabrication** elements that join a chiplet to an interposer:
Cu pillars, solder bumps, and microbumps.

It is split out of the interposer PDK so the bumping method can come from
**any vendor**, not only IHP. The interposer says *where* attachment lands
(the UBM openings it fabricates); this PDK says *how*, via the 3D bodies, the
connection stacks, and the bump-to-bump pitch/spacing rules.

## Status

> [!WARNING]
> IHP-Interconnect-IntM4TM2 is currently a preview release only!

## What lives here vs. the interposer

| Concern | Owner |
|---|---|
| UBM openings `9/35`, `41/35`, `99/35` (and `/36`); pad-vs-substrate rules (Padc.a/c/d/f) | **interposer** (it fabricates them) |
| 3D bodies `500/501/502` (plus vendor layers `510/511`); connection stacks; assembly-time pitch/spacing rules (`IXN.b` / `IXN.e`) | **interconnect_pdk** (this repo) |

The assembly-time pitch/spacing rules live here as `IXN.b` (spacing) and
`IXN.e` (pitch) because they govern the relationship *between* attachment
points; the pad-vs-substrate rules that constrain a single opening against the
substrate stay on the interposer. The interposer still keeps its own `Padc.b` /
`Padc.e` copies for the standalone cu-pillar pre-DRC in `bump_mirror.py`, so the
rules are mirrored across the split (`Padc.b` <-> `IXN.b`, `Padc.e` <-> `IXN.e`);
`interconnect_rules.json` mirrors the manifest `pitch_rules`, and a test in
`test_manifest.py` guards the two against drift.

## Layout

Follows the IHP Open-PDK directory convention (`libs.tech/<tool>/`,
`libs.ref/`), the same pattern as the sibling interposer repo. The manifest
stays at the root because it is the cross-tool contract of the whole PDK, not
data of one tool.

```
manifest/interconnect_methods.json           Single source of truth (methods -> stacks, layers, rules, adapter)
manifest/schema/                             JSON schema (draft-07) for the manifest; top-level key is schema_version
libs.tech/klayout/python/
    interconnect_manifest.py                 Reader API imported by the tool suite
    bump3d_generator.py                      Draws the 3D bodies (split from the interposer's bump_mirror.py)
libs.tech/klayout/interconnect_tests/        Test suite, pytest (test_manifest.py, test_bump3d_generator.py)
libs.tech/klayout/tech/interconnect.lyp      KLayout layer properties for the 500+ bodies
libs.tech/klayout/tech/drc/rule_decks/       layers_def_3d.drc, bump_pitch.drc, interconnect_rules.json
libs.tech/chiplet_studio/stackup_fragments/  3D stackup YAML fragments concatenated by chiplet-studio,
                                             one per METHOD id (cupillar_opt1/2/3, sbump_sac305, vendorx_microbump).
                                             z_reference: attachment_surface, so z values are relative to the
                                             surface the interposer stackup declares (method-pure). The
                                             ihp_cupillar / ihp_sbump fragments are DEPRECATED adapter-keyed copies.
libs.ref/interconnect_examples/
    vendorx_on_intm4tm2/                     Second-vendor (non-IHP) end-to-end demo
```

## How the suite consumes it

Tools add `<this repo>/libs.tech/klayout/python/` to `sys.path`, import
`interconnect_manifest`, and resolve a method id (for example `cupillar_opt2`)
instead of hardcoding the bump table:

```python
import interconnect_manifest as im
lib = im.get_connection_library()          # ordered default bump library for .chiplet emission
bodies = im.layers_3d("cupillar_opt2")     # [(name, gds_layer, gds_datatype), ...]
rules = im.pitch_rules("vendorx_microbump")  # {"IXN_spacing": ..., "IXN_pitch": ...}
```

Discovery of the manifest, when no explicit path is given, follows three tiers
(see `find_manifest_path()`):

1. `$INTERCONNECT_PDK_ROOT/manifest/interconnect_methods.json`
2. the repo's own `manifest/`, three levels up from the Python module
3. a parent-directory walk for a sibling checkout named `interconnect_pdk/` or
   `IHP-Interconnect-IntM4TM2/`, holding `manifest/`

The sibling walk accepts both the canonical name `interconnect_pdk/` and the
default clone name `IHP-Interconnect-IntM4TM2/`, matching the interposer's
`bump_mirror._get_bump3d` discovery, so a default clone resolves without a
rename. `INTERCONNECT_PDK_ROOT` still takes precedence:

```bash
git clone git@github.com:IHP-GmbH/IHP-Interconnect-IntM4TM2.git
export INTERCONNECT_PDK_ROOT="$PWD/IHP-Interconnect-IntM4TM2"
```

## Methods

The default connection library is `cupillar_opt1`, `cupillar_opt2`,
`cupillar_opt3`, and `sbump_sac305` (all PacTech / IHP); the default method is
`cupillar_opt2`. `vendorx_microbump` is a fictional non-IHP fine-pitch
microbump that is defined but deliberately excluded from the default library; it
demonstrates that the method is swappable on the same IHP 130-nm IntM4TM2
aluminum BEOL interposer.

| Method id | Vendor | 3D bodies | In default library |
|---|---|---|---|
| `cupillar_opt1` | PacTech (IHP) | CuPillar `500/35`, SnAgCap `501/35` | yes |
| `cupillar_opt2` | PacTech (IHP) | CuPillar `500/35`, SnAgCap `501/35` | yes (default method) |
| `cupillar_opt3` | PacTech (IHP) | CuPillar `500/35`, SnAgCap `501/35` | yes |
| `sbump_sac305` | PacTech (IHP) | SolderBall `502/36` | yes |
| `vendorx_microbump` | 'VendorX' (DEMO / non-IHP) | VendorXBumpCu `510/35`, VendorXBumpCap `511/35` | no |

## ADK relationship

The assembly DRC is interposer-agnostic and checks the *method* via a second
adapter axis. Each method names an `adapter` in the manifest, and the ADK looks
up `adk/pdk_adapters/interconnect/<adapter>.drc` (the manifest `adapter` field,
not the method id) for the pitch/spacing parameters; the ADK deck then applies
them over the abstract attachment region the interposer adapter exposes.

The shipped adapters are `ihp_cupillar.drc`, `ihp_sbump.drc`, and
`vendorx_microbump.drc`. The three `cupillar_opt*` methods all map to the
`ihp_cupillar` adapter and `sbump_sac305` maps to `ihp_sbump`, so the adapter
set is smaller than the method set. See `adk/docs/architecture.md`.
