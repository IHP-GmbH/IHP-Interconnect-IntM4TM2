# VendorX microbump on IHP interposer (demo)

End-to-end proof that the interconnection method is vendor-swappable **without
touching the interposer**.

## What it shows

Two pads at 50 µm pitch on a real IHP interposer (UBM openings `9/35 ∩ 41/35` —
the region the `intm4tm2` adapter exposes as
`chiplet_attachment_input`) with VendorX microbump 3D bodies (`510/511`). The ADK
assembly DRC runs twice over the **same geometry** with the **same interposer
adapter**, changing only `--interconnect-adapter`:

| interconnect.adapter | rule numbers | verdict |
|----------------------|--------------|---------|
| `vendorx_microbump`  | 15 / 50 µm   | PASS    |
| `ihp_cupillar`       | 40 / 80 µm   | FAIL (IXN.b, IXN.e) |

The interposer (IHP) is untouched; the method decides the verdict.

## Run

```
python3 run_demo.py
```

Requires klayout plus the `adk` and `interconnect_pdk` sibling repos.

## In a .chiplet

A design selects the method by declaring, alongside `interposer.adapter`:

```yaml
interconnect:
  adapter: "vendorx_microbump"
```

and on each die `connection: vendorx_microbump`. The orchestrator forwards
`--interconnect-adapter vendorx_microbump` to the ADK DRC; `hyp_to_gds` emits the
`510/511` bodies and the vendorx connection_stack from the manifest. Adding or
swapping a vendor needs **no code change** — only manifest data plus an adapter
file. See `vendorx_demo.chiplet`.
