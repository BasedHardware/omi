```python
# sdks/python-cli/examples/goals_html.md
To generate an HTML dashboard for Omi goals, use the following command:

```bash
omi --json goal list --limit 100 --include-inactive
```

Then, run the converter script:

```bash
python goals_to_html.py
```

The HTML will be saved to `goals.html`, which includes a responsive layout with stats cards, progress bars, and goal details.

# sdks/python-cli/examples/goals_to_html.py
```python
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

def main():
    import sys
    from html import escape

    data = json.load(sys.stdin)
    html = _generate_html(data)
    with open("goals.html", "w", encoding="utf-8") as f:
        f.write(html)

def _generate_html(data):
    goals = data.get("goals", [])
    stats = data.get("stats", {})

    def escape_html(text: str) -> str:
        return escape(text).replace('"', "&quot;")

    def format_date(date_str: str, offset: int = 0) -> str:
        if not date_str:
            return ""
        try:
            dt = datetime.fromisoformat(date_str)
            return dt.strftime("%Y-%m-%d %H:%M:%S %z")
        except ValueError:
            return date_str

    def format_number(num: str) -> str:
        try:
            return f"{float(num):.2f}"
        except ValueError:
            return num

    def progress_bar_html(goal):
        value = goal.get("current")
        target = goal.get("target")
        if not (value and target):
            return ""
        if goal["type"] == "Numeric":
            percent = (float(value) / float(target)) * 100
            color = "progress-positive" if percent >= 100 else "progress-negative"
            return f"<div class='progress-bar {color}' style='width: {min(percent, 100)}%'>{percent:.1f}%</div>"
        elif goal["type"] == "Scale":
            scale = goal.get("scale", "5")
            scale_steps = scale.split(',')
            value_index = int(float(value))
            target_index = int(float(target))
            if value_index > target_index:
                value_index = target_index
            step_size = len(scale_steps)
            progress_percent = (value_index / target_index) * 100
            return f"<div class='progress-bar progress-positive' style='width: {min(progress_percent, 100)}%'>{progress_percent:.1f}%</div>"

    def format_badge(text: str, category: str) -> str:
        colors = {
            "Active": "bg-success",
            "Inactive": "bg-danger",
            "Achieved": "bg-success",
            "Not Achieved": "bg-danger",
        }
        return f'<span class="badge badge-{colors.get(category, "bg-primary")}">{escape_html(text)}</span>'

    def format_type_badge(goal):
        type_ = goal.get("type", "Unknown")
        return format_badge(type_, type_)

    def format_due_date(goal):
        due_date = goal.get("due_date", "")
        offset = int(data.get("utc_offset", "0").replace(':', ''))
        formatted_date = format_date(due_date, offset)
        return formatted_date

    html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Omi Goals Dashboard</title>
    <style>
        body {{ 
            font-family: Arial, sans-serif;
        }}
        .container {{ 
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }}
        .card {{ 
            background: white;
            border-radius: 10px;
            padding: 20px;
            margin: 10px 0;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .stats-grid {{ 
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .progress-bar {{" 
            height: 20px;
            background: #eee;
            border-radius: 10px;
            overflow: hidden;
        }}
        .progress-positive {{ 
            background-color: #4CAF50;
        }}
        .progress-negative {{ 
            background-color: #f44336;
        }}
        .badge {{ 
            padding: 5px 10px;
            border-radius: 20px;
        }}
        @media print {{ 
            body {{ 
                background: white;
            }}
            .card {{ 
                box-shadow: none;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Omi Goals Dashboard</h1>
        <div class="stats-grid">
            <div class="card stat-card">
                <h3>Statistics</h3>
                <p>Total Goals: {escape_html(str(stats.get("total", 0)))}</p>
                <p>Active: {escape_html(str(stats.get("active", 0)))}</p>
                <p>Inactive: {escape_html(str(stats.get("inactive", 0)))}</p>
                <p>Achieved: {escape_html(str(stats.get("achieved", 0)))}</p>
            </div>
        </div>
        <div class="goals-list">
            {"".join(f"<div class='card goal-card'>
                <h3>{escape_html(goal['title'])}</h3>
                <p>Type: {format_type_badge(goal)}</p>
                <p>Unit: {escape_html(goal.get('unit', ''))}</p>
                <p>Target: {escape_html(str(goal.get('target', '')))}</p>
                <p>Current: {escape_html(str(goal.get('current', '')))}</p>
                <p>Due: {format_due_date(goal)}</p>
                <div class='progress-container'>
                    {progress_bar_html(goal)}
                </div>
                <div class='badges-container'>
                    {format_badge('Active', 'Active' if goal['status'] == 'Active' else 'Inactive')}
                    {format_badge('Achieved', 'Achieved' if goal.get('achieved', False) else 'Not Achieved')}
                </div>
            </div>" for goal in goals)}
        </div>
    </div>
</body>
</html>
"""
    return html

# sdks/python-cli/tests/test_goals_to_html.py
import json
from pathlib import Path
from unittest.mock import patch
from unittest import TestCase

class TestGoalsToHtml(TestCase):
    def test_goals_to_html(self):
        test_data = {
            "goals": [
                {
                    "title": "Test Goal 1",
                    "type": "Numeric",
                    "unit": "percent",
                    "target": "100",
                    "current": "80",
                    "status": "Active",
                    "achieved": True,
                    "due_date": "2023-10-01T00:00:00"
                },
                {
                    "title": "Test Goal 2",
                    "type": "Scale",
                    "unit": "rating",
                    "target": "5",
                    "current": "3",
                    "status": "Inactive",
                    "achieved": False,
                    "due_date": "2023-10-02T00:00:00"
                }
            ],
            "stats": {
                "total": 2,
                "active": 1,
                "inactive": 1,
                "achieved": 1
            }
        }
        with patch('sys.stdin', json.dumps(test_data)):
            main()
        self.assertTrue(Path('goals.html').exists())
        with open('goals.html', 'r', encoding='utf-8') as f:
            content = f.read()
            self.assertIn("Test Goal 1", content)
            self.assertIn("Test Goal 2", content)
            self.assertIn("80.0%", content)
            self.assertIn("60.0%", content)
            self.assertIn("2023-10-01+00:00", content)
            self.assertIn("2023-10-02+00:00", content)
```
```