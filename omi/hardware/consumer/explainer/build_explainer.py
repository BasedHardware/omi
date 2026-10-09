#!/usr/bin/env python3
"""Build the "How the Omi pendant works" guide from the KiCad sources in this repo.

Reads the hardware files from a git ref (never from a checkout), renders each
mainboard layer with kicad-cli, extracts part positions, and fills the template.

  python3 omi/hardware/consumer/explainer/build_explainer.py --mintlify-docs docs   # what ships to docs.omi.me
  python3 omi/hardware/consumer/explainer/build_explainer.py -o /tmp/pendant-guide.html  # standalone preview

Run it again whenever the mainboard KiCad files or the template change, and commit the outputs.

Requires kicad-cli (KiCad 9+) on PATH.
"""
import argparse, base64, csv, json, pathlib, re, subprocess, sys, tempfile, zipfile

HERE = pathlib.Path(__file__).resolve().parent
MAIN_ZIP = "omi/hardware/consumer/electrical/mainboard/altium/omi2-mainboard-v1.2-altium.zip"
EXPLODED = "omi/hardware/consumer/assembly/photos/materials-labelled-exploded-view.jpg"
KEY_PARTS = set("U1 U2 U3 U4 U5 U6 U7 U8 U9 U10 U11 U12 U13 U14 U15 U16 MIC1 MIC2 J1 K2 "
                "D1 D2 D3 D4 D7 Q1 Q2 Q7 X1 X2 X3 PP1 PP2 PP3 PP4 PP5 PP6".split())


def git_blob(repo, ref, path):
    return subprocess.run(["git", "-C", repo, "show", f"{ref}:{path}"], check=True, capture_output=True).stdout


def kicad(*args):
    subprocess.run(["kicad-cli", *args], check=True, capture_output=True)


def layer_fragment(svg_path, cls):
    t = pathlib.Path(svg_path).read_text()
    b = t[t.index("<g"):t.rindex("</svg>")]
    b = re.sub(r"fill:#FFFFFF", "fill:var(--pcb-hole)", b, flags=re.I)
    b = re.sub(r"(fill|stroke):#[0-9A-Fa-f]{6}", r"\1:currentColor", b)
    b = re.sub(r"(\d+\.\d{3})\d+", r"\1", b)
    b = re.sub(r"\s*\n\s*", " ", b)
    return f'<g class="ly {cls}">{b}</g>'


def edge_origin(pcb_text):
    """Board is a 21 mm circle; KiCad's board-area SVG origin is its bounding box corner."""
    arcs = []
    for block in pcb_text.split("(gr_arc")[1:]:
        block = block[:block.find("(uuid")]
        m = re.search(r'\(start ([-\d.]+) ([-\d.]+)\)\s*\(mid ([-\d.]+) ([-\d.]+)\)\s*\(end ([-\d.]+) ([-\d.]+)\)', block)
        if m and '(layer "Edge.Cuts")' in block:
            arcs.append(m.groups())
    best = None
    for a in arcs:
        (x1, y1, x2, y2, x3, y3) = map(float, a)
        d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
        if abs(d) < 1e-9:
            continue
        ux = ((x1**2 + y1**2) * (y2 - y3) + (x2**2 + y2**2) * (y3 - y1) + (x3**2 + y3**2) * (y1 - y2)) / d
        uy = ((x1**2 + y1**2) * (x3 - x2) + (x2**2 + y2**2) * (x1 - x3) + (x3**2 + y3**2) * (x2 - x1)) / d
        r = ((x1 - ux) ** 2 + (y1 - uy) ** 2) ** .5
        if best is None or r > best[2]:
            best = (ux, uy, r)
    cx, cy, r = best
    half = 20.9804 / 2  # SVG viewBox width reported by kicad-cli for this board
    return cx - half, cy - half


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=str(HERE.parents[3]))
    ap.add_argument("--ref", default="HEAD")
    ap.add_argument("--fragment", action="store_true", help="omit the document skeleton (for hosts that add their own)")
    ap.add_argument("--mintlify-docs", metavar="DOCS_DIR",
                    help="write a Mintlify JSX snippet plus image assets into DOCS_DIR (the repo's docs/)")
    ap.add_argument("-o", "--out")
    a = ap.parse_args()
    a.out = a.out or str(HERE / "pendant-guide.html")

    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        (td / "main.zip").write_bytes(git_blob(a.repo, a.ref, MAIN_ZIP))
        zipfile.ZipFile(td / "main.zip").extractall(td / "main")
        pcb = next(p for p in (td / "main").rglob("OMI.kicad_pcb") if "__MACOSX" not in str(p))
        for layer in ["F.Cu", "B.Cu", "In1.Cu", "F.Silkscreen", "B.Silkscreen", "Edge.Cuts", "F.Mask", "B.Mask"]:
            kicad("pcb", "export", "svg", str(pcb), "--mode-single", "-l", layer, "--page-size-mode", "2",
                  "--exclude-drawing-sheet", "-o", str(td / f"{layer}.svg"))
        kicad("pcb", "export", "pos", str(pcb), "--format", "csv", "--units", "mm", "--side", "both",
              "-o", str(td / "pos.csv"))
        top = "".join(layer_fragment(td / f"{l}.svg", c) for l, c in
                      [("F.Mask", "mask"), ("In1.Cu", "inner"), ("F.Cu", "cu"), ("F.Silkscreen", "silk"), ("Edge.Cuts", "edge")])
        bot = "".join(layer_fragment(td / f"{l}.svg", c) for l, c in
                      [("B.Mask", "mask"), ("B.Cu", "cu"), ("B.Silkscreen", "silk"), ("Edge.Cuts", "edge")])
        ox, oy = edge_origin(pcb.read_text())
        parts = {}
        for r in csv.DictReader(open(td / "pos.csv")):
            if r["Ref"] in KEY_PARTS:
                parts[r["Ref"]] = [round(float(r["PosX"]) - ox, 3), round(-float(r["PosY"]) - oy, 3), r["Side"][0]]

    img = base64.b64encode(git_blob(a.repo, a.ref, EXPLODED)).decode()
    a._top, a._bot = top, bot
    html = (HERE / "pendant-guide.src.html").read_text()
    html = (html.replace("{{TOP}}", top).replace("{{BOT}}", bot)
                .replace("{{PARTS}}", json.dumps(parts)).replace("{{EXPLODED}}", "data:image/jpeg;base64," + img))
    return finish(a, html)


BOARD_STYLE = (".ly.mask{color:#16302a}.ly.cu{color:#c88a4a;opacity:.38}.ly.inner{display:none}"
               ".ly.silk{color:#f4f1e4}.ly.edge{color:#f4f1e4;opacity:.7}")


def board_svg(fragment, mirror):
    body = f'<g transform="translate(20.98 0) scale(-1 1)">{fragment}</g>' if mirror else fragment
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="-0.3 -0.3 21.6 21.6" width="216" height="216">'
            f'<style>{BOARD_STYLE}:root{{--pcb-hole:#1d3a2f}}</style>'
            f'<circle cx="10.49" cy="10.49" r="10.5" fill="#1d3a2f"/>{body}</svg>')


def write_mintlify(a, html):
    """Emit docs/snippets/pendant-guide.jsx and its static images for the Mintlify site.

    Mintlify does not serve raw .html, so the page mounts as a JSX snippet: the markup is
    injected once and the page script runs in useEffect. Board renders become static SVGs
    referenced through <image>, keeping the snippet small.
    """
    docs = pathlib.Path(a.mintlify_docs)
    img_dir = docs / "images" / "hardware" / "pendant-guide"
    img_dir.mkdir(parents=True, exist_ok=True)
    (img_dir / "board-front.svg").write_text(board_svg(a._top, False))
    (img_dir / "board-back.svg").write_text(board_svg(a._bot, True))
    (img_dir / "exploded.jpg").write_bytes(git_blob(a.repo, a.ref, EXPLODED))
    base = "/images/hardware/pendant-guide/"
    html = re.sub(r'<symbol id="board-top"[^>]*>.*?</symbol>',
                  f'<symbol id="board-top" viewBox="-0.3 -0.3 21.6 21.6"><image href="{base}board-front.svg" x="-0.3" y="-0.3" width="21.6" height="21.6"/></symbol>',
                  html, count=1, flags=re.S)
    html = re.sub(r'<symbol id="board-bot"[^>]*>.*?</symbol>',
                  f'<symbol id="board-bot" viewBox="-0.3 -0.3 21.6 21.6"><image href="{base}board-back.svg" x="-0.3" y="-0.3" width="21.6" height="21.6"/></symbol>',
                  html, count=1, flags=re.S)
    html = re.sub(r'data:image/jpeg;base64,[A-Za-z0-9+/=]+', base + "exploded.jpg", html)
    # Mintlify owns the page title, metadata, ground and theme switch (html.dark).
    html = re.sub(r"<title>.*?</title>\s*<meta name=\"description\"[^>]*>", "", html, flags=re.S)
    html = re.sub(r"<header>.*?</header>", "", html, count=1, flags=re.S)
    html = re.sub(r'@media \(prefers-color-scheme: dark\)\{html:not\(\[data-theme="light"\]\) \.pg[^{]*\{[^}]*\}\}', "", html)
    html = re.sub(r"/\* page ground for standalone hosting.*?\.pg\{min-height:100%\}", "", html, flags=re.S)
    m = re.search(r"<script>(.*)</script>", html, flags=re.S)
    script, markup = m.group(1), html[:m.start()] + html[m.end():]
    jsx = (
        "// Generated by omi/hardware/consumer/explainer/build_explainer.py "
        "(--mintlify-docs docs). Edit the template and rebuild; do not edit by hand.\n"
        "export const PendantGuide = () => {\n"
        f"  const html = {json.dumps(markup)};\n"
        "  useEffect(() => {\n"
        "    let stopped = false;\n"
        "    const requestAnimationFrame = (f) => (stopped ? 0 : window.requestAnimationFrame(f));\n"
        f"{script}\n"
        "    return () => { stopped = true; };\n"
        "  }, []);\n"
        "  return <div dangerouslySetInnerHTML={{ __html: html }} />;\n"
        "};\n")
    snip = docs / "snippets"
    snip.mkdir(exist_ok=True)
    (snip / "pendant-guide.jsx").write_text(jsx)
    print(f"wrote {snip / 'pendant-guide.jsx'} ({len(jsx)//1024} KB) and images in {img_dir}")


def finish(a, html):
    if a.mintlify_docs:
        return write_mintlify(a, html)
    if not a.fragment:
        html = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                + html.replace("</style>", "</style>\n</head>\n<body>", 1) + "\n</body>\n</html>\n")
    pathlib.Path(a.out).write_text(html)
    print(f"wrote {a.out} ({len(html)//1024} KB)")


if __name__ == "__main__":
    sys.exit(main())
