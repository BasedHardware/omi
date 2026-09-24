#!/usr/bin/env python3
"""Compile Omi conversations into an offline EPUB e-book for Kindle, Apple Books, and e-readers.

Usage:
    python conversations_to_epub.py conversations.json -o my_journal.epub
    omi --json conversation list | python conversations_to_epub.py - --title "Omi Journal 2026" -o journal.epub

Compiles conversations into a fully compliant EPUB archive:
- Chapter per conversation with structured overview and transcript dialogue
- Table of contents (NCX and OPF navigation)
- Clean, responsive e-reader CSS typography
Requires only the Python standard library (zipfile, json, html).
"""

from __future__ import annotations

import argparse
import html
import json
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, List


def extract_conversations(content: str, source_label: str = "<input>") -> List[Dict[str, Any]]:
    """Parse JSON and extract list of conversation items."""
    raw = content.lstrip("\ufeff")
    items = json.loads(raw)

    if isinstance(items, dict):
        for key in ("conversations", "items", "data"):
            if isinstance(items.get(key), list):
                items = items[key]
                break
        else:
            items = [items]

    if not isinstance(items, list):
        raise ValueError(f"{source_label}: expected a JSON array or wrapped conversations object")

    return items


def build_chapter_html(conv: Dict[str, Any], chapter_num: int) -> str:
    """Generate XHTML for a single conversation chapter."""
    structured = conv.get("structured") or {}
    title = str(structured.get("title") or conv.get("title") or f"Conversation {chapter_num}").strip()
    overview = str(structured.get("overview") or conv.get("overview") or "").strip()
    date_str = str(conv.get("started_at") or conv.get("created_at") or "")[:19].replace("T", " ")

    segments = conv.get("transcript_segments") or []

    dialogue_html = []
    if isinstance(segments, list) and segments:
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            spk = html.escape(str(seg.get("speaker") or seg.get("speaker_id") or "Speaker"))
            txt = html.escape(str(seg.get("text") or ""))
            dialogue_html.append(
                f'<p class="dialogue"><strong class="speaker">{spk}:</strong> {txt}</p>'
            )
    elif conv.get("transcript"):
        dialogue_html.append(f'<p>{html.escape(str(conv["transcript"]))}</p>')

    content = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">
<head>
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: Georgia, serif; line-height: 1.6; margin: 5%; color: #1a1a1a; }}
    h1 {{ font-size: 1.8em; margin-bottom: 0.2em; color: #111; }}
    .date {{ font-size: 0.9em; color: #666; margin-bottom: 1.5em; }}
    .overview {{ background: #f4f4f5; padding: 1em; border-left: 4px solid #6366f1; margin-bottom: 2em; }}
    .overview h3 {{ margin-top: 0; font-size: 1em; text-transform: uppercase; color: #4338ca; }}
    .dialogue {{ margin-bottom: 0.8em; }}
    .speaker {{ color: #3730a3; }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <div class="date">{html.escape(date_str)}</div>
  {f'<div class="overview"><h3>Overview</h3><p>{html.escape(overview)}</p></div>' if overview else ''}
  <div class="transcript">
    {''.join(dialogue_html)}
  </div>
</body>
</html>"""
    return content


def build_epub(
    conversations: List[Dict[str, Any]], output_path: Path, title: str = "Omi Conversations"
) -> None:
    """Build and write EPUB archive file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(output_path, "w") as zf:
        # 1. mimetype (must be first and uncompressed)
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)

        # 2. META-INF/container.xml
        container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""
        zf.writestr("META-INF/container.xml", container_xml, compress_type=zipfile.ZIP_DEFLATED)

        # Build chapters
        manifest_items = [
            '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
        ]
        spine_items = []
        nav_points = []

        for idx, conv in enumerate(conversations, start=1):
            ch_id = f"chapter_{idx}"
            ch_filename = f"{ch_id}.xhtml"
            ch_content = build_chapter_html(conv, idx)
            zf.writestr(f"OEBPS/{ch_filename}", ch_content, compress_type=zipfile.ZIP_DEFLATED)

            manifest_items.append(
                f'<item id="{ch_id}" href="{ch_filename}" media-type="application/xhtml+xml"/>'
            )
            spine_items.append(f'<itemref idref="{ch_id}"/>')

            ch_title = str(
                (conv.get("structured") or {}).get("title")
                or conv.get("title")
                or f"Chapter {idx}"
            ).strip()
            nav_points.append(f"""    <navPoint id="navPoint-{idx}" playOrder="{idx}">
      <navLabel><text>{html.escape(ch_title)}</text></navLabel>
      <content src="{ch_filename}"/>
    </navPoint>""")

        # 3. OEBPS/toc.ncx
        toc_ncx = f"""<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="urn:uuid:omi-conversations-export"/>
    <meta name="dtb:depth" content="1"/>
  </head>
  <docTitle><text>{html.escape(title)}</text></docTitle>
  <navMap>
{chr(10).join(nav_points)}
  </navMap>
</ncx>"""
        zf.writestr("OEBPS/toc.ncx", toc_ncx, compress_type=zipfile.ZIP_DEFLATED)

        # 4. OEBPS/content.opf
        content_opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="BookId" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>{html.escape(title)}</dc:title>
    <dc:creator>Omi AI</dc:creator>
    <dc:language>en</dc:language>
    <dc:identifier id="BookId">urn:uuid:omi-conversations-export</dc:identifier>
  </metadata>
  <manifest>
    {chr(10).join('    ' + item for item in manifest_items)}
  </manifest>
  <spine toc="ncx">
    {chr(10).join('    ' + item for item in spine_items)}
  </spine>
</package>"""
        zf.writestr("OEBPS/content.opf", content_opf, compress_type=zipfile.ZIP_DEFLATED)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compile Omi conversations into an offline EPUB e-book."
    )
    parser.add_argument("inputs", nargs="*", help="Input JSON files or '-' for stdin")
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="Destination .epub file path",
    )
    parser.add_argument(
        "--title",
        default="Omi Journal",
        help="Title of the e-book",
    )
    args = parser.parse_args()

    all_conversations: List[Dict[str, Any]] = []
    for src in args.inputs:
        if str(src) == "-":
            content = sys.stdin.read()
            all_conversations.extend(extract_conversations(content, "<stdin>"))
        else:
            p = Path(src)
            content = p.read_text(encoding="utf-8")
            all_conversations.extend(extract_conversations(content, str(p)))

    if not all_conversations:
        print("Error: No conversations provided to compile.", file=sys.stderr)
        sys.exit(1)

    out_file = Path(args.output)
    build_epub(all_conversations, out_file, title=args.title)
    print(f"Compiled {len(all_conversations)} conversation(s) into EPUB e-book at {out_file}", file=sys.stderr)


if __name__ == "__main__":
    main()
