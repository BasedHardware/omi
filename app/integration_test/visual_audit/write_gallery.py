#!/usr/bin/env python3
"""Pair before/ and after/ captures into INDEX.md and a static gallery.html; never redraws a PNG.

Usage: write_gallery.py OUT_DIR --command "..." [--base-sha SHA] --head-sha SHA
Each side directory holds scenarios.json (what that revision's suite was asked for), frames.json
(what was captured), source.json (the revision and suite) and the PNGs. A scenario one side's suite
does not have "did not exist" there; one it has but did not capture "failed".
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
    asked = load(root / 'scenarios.json', [])
    return {
        'source': load(root / 'source.json', {}),
        'scenarios': asked['scenarios'] if isinstance(asked, dict) else asked,
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
    for data in reversed(list(sides.values())):  # the newer side's order and titles first
        for scenario in data['scenarios']:
            scenarios.setdefault(scenario['id'], scenario)
    files: dict[str, list[str]] = {sid: [] for sid in scenarios}
    for data in sides.values():
        for name, frame in data['frames'].items():
            bucket = files.setdefault(frame['scenario'], [])
            if name not in bucket:
                bucket.append(name)

    md = ['# Visual audit', '', f'Command: `{args.command}`', '']
    md += ['| Side | Revision | Commit | Suite | Captured (UTC) | Scenarios captured |',
           '| --- | --- | --- | --- | --- | --- |']
    for side, data in sides.items():
        src, times = data['source'], data['times']
        captured = {f['scenario'] for f in data['frames'].values()}
        span = f'{times[0]} to {times[-1]}' if times else 'nothing captured'
        md.append(f"| {side} | `{src.get('rev', '?')}` | `{src.get('sha', '?')}` | {src.get('suite', 'current')} | {span} | "
                  f'{len(captured)} of {len(data["scenarios"])} |')
    md += ['', 'Screenshots stay outside Git. Headless widget captures of production pages with synthetic',
           'local state at 390x844 logical px, 2x; not an installed app (see app/e2e/SKILL.md, "Visual audit").', '']

    cards = []
    for sid, scenario in scenarios.items():
        has = {side: next((s for s in d['scenarios'] if s['id'] == sid), None) for side, d in sides.items()}
        got = {side: any(f['scenario'] == sid for f in d['frames'].values()) for side, d in sides.items()}
        pages = [f"{side}: `{meta['page']}`" for side, meta in has.items() if meta]
        same_page = len({meta['page'] for meta in has.values() if meta}) == 1
        md += [f"## {sid}: {scenario['title']}", '',
               (f"Page: `{scenario['page']}`" if same_page else 'Page: ' + '; '.join(pages)) + f". State: {scenario['state']}", '']

        def cell(side: str, name: str) -> tuple[str, str]:
            if not has[side]:
                return f'{side}: did not exist', f'<figure class="missing"><figcaption>{side}</figcaption><p>Did not exist at this revision</p></figure>'
            if not got[side]:
                return f'{side}: failed', f'<figure class="missing"><figcaption>{side}</figcaption><p class="warn">Failed (see {side}/capture.log)</p></figure>'
            if name not in sides[side]['frames']:
                return f'{side}: no equivalent frame', f'<figure class="missing"><figcaption>{side}</figcaption><p>No equivalent frame at this revision</p></figure>'
            src = f'{side}/{html.escape(name)}'
            return f'`{side}/{name}`', f'<figure><figcaption>{side}</figcaption><a href="{src}"><img loading="lazy" src="{src}" alt="{side} {html.escape(name)}"></a></figure>'

        names = sorted(files.get(sid, [])) or [f'{sid}.png']
        rows = []
        for name in names:
            parts = [cell(side, name) for side in sides]
            action = next((d['frames'][name]['action'] for d in sides.values() if name in d['frames']), scenario['title'])
            md.append(f'- {action}: ' + ' · '.join(p[0] for p in parts))
            rows.append(f'<div class="step"><h3>{html.escape(action)}</h3><div class="pair">{"".join(p[1] for p in parts)}</div></div>')
        md.append('')
        meta = html.escape(scenario['page'] if same_page else '; '.join(p.replace('`', '') for p in pages))
        cards.append(f'<section id="{html.escape(sid)}"><h2>{html.escape(scenario["title"])} <code>{html.escape(sid)}</code></h2>'
                     f'<p class="meta">{meta}. {html.escape(scenario["state"])}</p>' + ''.join(rows) + '</section>')
    (out / 'INDEX.md').write_text('\n'.join(md))

    heads = ''.join(
        f"<li><b>{side}</b> <code>{html.escape(str(d['source'].get('sha', '?')))}</code> "
        f"({html.escape(str(d['source'].get('rev', '?')))}, suite {html.escape(str(d['source'].get('suite', 'current')))}), captured {html.escape(d['times'][0] if d['times'] else 'nothing')}</li>"
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
