#!/usr/bin/env python3
"""Package original captures into a browsable gallery; never redraw screenshots."""
import html
import json
import os
from pathlib import Path

output = Path(os.environ['OMI_AUDIT_OUTPUT'])
frames = json.loads((output / 'frames.json').read_text())
cards = ''.join(
    '<figure><a href="{file}"><img loading="lazy" src="{file}" alt="{action}"></a>'
    '<figcaption>{action}<small>{file}</small></figcaption></figure>'.format(
        file=html.escape(frame['file'], quote=True), action=html.escape(frame['action'], quote=True)
    ) for frame in frames
)
(output / 'index.html').write_text('''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Mobile UI captures</title>
<style>body{background:#101014;color:#f5f5f7;font:16px system-ui;margin:32px}
h1{font-size:28px}p{max-width:850px;color:#b8b8c4;line-height:1.6}
main{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:24px}
figure{margin:0;background:#202026;border-radius:16px;overflow:hidden}img{width:100%;display:block}
figcaption{padding:16px;line-height:1.5}small{display:block;color:#b8b8c4;margin-top:8px}</style>
<h1>Mobile UI captures</h1><p>Real production Flutter widgets, driven through taps and text entry.
Synthetic local account and loopback backend, English dark theme, 390×844 logical pixels.
These are headless widget captures, not an installed phone app. Native keyboard, physical haptics,
platform permissions and screen-reader behavior require device verification. Tap any image for the original PNG.</p>
<main>''' + cards + '</main></html>')
