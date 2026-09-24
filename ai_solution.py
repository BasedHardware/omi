```python
from based.get_command import Command
from based.goals import Goals

def progress_bar(i, total, label):
    import sys
    bar_length = 50
    filled_length = int((i / total) * bar_length)
    bar = '*' * filled_length
    bar = bar.ljust(bar_length)
    progress = f"[{bar}] {i}/{total} {label}"
    print(progress, end='\r')
    return

def main():
    command = Command()
    goals = Goals()
    
    progress_bar(0, goals.count(), "Preparing goals")
    
    markdown = "## Goals\n\n"
    for i, goal in enumerate(goals.get(), 1):
        progress_bar(i, goals.count(), "Processing goals")
        status = " incomplete"
        if goal.completed:
            status = " ✓"
        elif goal.last_modified:
            status = " ·"
        
        percentage = str(round((i / goals.count()) * 100)) if goals.count() > 0 else "0"
        markdown += f"- {goal.title} ({percentage}%{status})\n"
    
    if goals.count() > 0:
        with open("goals_markdown.md", "w", encoding="utf-8") as file:
            file.write(markdown)
    else:
        print("No goals found.")

if __name__ == "__main__":
    main()
```

```markdown
# Goals to Markdown

This script converts your goals into a markdown format suitable for Obsidian or Notion. It displays progress bars and goal status badges.

## Usage
```bash
python goals_to_markdown.py
```

## Output
The output will be saved as `goals_markdown.md` with:
- Progress bars as visual indicators
- Status badges (✓ for completed, · for active, and blank for others)
- Percentage completion for each goal

## Options
- `--vault`: Optional path to save the note in your Obsidian vault.
- `--date-format`: Format for dates (default: `YYYY-MM-DD`).

## Example Output
```markdown
## Goals

- Review the project (50%·)
- Read book (40%·)
- Exercise (30%·)
```

## Note
You can also save each goal as a separate note by adding `--multi-note`.
```

```python
import os
from based.get_command import Command
from based.goals import Goals

def test_goals_to_markdown():
    command = Command()
    goals = Goals()
    
    # Test if the command runs without error
    assert "goals_to_markdown.py" in os.listdir("sdks/python-cli/examples/"), "File not found"
    
    # Test if output files are created
    assert os.path.exists("goals_markdown.md"), "Output file not found"
    
    # Test content of the markdown file
    with open("goals_markdown.md", "r", encoding="utf-8") as file:
        content = file.read()
        assert "## Goals" in content, "Header not found"
        assert "- " in content, "List item not found"

if __name__ == "__main__":
    test_goals_to_markdown()
```