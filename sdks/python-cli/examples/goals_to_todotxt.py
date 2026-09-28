#!/usr/bin/env python3
"""
Export Omi goals to todo.txt format.

This script fetches user goals from the Omi CLI, formats them according to
todo.txt conventions, and writes them to a specified file.

- Active goals are assigned `(B)` priority.
- Inactive goals (achieved or abandoned) are prefixed with `x `.
- Numeric and scale goals include `\cur:X`, `\target:Y`, and `\pct:Z%` tags.
- Zero-width spaces (ZWSP) are inserted to prevent user-provided titles from
  being misinterpreted as todo.txt completion or priority prefixes.
- Plus (`+`) and at (`@`) symbols in titles are escaped to ensure they are
  treated as literal text.
- The script uses atomic file writes to prevent accidental data loss.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional

# Zero-width space for syntax protection
ZWSP = "\u200b"


def _atomic_write(filepath: str, content: str, overwrite: bool) -> None:
    """
    Atomically writes content to a file.

    Writes to a temporary file and then renames it to the target filepath.
    Raises FileExistsError if the file exists and overwrite is False.
    """
    if not overwrite and os.path.exists(filepath):
        raise FileExistsError(f"File '{filepath}' already exists. Use --overwrite to replace.")

    # Write to a temporary file in the same directory
    temp_filepath = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, encoding="utf-8", dir=os.path.dirname(filepath)
        ) as temp_file:
            temp_file.write(content)
            temp_filepath = temp_file.name
        os.replace(temp_filepath, filepath)
    finally:
        if temp_filepath and os.path.exists(temp_filepath):
            os.remove(temp_filepath)


def _escape_todotxt_title(title: str) -> str:
    """
    Escapes characters in the title that could be misinterpreted as todo.txt syntax.
    """
    # Escape '+' and '@' to prevent them from being interpreted as project/context tags.
    # Since we are not mapping structured categories to +projects, these should be literal.
    escaped_title = re.sub(r"([+@])", r"\\\1", title)
    return escaped_title


def format_goal_to_todotxt(goal: Dict[str, Any]) -> str:
    """
    Formats a single Omi goal dictionary into a todo.txt line.
    """
    title = str(goal.get("title", "")).strip()
    is_active = bool(goal.get("is_active", False))
    goal_type = goal.get("goal_type")
    current_value = goal.get("current_value")
    target_value = goal.get("target_value")
    unit = goal.get("unit")

    line_parts: List[str] = []

    # 1. Completion prefix
    if not is_active:
        line_parts.append("x")

    # 2. Priority for active goals
    if is_active:
        line_parts.append("(B)")

    # 3. ZWSP protection for titles that start with todo.txt syntax
    # This prevents user-provided "x-ray" from becoming a completed task,
    # or "(A) plan" from becoming a priority A task if we assigned (B).
    # We check the *original* title for these patterns.
    original_title_starts_with_x = re.match(r"x\s", title, re.IGNORECASE)
    original_title_starts_with_priority = re.match(r"\([A-Z]\)\s", title)

    if (not is_active and original_title_starts_with_x) or \
       (is_active and original_title_starts_with_priority):
        line_parts.append(ZWSP)

    # 4. Escaped title
    line_parts.append(_escape_todotxt_title(title))

    # 5. Metric tags
    if goal_type in ("numeric", "scale"):
        tags: List[str] = []
        if current_value is not None:
            formatted_cur = f"{current_value:.2f}".rstrip("0").rstrip(".")
            tags.append(f"\\cur:{formatted_cur}{unit if unit else ''}")
        if target_value is not None:
            formatted_target = f"{target_value:.2f}".rstrip("0").rstrip(".")
            tags.append(f"\\target:{formatted_target}{unit if unit else ''}")

        if current_value is not None and target_value is not None and target_value != 0:
            pct = (current_value / target_value) * 100
            tags.append(f"\\pct:{pct:.0f}%")
        line_parts.extend(tags)

    return " ".join(filter(None, line_parts)).strip()


def main() -> None:
    """
    Main function to fetch goals and write them to a todo.txt file.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Export Omi goals to todo.txt format.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "output_file",
        help="Path to the output todo.txt file. Use '-' for stdout.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite the output file if it already exists.",
    )
    args = parser.parse_args()

    try:
        # Fetch goals using omi-cli
        # We include inactive goals to allow marking them as 'x ' in todo.txt
        result = subprocess.run(
            [sys.executable, "-m", "omi_cli", "--json", "goal", "list", "--include-inactive"],
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
        )
        goals_data: List[Dict[str, Any]] = json.loads(result.stdout)
    except FileNotFoundError:
        print("Error: 'omi_cli' command not found. Ensure omi-cli is installed and in your PATH.", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"Error calling omi-cli: {e}", file=sys.stderr)
        print(f"Stderr: {e.stderr}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: Could not parse JSON output from omi-cli: {result.stdout}", file=sys.stderr)
        sys.exit(1)

    todo_lines: List[str] = []
    for goal in goals_data:
        todo_lines.append(format_goal_to_todotxt(goal))

    output_content = "\n".join(todo_lines) + "\n"

    if args.output_file == "-":
        sys.stdout.write(output_content)
    else:
        try:
            _atomic_write(args.output_file, output_content, args.overwrite)
            print(f"Goals exported to '{args.output_file}'")
        except FileExistsError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        except IOError as e:
            print(f"Error writing to file '{args.output_file}': {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()