#!/usr/bin/env python3
"""Pair before/ and after/ captures into INDEX.md and a static gallery.html; never redraws a PNG.

Usage: write_gallery.py OUT_DIR --command "..." [--base-sha SHA] --head-sha SHA
Each side directory holds scenarios.json (what was asked for), frames.json (what was captured),
source.json (the revision) and the PNGs. A scenario asked for but not captured is marked failed.
"""
import argparse
import html
import json
from pathlib import Path

SIDES = ('before', 'after')


def load(path: Path, default):
    return json.loads(path.read_text()) if path.exists() else default


def side_data(out: Path, side: str) -> dict | None:
    root = out / side
    if not root.is_dir():
        return None
    frames = load(root / 'frames.json', [])
    return {
        'source': load(root / 'source.json', {}),
        'scenarios': load(root / 'scenarios.json', []),
        'frames': {f['file']: f for f in frames},
        'times': sorted(f['captured_at'] for f in frames),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('out')
    parser.add_argument('--command', required=True)
    args = parser.parse_args()
    out = Path(args.out)
    sides = {side: data for side in SIDES if (data := side_data(out, side))}

    scenarios: dict[str, dict] = {}
    for data in sides.values():
        for scenario in data['scenarios']:
            scenarios.setdefault(scenario['id'], scenario)
    files: dict[str, list[str]] = {sid: [] for sid in scenarios}
    for data in sides.values():
        for name, frame in data['frames'].items():
            bucket = files.setdefault(frame['scenario'], [])
            if name not in bucket:
                bucket.append(name)

    md = ['# Visual audit', '', f'Command: `{args.command}`', '']
    md += ['| Side | Revision | Commit | Captured (UTC) | Scenarios captured |', '| --- | --- | --- | --- | --- |']
    for side, data in sides.items():
        src, times = data['source'], data['times']
        captured = {f['scenario'] for f in data['frames'].values()}
        span = f'{times[0]} to {times[-1]}' if times else 'nothing captured'
        md.append(f"| {side} | `{src.get('rev', '?')}` | `{src.get('sha', '?')}` | {span} | "
                  f'{len(captured)} of {len(data["scenarios"])} |')
    md += ['', 'Screenshots stay outside Git. Headless widget captures of production pages with synthetic',
           'local state at 390x844 logical px, 2x; not an installed app (see app/e2e/SKILL.md, "Visual audit").', '']

    cards = []
    for sid, scenario in scenarios.items():
        md += [f"## {sid}: {scenario['title']}", '', f"Page: `{scenario['page']}`. State: {scenario['state']}", '']
        rows = []
        for name in sorted(files.get(sid, [])):
            cells, line = [], []
            for side, data in sides.items():
                frame = data['frames'].get(name)
                line.append(f'`{side}/{name}`' if frame else f'{side}: not captured')
                if frame:
                    cells.append(f'<figure><figcaption>{side}</figcaption><a href="{side}/{html.escape(name)}">'
                                 f'<img loading="lazy" src="{side}/{html.escape(name)}" alt="{side} {html.escape(name)}">'
                                 '</a></figure>')
                else:
                    cells.append(f'<figure class="missing"><figcaption>{side}</figcaption><p>Not captured</p></figure>')
            action = next(d['frames'][name]['action'] for d in sides.values() if name in d['frames'])
            md.append(f'- {action}: ' + ' · '.join(line))
            rows.append(f'<div class="step"><h3>{html.escape(action)}</h3><div class="pair">{"".join(cells)}</div></div>')
        failed = [side for side, data in sides.items()
                  if any(s['id'] == sid for s in data['scenarios'])
                  and not any(f['scenario'] == sid for f in data['frames'].values())]
        if failed:
            md.append(f"- Failed on {', '.join(failed)}: see {', '.join(f'{s}/capture.log' for s in failed)}")
        md.append('')
        warn = f'<p class="warn">Failed on {", ".join(failed)} (see capture.log)</p>' if failed else ''
        cards.append(f'<section id="{html.escape(sid)}"><h2>{html.escape(scenario["title"])} <code>{html.escape(sid)}</code></h2>'
                     f'<p class="meta">{html.escape(scenario["page"])}. {html.escape(scenario["state"])}</p>{warn}'
                     + ''.join(rows) + '</section>')
    (out / 'INDEX.md').write_text('\n'.join(md))

    heads = ''.join(
        f"<li><b>{side}</b> <code>{html.escape(str(d['source'].get('sha', '?')))}</code> "
        f"({html.escape(str(d['source'].get('rev', '?')))}), captured {html.escape(d['times'][0] if d['times'] else 'nothing')}</li>"
        for side, d in sides.items())
    (out / 'gallery.html').write_text(f'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Visual audit</title>
<style>body{{background:#101014;color:#f5f5f7;font:15px system-ui;margin:24px auto;max-width:1100px;padding:0 16px}}
code{{color:#b8b8c4}}.meta{{color:#b8b8c4}}.warn{{color:#ff8a80}}section{{border-top:1px solid #2a2a33;padding:8px 0 24px}}
h3{{font-size:14px;font-weight:500;color:#d8d8e0}}.pair{{display:flex;gap:16px;flex-wrap:wrap}}
figure{{margin:0;flex:1 1 300px;max-width:390px}}figcaption{{color:#b8b8c4;margin-bottom:6px}}
img{{width:100%;display:block;border-radius:12px}}.missing p{{padding:40px;background:#202026;border-radius:12px}}</style>
<h1>Visual audit</h1><ul>{heads}</ul><p class="meta">{html.escape(args.command)}</p>
<p class="meta">Production Flutter widgets with synthetic local state, 390×844 logical px at 2×. Headless captures,
not an installed app: no native keyboard, status bar, permissions dialogs or screen reader.</p>
{''.join(cards)}</html>''')
    print(out / 'INDEX.md')
    print(out / 'gallery.html')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
