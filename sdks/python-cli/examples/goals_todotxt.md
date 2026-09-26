# Turn tracked goals into a todo.txt file

Use this recipe to keep your Omi tracked goals in the plain-text
[todo.txt](https://github.com/todotxt/todo.txt) format. Active goals receive
priority markers, completed/inactive goals receive the `x` marker, categories
become `+projects`, and metric progress values are captured as key:value tags.
It reads a saved JSON export, makes no network requests, and produces standard
`todo.txt` syntax.

You need Python 3.10+ and an authenticated `omi-cli` for the initial export.

Export your goals:

```sh
omi --json goal list --limit 100 > goals.json
```

Save the following as `goals_to_todotxt.py`:

```python
import json
import re
import sys
from pathlib import Path

ZWSP = "\u200b"  # zero-width space: breaks todo.txt syntax without altering display
RESERVED_KEYS = {"cur", "target", "pct", "id", "due", "pri", "unit"}


def one_line(value):
    """Render one exported field as clean single-line text."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return " ".join(value.split())


def task_text(value):
    """Keep goal title and description from colliding with todo.txt syntax."""
    words = []
    for word in one_line(value).split(" "):
        if len(word) > 1 and word[0] in "+@":
            word = ZWSP + word
        elif ":" in word and word.split(":", 1)[0].lower() in RESERVED_KEYS:
            key, rest = word.split(":", 1)
            word = f"{key}{ZWSP}:{rest}"
        words.append(word)
    text = " ".join(words) or "(untitled goal)"
    if re.match(r"x |\([A-Z]\) |\d{4}-\d{2}-\d{2}( |$)", text):
        text = ZWSP + text
    return text


def calculate_progress(current, target):
    """Calculate progress percentage safely."""
    try:
        if current is not None and target is not None:
            c = float(current)
            t = float(target)
            if t > 0:
                return round((c / t) * 100.0, 1)
    except (ValueError, TypeError, ZeroDivisionError):
        pass
    return None


def format_goal_line(goal):
    """Format one goal dict into a canonical todo.txt line."""
    is_active = bool(goal.get("is_active", True))
    current_val = goal.get("current_value")
    target_val = goal.get("target_value")
    pct = calculate_progress(current_val, target_val)

    title = task_text(goal.get("title"))
    goal_type = one_line(goal.get("goal_type")) or "goal"
    project_tag = "+" + re.sub(r"[^\w\-]", "", goal_type.lower()) if goal_type else "+goal"

    tokens = []
    if not is_active:
        tokens.append("x")
    else:
        tokens.append("(B)")

    tokens.append(title)
    tokens.append(project_tag)
    tokens.append("@omi")

    if current_val is not None:
        tokens.append(f"cur:{current_val}")
    if target_val is not None:
        tokens.append(f"target:{target_val}")
    if pct is not None:
        tokens.append(f"pct:{pct}%")
    if goal.get("unit"):
        tokens.append(f"unit:{one_line(goal.get('unit'))}")
    if goal.get("id"):
        tokens.append(f"id:{goal.get('id')}")

    return " ".join(tokens)


def convert(source, destination):
    items = json.loads(Path(source).read_bytes())
    if not isinstance(items, list):
        raise ValueError("Expected the JSON array from omi --json goal list")

    lines = []
    for item in items:
        if not isinstance(item, dict):
            continue
        lines.append(format_goal_line(item))

    payload = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
    dest_path = Path(destination)
    try:
        output = dest_path.open("xb")
    except FileExistsError:
        raise FileExistsError(f"Refusing to overwrite existing {dest_path}") from None
    try:
        with output:
            output.write(payload)
    except OSError:
        dest_path.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python goals_to_todotxt.py INPUT.json OUTPUT.txt")
    try:
        convert(sys.argv[1], sys.argv[2])
    except Exception as exc:
        sys.exit(f"Error: {exc}")
```

Run the script:

```sh
python goals_to_todotxt.py goals.json todo.txt
```
