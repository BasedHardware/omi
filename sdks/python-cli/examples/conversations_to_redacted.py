#!/usr/bin/env python3
"""Sanitize and redact Personally Identifiable Information (PII) from Omi conversation exports.

Usage:
    python conversations_to_redacted.py conversations.json -o redacted_conversations.json
    omi --json conversation list | python conversations_to_redacted.py - -o clean.json --summary

Protects privacy prior to sharing, uploading to third-party LLMs, or indexing.
Redacts emails, phone numbers, API keys/secrets, IPv4 addresses, and credit card numbers.
Requires only the Python standard library.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Redaction patterns
RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
RE_PHONE = re.compile(
    r"(?:(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}|\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b)"
)
RE_CARD = re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b")
RE_SECRET = re.compile(
    r"\b(?:sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{30,}|gho_[a-zA-Z0-9]{30,}|AIza[0-9A-Za-z-_]{35}|[a-zA-Z0-9_-]{32,45}\.eyJ[a-zA-Z0-9_-]{20,})\b"
)
RE_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def redact_text(text: str) -> Tuple[str, Dict[str, int]]:
    """Redact sensitive PII tokens from string and return count statistics."""
    if not text:
        return text, {}

    stats: Dict[str, int] = {}

    def replace_and_count(pattern: re.Pattern, repl: str, s: str, key: str) -> str:
        matches = len(pattern.findall(s))
        if matches:
            stats[key] = stats.get(key, 0) + matches
            return pattern.sub(repl, s)
        return s

    cleaned = text
    cleaned = replace_and_count(RE_SECRET, "[REDACTED_SECRET]", cleaned, "secrets")
    cleaned = replace_and_count(RE_EMAIL, "[REDACTED_EMAIL]", cleaned, "emails")
    cleaned = replace_and_count(RE_CARD, "[REDACTED_CARD]", cleaned, "cards")
    cleaned = replace_and_count(RE_PHONE, "[REDACTED_PHONE]", cleaned, "phones")
    cleaned = replace_and_count(RE_IPV4, "[REDACTED_IP]", cleaned, "ips")

    return cleaned, stats


def sanitize_conversation(conv: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, int]]:
    """Sanitize a conversation object in-place or copy, returning redaction counts."""
    sanitized = json.loads(json.dumps(conv))
    total_stats: Dict[str, int] = {}

    def accumulate(stats: Dict[str, int]) -> None:
        for k, v in stats.items():
            total_stats[k] = total_stats.get(k, 0) + v

    # Structured fields
    if isinstance(sanitized.get("structured"), dict):
        st = sanitized["structured"]
        for field in ("title", "overview"):
            if st.get(field):
                st[field], s = redact_text(str(st[field]))
                accumulate(s)

    # Top-level fields
    for field in ("title", "overview", "transcript"):
        if sanitized.get(field):
            sanitized[field], s = redact_text(str(sanitized[field]))
            accumulate(s)

    # Segments
    segments = sanitized.get("transcript_segments")
    if isinstance(segments, list):
        for seg in segments:
            if isinstance(seg, dict) and seg.get("text"):
                seg["text"], s = redact_text(str(seg["text"]))
                accumulate(s)

    return sanitized, total_stats


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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sanitize and redact Personally Identifiable Information (PII) from Omi conversations."
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        help="Input JSON files or '-' for stdin",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="-",
        help="Destination JSON file (defaults to stdout)",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print summary of redacted items to stderr",
    )
    args = parser.parse_args()

    if not args.inputs:
        parser.print_help()
        sys.exit(1)

    all_conversations: List[Dict[str, Any]] = []
    for src in args.inputs:
        if str(src) == "-":
            content = sys.stdin.read()
            all_conversations.extend(extract_conversations(content, "<stdin>"))
        else:
            p = Path(src)
            content = p.read_text(encoding="utf-8")
            all_conversations.extend(extract_conversations(content, str(p)))

    sanitized_items = []
    total_stats: Dict[str, int] = {}
    for conv in all_conversations:
        clean_conv, stats = sanitize_conversation(conv)
        sanitized_items.append(clean_conv)
        for k, v in stats.items():
            total_stats[k] = total_stats.get(k, 0) + v

    output_text = json.dumps(sanitized_items, indent=2, ensure_ascii=False)

    if args.output != "-":
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_text, encoding="utf-8")
    else:
        sys.stdout.write(output_text + "\n")

    if args.summary or args.output != "-":
        summary_lines = [f"{k}: {v}" for k, v in sorted(total_stats.items())]
        summary_str = ", ".join(summary_lines) if summary_lines else "none detected"
        print(
            f"Redacted {len(sanitized_items)} conversations. Elements redacted: [{summary_str}]",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
