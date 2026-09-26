```python
import json
import sys
import os
from datetime import datetime
import re

def goals_to_markdown():
    goals_json = sys.stdin.read()
    goals = json.loads(goals_json)

    now = datetime.utcnow()
    frontmatter = f"---\n"
    frontmatter += f"tags: ['goal', 'checklist']\n"
    frontmatter += f"updated_at: {now.isoformat()}\n"
    frontmatter += f"active_goals: {len([g for g in goals if not g.get('completed')])}\n"
    frontmatter += f"completed_goals: {len([g for g in goals if g.get('completed')])}\n"
    frontmatter += "---\n\n"

    active_goals = []
    completed_goals = []

    for goal in goals:
        if goal.get('completed'):
            section = completed_goals
        else:
            section = active_goals

        if goal.get('type') == 'number':
            current = goal.get('current')
            target = goal.get('target')
            if target:
                percentage = (current / target * 100) if target != 0 else 0
                percentage = f"({percentage:.1f}%)"
            else:
                percentage = ""
        elif goal.get('type') == 'scale':
            current = goal.get('current')
            target = goal.get('scale_steps') or 5
            percentage = (current / target * 100) if target != 0 else 0
            percentage = f"({percentage:.1f}%)"
        else:
            percentage = ""

        checkbox = "- [ ]" if not goal.get('completed') else "- [x]"
        line = f"{checkbox} {goal['title']}{percentage}"
        section.append(line)

    output = frontmatter + "\nActive Goals:\n\n" + "\n".join(active_goals) + "\n\n"
    if completed_goals:
        output += "Completed Goals:\n\n" + "\n".join(completed_goals)

    filename = os.path.join("sdks/python-cli/examples/goals_markdown.md")
    with open(filename, "x") if not sys.stdin.isatty() else sys.stdout.write(output.encode()):
        pass

if __name__ == "__main__":
    goals_to_markdown()
```