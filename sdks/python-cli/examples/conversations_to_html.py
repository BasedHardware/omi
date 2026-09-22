#!/usr/bin/env python3
"""
Render a conversation JSON file into a styled, self‑contained HTML report.

The script accepts a JSON file containing a list of messages, each with a
``role`` (e.g. "user", "assistant") and ``content`` field.  It produces a
single HTML file that can be opened in any browser without external
dependencies.

Usage:
    python conversations_to_html.py --input convo.json --output report.html
"""

import argparse
import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import List, Dict

__all__ = ["render_conversation_to_html", "main"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def _load_conversation(path: Path) -> List[Dict]:
    """Load and validate the conversation JSON."""
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Input file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc

    if not isinstance(data, list):
        raise ValueError(f"Conversation JSON must be a list of messages, got {type(data)}")

    for idx, msg in enumerate(data, start=1):
        if not isinstance(msg, dict):
            raise ValueError(f"Message #{idx} is not a JSON object")
        if "role" not in msg or "content" not in msg:
            raise ValueError(f"Message #{idx} missing required keys 'role' or 'content'")
    return data


def _generate_html(messages: List[Dict], title: str = "Conversation Report") -> str:
    """Return a complete HTML document as a string."""
    css = """
    body {font-family: Arial, sans-serif; margin: 0; padding: 0; background:#f5f5f5;}
    .container {max-width: 800px; margin: 2rem auto; background:#fff; padding:2rem; box-shadow:0 0 10px rgba(0,0,0,0.1);}
    h1 {text-align:center;}
    .message {margin-bottom:1.5rem;}
    .role {font-weight:bold; color:#333;}
    .content {margin-top:0.5rem; white-space:pre-wrap;}
    """
    body = []
    for msg in messages:
        role = msg["role"].capitalize()
        content = msg["content"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        body.append(
            f'<div class="message"><span class="role">{role}:</span>'
            f'<div class="content">{content}</div></div>'
        )
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>{css}</style>
</head>
<body>
<div class="container">
<h1>{title}</h1>
{''.join(body)}
</div>
</body>
</html>"""
    return html


def render_conversation_to_html(
    input_path: Path, output_path: Path, title: str = "Conversation Report"
) -> None:
    """
    Convert a conversation JSON file to an HTML report.

    Parameters
    ----------
    input_path : Path
        Path to the input JSON file.
    output_path : Path
        Path where the HTML report will be written.
    title : str, optional
        Title of the report.
    """
    logging.info("Loading conversation from %s", input_path)
    messages = _load_conversation(input_path)

    logging.info("Generating HTML content")
    html = _generate_html(messages, title=title)

    # Write atomically: temp file + rename
    logging.info("Writing report to %s", output_path)
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            delete=False,
            dir=output_path.parent,
            suffix=".tmp",
        ) as tmp_file:
            tmp_file.write(html)
            temp_path = Path(tmp_file.name)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temp_path, output_path)
    except Exception as exc:
        # Clean up temp file if something went wrong
        if temp_path.exists():
            temp_path.unlink()
        raise RuntimeError(f"Failed to write HTML report: {exc}") from exc

    logging.info("Report written successfully to %s", output_path)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render a conversation JSON file into a styled HTML report."
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        type=Path,
        help="Path to the input conversation JSON file.",
    )
    parser.add_argument(
        "--output",
        "-o",
        required=True,
        type=Path,
        help="Path where the HTML report will be written.",
    )
    parser.add_argument(
        "--title",
        "-t",
        default="Conversation Report",
        help="Title of the generated report.",
    )
    return parser


def main(argv: List[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        render_conversation_to_html(args.input, args.output, title=args.title)
    except Exception as exc:
        logging.error("Error: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
