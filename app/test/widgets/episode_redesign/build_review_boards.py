"""Combine unmodified Flutter captures into labeled before/after review boards.

Run from the repo root with backend/.venv/bin/python (Pillow is already a dependency).
"""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[4]
OUTPUT = ROOT / '.agent-artifacts/ui-evidence/episoderedesign'
FONT = ROOT / 'app/test/fonts/SFPRODISPLAYREGULAR.OTF'


def main():
    font = ImageFont.truetype(str(FONT), 24)
    small = ImageFont.truetype(str(FONT), 19)
    width, height, gap = 589, 1278, 24
    states = ['typical-day', 'many-noisy', 'few-members', 'long-summary']
    for ordinal, state in enumerate(states, 23):
        board = Image.new('RGB', (width * 2 + gap * 3, height * 2 + 200), '#ececf1')
        draw = ImageDraw.Draw(board)
        draw.text((gap, 14), f'{state.replace("-", " ").title()} · Synthetic fixture · Render review only',
                  fill='#161618', font=font)
        for col, phase in enumerate(['before', 'after']):
            x = gap + col * (width + gap)
            draw.text((x, 52), 'Before / current page' if col == 0 else 'After / proposal',
                      fill='#161618', font=font)
            for row, position in enumerate(['top', 'rows']):
                y = 110 + row * (height + 64)
                draw.text((x, y - 25), 'At open' if row == 0 else 'End of list (scrolled)',
                          fill='#48484b', font=small)
                files = list(OUTPUT.glob(f'*-mobile-ios-{state}-{phase}-{position}.png'))
                assert len(files) == 1, (state, phase, position, files)
                with Image.open(files[0]) as frame:
                    assert frame.size == (1179, 2556), frame.size
                    board.paste(frame.convert('RGB').resize((width, height), Image.Resampling.LANCZOS), (x, y))
        board.save(OUTPUT / f'{ordinal:03}-mobile-ios-{state}-comparison.png')

    entries = []
    for path in sorted(OUTPUT.glob('*.png')):
        slug = path.stem.split('-mobile-ios-', 1)[1]
        assert len(slug) <= 40, slug
        entries.append({
            'file': path.name,
            'platform': 'mobile-ios',
            'description': f'Episode redesign review: {slug.replace("-", " ")}. '
                           'Synthetic data only. Current production widget before; test-only proposal after. '
                           'Widget-test rendering, not device E2E.',
            'captured_by': 'agent',
            'source': 'visual-audit',
        })
    (OUTPUT / 'evidence.json').write_text(json.dumps({'version': 1, 'images': entries}, indent=2) + '\n')
    print(f'Created four review boards and manifest for {len(entries)} images in {OUTPUT}')


if __name__ == '__main__':
    main()
