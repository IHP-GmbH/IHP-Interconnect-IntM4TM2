# IHP-Interconnect-IntM4TM2

The interconnect PDK for chiplet-on-interposer assembly in the IHP Open ADK flow. It holds
the post-fabrication elements that join a chiplet to the IHP IntM4TM2 interposer (Cu
pillars, solder bumps and microbumps) as a method registry that the assembly tools, the 3D
view and the assembly DRC read, so the bumping method can change without touching the
interposer PDK.

IHP applies the same methods, with the same parameters, to IHP SG13G2 and IHP SG13CMOS5L
dies; each method lists the die processes it attaches as `die_processes`.

## Use

It runs in the ADK-Tools image. The container page,
https://ihp-open-adk-docs.readthedocs.io/en/latest/install/01_container.html, says how to get
the image and open a shell in it. In that shell:

```bash
/opt/adk-tools/venv/bin/python3 \
    "$INTERCONNECT_PDK_ROOT/libs.tech/openroad/python/bump_lef_generator.py" \
    cupillar_opt1 TopMetal2
```

This renders the OpenROAD bump macro of one method against the routing layer of a die
technology; in the image this PDK is `$INTERCONNECT_PDK_ROOT`.

## Documentation

The full documentation is at
https://ihp-open-adk-docs.readthedocs.io/en/latest/tools/06_interconnect_pdk.html

## Release

Released as part of the IHP Open ADK. The release page lists the commit of every
repository in each release:
https://ihp-open-adk-docs.readthedocs.io/en/latest/install/00_release.html

## License

Apache-2.0. See `LICENSE`.
