#!/usr/bin/env bash

set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "usage: $0 <assets-dir> <bundle-dir> [source-commit] [source-branch]" >&2
  exit 1
fi

ASSETS_DIR=$1
BUNDLE_DIR=$2
SOURCE_COMMIT=${3:-local}
SOURCE_BRANCH=${4:-local}

if [[ ! -d "$ASSETS_DIR" ]]; then
  echo "assets directory not found: $ASSETS_DIR" >&2
  exit 1
fi

rm -rf "$BUNDLE_DIR"
mkdir -p "$BUNDLE_DIR"

find "$ASSETS_DIR" -maxdepth 1 \( -name '*.png' -o -name '*.pdf' \) -print0 | while IFS= read -r -d '' file; do
  cp "$file" "$BUNDLE_DIR/"
done

python3 - "$BUNDLE_DIR" "$SOURCE_COMMIT" "$SOURCE_BRANCH" <<'PY'
import json
import pathlib
import subprocess
import sys
from datetime import datetime, timezone

bundle_dir = pathlib.Path(sys.argv[1])
source_commit = sys.argv[2]
source_branch = sys.argv[3]

assets = []
for png_path in sorted(bundle_dir.glob("*.png")):
    pdf_path = png_path.with_suffix(".pdf")
    sips_output = subprocess.run(
        ["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(png_path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    width = height = None
    for line in sips_output.splitlines():
        if "pixelWidth:" in line:
            width = int(line.split(":")[-1].strip())
        if "pixelHeight:" in line:
            height = int(line.split(":")[-1].strip())

    if width is None or height is None:
        raise RuntimeError(f"failed to read image dimensions for {png_path.name}")

    assets.append(
        {
            "name": png_path.stem,
            "png": png_path.name,
            "pdf": pdf_path.name if pdf_path.exists() else None,
            "width": width,
            "height": height,
        }
    )

manifest = {
    "generatedAt": datetime.now(timezone.utc).isoformat(),
    "sourceCommit": source_commit,
    "sourceBranch": source_branch,
    "assetCount": len(assets),
    "assets": assets,
}

(bundle_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

cards = []
for asset in assets:
    cards.append(
        f"""
        <article class="card">
          <h2>{asset["name"]}</h2>
          <img src="{asset["png"]}" width="{asset["width"]}" height="{asset["height"]}" alt="{asset["name"]}">
        </article>
        """.strip()
    )

html = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>OMI Onboarding Sync</title>
    <script src="https://mcp.figma.com/mcp/html-to-design/capture.js" async></script>
    <style>
      :root {{
        color-scheme: dark;
        font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }}
      body {{
        margin: 0;
        padding: 32px;
        background: #111111;
        color: #f5f5f5;
      }}
      header {{
        margin-bottom: 24px;
      }}
      .grid {{
        display: grid;
        gap: 28px;
        grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      }}
      .card {{
        background: #1a1a1a;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 16px;
        overflow: hidden;
      }}
      .card h2 {{
        margin: 0;
        padding: 14px 16px;
        font-size: 14px;
        font-weight: 600;
        letter-spacing: 0.01em;
      }}
      .card img {{
        display: block;
        width: 100%;
        height: auto;
      }}
      code {{
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      }}
    </style>
  </head>
  <body>
    <header>
      <h1>OMI Onboarding Sync</h1>
      <p>Commit <code>{source_commit}</code> from <code>{source_branch}</code></p>
      <p>{len(assets)} onboarding steps, generated {manifest["generatedAt"]}</p>
    </header>
    <section class="grid">
      {"".join(cards)}
    </section>
  </body>
</html>
"""

(bundle_dir / "index.html").write_text(html)
PY
