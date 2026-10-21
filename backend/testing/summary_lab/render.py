"""Render a lab run to a standalone HTML table."""

from __future__ import annotations

import html

from testing.summary_lab.runner import LabRun


def render_lab_html(run: LabRun) -> str:
    rows: list[str] = []
    for cell in run.cells:
        defects = ', '.join(cell.judge.defects) or 'none'
        title = ''
        raw_title = cell.note.get('title')
        if isinstance(raw_title, str):
            title = raw_title
        rows.append(
            '<tr>'
            f'<td>{html.escape(cell.fixture_id)}</td>'
            f'<td>{html.escape(cell.variant_id)}</td>'
            f'<td>{cell.judge.usefulness:.2f}</td>'
            f'<td>${cell.cost.usd:.5f}</td>'
            f'<td>{html.escape(defects)}</td>'
            f'<td>{html.escape(title)}</td>'
            '</tr>'
        )
    body = '\n'.join(rows)
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>summary lab</title>
  <style>
    body {{ font-family: sans-serif; margin: 24px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ccc; padding: 6px 8px; text-align: left; }}
    th {{ background: #f4f4f4; }}
  </style>
</head>
<body>
  <h1>summary lab</h1>
  <p>mean usefulness {run.mean_usefulness:.3f} · estimated USD {run.total_usd:.5f}</p>
  <table>
    <thead>
      <tr>
        <th>fixture</th>
        <th>variant</th>
        <th>usefulness</th>
        <th>est. USD</th>
        <th>defects</th>
        <th>title</th>
      </tr>
    </thead>
    <tbody>
{body}
    </tbody>
  </table>
</body>
</html>
'''
