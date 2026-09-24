#!/usr/bin/env python3
"""Convert Omi memories JSON export into a Graphviz (.dot) knowledge graph.

Usage:
    python memories_to_graphviz.py memories.json -o knowledge_graph.dot
    omi --json memory list | python memories_to_graphviz.py - -o memories.dot
    dot -Tpng memories.dot -o memories.png

Generates clean Graphviz DOT syntax clustering memories by category into subgraphs,
with styled nodes containing titles/previews and timestamps.
Requires only the Python standard library.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List


def extract_memories(content: str, source_label: str = "<input>") -> List[Dict[str, Any]]:
    """Parse JSON and extract list of memory items."""
    raw = content.lstrip("\ufeff")
    items = json.loads(raw)

    if isinstance(items, dict):
        for key in ("memories", "items", "data"):
            if isinstance(items.get(key), list):
                items = items[key]
                break
        else:
            items = [items]

    if not isinstance(items, list):
        raise ValueError(f"{source_label}: expected a JSON array or wrapped memories object")

    results = []
    for item in items:
        if not isinstance(item, dict):
            continue
        text = str(item.get("content") or item.get("text") or "").strip()
        mid = str(item.get("id") or "").strip()
        if text and mid:
            results.append(item)

    return results


def escape_dot(text: str) -> str:
    """Escape text safely for Graphviz node labels."""
    cleaned = text.replace('"', '\\"').replace("\n", "\\n")
    return cleaned


def generate_dot_graph(memories: List[Dict[str, Any]], title: str = "Omi Knowledge Graph") -> str:
    """Generate Graphviz DOT representation of memories clustered by category."""
    lines = [
        f'digraph "{escape_dot(title)}" {{',
        '  graph [rankdir=LR, fontname="Helvetica,Arial,sans-serif", bgcolor="transparent", compound=true];',
        '  node [shape=box, style="rounded,filled", fillcolor="#f8fafc", color="#cbd5e1", fontname="Helvetica,Arial,sans-serif", fontsize=10];',
        '  edge [color="#94a3b8", arrowhead=vee];',
        "",
    ]

    # Group memories by category
    categories: Dict[str, List[Dict[str, Any]]] = {}
    for mem in memories:
        cat = str(mem.get("category") or "general").strip()
        categories.setdefault(cat, []).append(mem)

    # Category colors
    palette = [
        ("#eff6ff", "#3b82f6"),  # blue
        ("#f0fdf4", "#22c55e"),  # green
        ("#faf5ff", "#a855f7"),  # purple
        ("#fff7ed", "#f97316"),  # orange
        ("#fdf2f8", "#ec4899"),  # pink
        ("#f8fafc", "#64748b"),  # slate
    ]

    for idx, (cat_name, cat_mems) in enumerate(sorted(categories.items())):
        fill, stroke = palette[idx % len(palette)]
        sanitized_cat = re.sub(r"\W+", "_", cat_name)
        lines.append(f"  subgraph cluster_{sanitized_cat} {{")
        lines.append(f'    label = "{escape_dot(cat_name.upper())}";')
        lines.append(f'    color = "{stroke}";')
        lines.append('    style = "dashed,rounded";')
        lines.append(f'    fontcolor = "{stroke}";')
        lines.append('    fontname = "Helvetica-Bold";')
        lines.append('    fontsize = 11;')
        lines.append("")

        for mem in cat_mems:
            mid = re.sub(r"\W+", "_", str(mem["id"]))
            content = str(mem.get("content") or mem.get("text") or "").strip()
            # truncate for display if long
            preview = (content[:50] + "...") if len(content) > 50 else content
            date_str = str(mem.get("created_at") or "")[:10]
            label_text = f"{preview}\\n({date_str})" if date_str else preview

            lines.append(
                f'    node_{mid} [label="{escape_dot(label_text)}", fillcolor="{fill}", color="{stroke}"];'
            )

        lines.append("  }")
        lines.append("")

    lines.append("}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi memories JSON export into a Graphviz (.dot) knowledge graph."
    )
    parser.add_argument("inputs", nargs="*", help="Input JSON files or '-' for stdin")
    parser.add_argument(
        "-o",
        "--output",
        default="-",
        help="Destination .dot file (defaults to stdout)",
    )
    parser.add_argument(
        "--title",
        default="Omi Knowledge Graph",
        help="Custom graph title",
    )
    args = parser.parse_args()

    if not args.inputs:
        parser.print_help()
        sys.exit(1)

    all_memories: List[Dict[str, Any]] = []
    for src in args.inputs:
        if str(src) == "-":
            content = sys.stdin.read()
            all_memories.extend(extract_memories(content, "<stdin>"))
        else:
            p = Path(src)
            content = p.read_text(encoding="utf-8")
            all_memories.extend(extract_memories(content, str(p)))

    dot_output = generate_dot_graph(all_memories, args.title)

    if args.output != "-":
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(dot_output, encoding="utf-8")
        print(f"Generated Graphviz knowledge graph with {len(all_memories)} memories at {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(dot_output + "\n")


if __name__ == "__main__":
    main()
