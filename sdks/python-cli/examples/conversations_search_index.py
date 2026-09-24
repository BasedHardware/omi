#!/usr/bin/env python3
"""Build and query an offline full-text inverted search index for Omi conversations.

Usage:
    # Build search index
    python conversations_search_index.py conversations.json -o index.json
    omi --json conversation list | python conversations_search_index.py - -o index.json

    # Query the index from command line
    python conversations_search_index.py --index index.json --query "architecture postgres"

Generates a portable, dependency-free full-text inverted index in pure JSON,
enabling instant sub-millisecond keyword and boolean searches across thousands of conversations.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

STOP_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "as", "at", "be", "because", "been", "before", "being", "below",
    "between", "both", "but", "by", "could", "did", "do", "does", "doing", "down",
    "during", "each", "few", "for", "from", "further", "had", "has", "have",
    "having", "he", "her", "here", "hers", "herself", "him", "himself", "his",
    "how", "i", "if", "in", "into", "is", "it", "its", "itself", "just", "me",
    "more", "most", "my", "myself", "no", "nor", "not", "of", "off", "on", "once",
    "only", "or", "other", "ought", "our", "ours", "ourselves", "out", "over",
    "own", "same", "she", "should", "so", "some", "such", "than", "that", "the",
    "their", "theirs", "them", "themselves", "then", "there", "these", "they",
    "this", "those", "through", "to", "too", "under", "until", "up", "very", "was",
    "we", "were", "what", "when", "where", "which", "while", "who", "whom", "why",
    "with", "would", "you", "your", "yours", "yourself", "yourselves"
}


def tokenize(text: str) -> List[str]:
    """Tokenize text into lowercase alphanumeric words, excluding common stop words."""
    if not text:
        return []
    words = re.findall(r"\b[a-zA-Z0-9_-]{2,}\b", text.lower())
    return [w for w in words if w not in STOP_WORDS]


def extract_conversations(content: str, source_label: str = "<input>") -> List[Dict[str, Any]]:
    """Parse JSON content and extract a list of conversation dictionaries."""
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

    results: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{source_label}: each conversation must be a JSON object")
        if not item.get("id") or str(item.get("id")).strip() == "":
            raise ValueError(f"{source_label}: conversation missing required 'id' field")
        results.append(item)

    return results


def build_index(conversations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build an inverted search index mapping words to conversation IDs."""
    inverted_index: Dict[str, List[str]] = {}
    documents: Dict[str, Dict[str, Any]] = {}

    for conv in conversations:
        cid = str(conv.get("id"))
        structured = conv.get("structured") or {}
        title = str(structured.get("title") or conv.get("title") or "Conversation").strip()
        overview = str(structured.get("overview") or conv.get("overview") or "").strip()
        category = str(structured.get("category") or conv.get("category") or "").strip()

        # Gather transcript text
        transcript_parts = []
        segments = conv.get("transcript_segments") or []
        if isinstance(segments, list) and segments:
            for s in segments:
                if isinstance(s, dict) and s.get("text"):
                    transcript_parts.append(str(s["text"]))
        elif conv.get("transcript"):
            transcript_parts.append(str(conv["transcript"]))

        full_transcript = " ".join(transcript_parts)
        combined_text = f"{title} {overview} {category} {full_transcript}"
        tokens = set(tokenize(combined_text))

        for tok in tokens:
            inverted_index.setdefault(tok, []).append(cid)

        # Store compact document summary for quick search previews
        preview = overview if overview else (full_transcript[:120] + "..." if full_transcript else title)
        documents[cid] = {
            "title": title,
            "category": category,
            "started_at": conv.get("started_at"),
            "preview": preview,
        }

    return {
        "metadata": {
            "total_documents": len(documents),
            "total_terms": len(inverted_index),
        },
        "index": inverted_index,
        "documents": documents,
    }


def search_index(index_data: Dict[str, Any], query: str) -> List[Dict[str, Any]]:
    """Search an inverted index for matching documents with ranking based on keyword overlap."""
    query_terms = tokenize(query)
    if not query_terms:
        return []

    inverted = index_data.get("index") or {}
    docs = index_data.get("documents") or {}

    doc_scores: Dict[str, int] = {}
    for term in query_terms:
        matches = inverted.get(term) or []
        for doc_id in matches:
            doc_scores[doc_id] = doc_scores.get(doc_id, 0) + 1

    ranked = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)
    results = []
    for doc_id, score in ranked:
        doc_info = docs.get(doc_id, {}).copy()
        doc_info["id"] = doc_id
        doc_info["match_score"] = score
        results.append(doc_info)

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build and query an offline full-text inverted search index for Omi conversations."
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        help="Input JSON files or '-' for standard input (used when building index)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="-",
        help="Destination JSON index file (defaults to stdout)",
    )
    parser.add_argument(
        "--index",
        help="Path to pre-built index JSON file to query",
    )
    parser.add_argument(
        "-q",
        "--query",
        help="Query terms to search across the index",
    )
    args = parser.parse_args()

    # Query mode
    if args.query:
        if not args.index:
            print("Error: --index must be provided when searching with --query", file=sys.stderr)
            sys.exit(1)
        index_file = Path(args.index)
        if not index_file.exists():
            print(f"Error: Index file not found at {args.index}", file=sys.stderr)
            sys.exit(1)

        data = json.loads(index_file.read_text(encoding="utf-8"))
        hits = search_index(data, args.query)
        print(f"Found {len(hits)} matching conversation(s) for query: '{args.query}'\n")
        for h in hits:
            print(f"• [{h['id']}] {h.get('title')} (score: {h['match_score']})")
            print(f"  Date: {h.get('started_at')} | Category: {h.get('category')}")
            print(f"  Preview: {h.get('preview')}\n")
        return

    # Build mode
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

    index_payload = build_index(all_conversations)
    output_text = json.dumps(index_payload, indent=2, ensure_ascii=False)

    if args.output != "-":
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_text, encoding="utf-8")
        print(
            f"Built search index with {index_payload['metadata']['total_terms']} terms across "
            f"{index_payload['metadata']['total_documents']} conversations at {args.output}",
            file=sys.stderr,
        )
    else:
        sys.stdout.write(output_text + "\n")


if __name__ == "__main__":
    main()
