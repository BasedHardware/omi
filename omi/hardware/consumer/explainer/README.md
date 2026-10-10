# Pendant guide

Source for **How the Omi pendant works**, the visual guide at
[docs.omi.me/doc/hardware/how-the-pendant-works](https://docs.omi.me/doc/hardware/how-the-pendant-works).
It is the on-ramp for new contributors: where audio goes, what's inside, what the light means, the
limits, and how the device fails. Engineering detail lives in the firmware source and in
`docs/doc/hardware/consumer/`.

| File | What it is |
| --- | --- |
| `pendant-guide.src.html` | The page: markup, styles (all scoped under `.pg`) and script |
| `build_explainer.py` | Renders the mainboard from the KiCad sources and writes the outputs |

The build writes these generated outputs. Commit them, and don't edit them by hand:

- `docs/snippets/pendant-guide.jsx`: Mintlify can't serve raw HTML, so the page mounts as a JSX snippet.
- `docs/images/hardware/pendant-guide/board-front.svg` and `board-back.svg`: board renders made with `kicad-cli`.
- `docs/images/hardware/pendant-guide/exploded.jpg`: a copy of the assembly photo.

The page itself is `docs/doc/hardware/how-the-pendant-works.mdx`, which just mounts the snippet.

## Rebuild

Requires KiCad 9+ (`kicad-cli` on PATH). Run from the repo root:

```bash
python3 omi/hardware/consumer/explainer/build_explainer.py --mintlify-docs docs
```

Rebuild when the template changes, or when the mainboard KiCad files change, because part
positions and board art come from `HEAD`.

For a standalone preview, run:

```bash
python3 omi/hardware/consumer/explainer/build_explainer.py -o /tmp/pendant-guide.html
```

To check the docs page itself, run `npx mint dev` in `docs/`.

## Accuracy

Claims are static reads of `omi/firmware/omi/` and the KiCad netlist, checked against the code
on 2026-10-09. Battery and memory figures are labelled estimates. When firmware behaviour
changes, update the matching card. This applies especially to the "connected but not listening"
card and the "planned fix" toggles, which describe unshipped retention work.
