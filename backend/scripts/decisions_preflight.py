"""Decisions preflight CLI.

Runs `extract_decisions` over a uid's recent conversations to evaluate the
Decisions lens before enabling it for that user. Dumps per-conversation
JSON and a CSV summary.

Usage:
    python backend/scripts/decisions_preflight.py --uid <uid> --limit 50 \\
        [--output-dir /tmp/preflight]
"""

import argparse
import csv
import json
import os
import statistics
import sys
from pathlib import Path
from typing import List, Optional

# Allow running from repo root or from backend/.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from database.conversations import get_conversations  # noqa: E402
from models.conversation import Conversation, Decision, Structured  # noqa: E402
from utils.llm.decisions import extract_decisions  # noqa: E402


def _conversation_to_transcript(conversation: Conversation) -> str:
    """Best-effort transcript extraction for an offline conversation dict."""
    try:
        return conversation.get_transcript(False)
    except Exception:
        # Fall back to raw segment text.
        segments = getattr(conversation, 'transcript_segments', []) or []
        return "\n".join(getattr(s, 'text', '') for s in segments)


def _build_conversation(raw: dict) -> Optional[Conversation]:
    """Hydrate a Conversation from the raw firestore dict; skip on failure."""
    try:
        return Conversation(**raw)
    except Exception:
        return None


def _decision_dict(d: Decision) -> dict:
    return {
        "id": d.id,
        "statement": d.statement,
        "owner_name": d.owner_name,
        "due_at": d.due_at.isoformat() if d.due_at else None,
        "status": d.status.value if hasattr(d.status, 'value') else str(d.status),
        "open_questions": list(d.open_questions),
        "related_action_item_ids": list(d.related_action_item_ids),
    }


def _structured_action_items(structured: Structured) -> List[dict]:
    return [
        {
            "index": i,
            "description": item.description,
            "completed": bool(item.completed),
        }
        for i, item in enumerate(structured.action_items)
    ]


def _invalid_index_pct(decisions: List[Decision], n_action_items: int) -> float:
    """Compute the share of indexes (across all decisions) that fall outside the action_items range.

    extract_decisions already drops invalids in-place, so this is informational
    for dataset-level visibility (typically 0.0 here, but kept for parity with
    the column in the spec).
    """
    total = 0
    invalid = 0
    for d in decisions:
        for idx in d.related_action_item_ids:
            total += 1
            if not (isinstance(idx, int) and 0 <= idx < n_action_items):
                invalid += 1
    if total == 0:
        return 0.0
    return invalid / total


def run_preflight(uid: str, limit: int, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_conversations = get_conversations(uid, limit=limit, include_discarded=False)
    print(f"[preflight] fetched {len(raw_conversations)} conversations for uid={uid}")

    summary_rows: List[dict] = []

    for raw in raw_conversations:
        conversation = _build_conversation(raw)
        if conversation is None or not conversation.structured:
            continue

        structured = conversation.structured
        transcript = _conversation_to_transcript(conversation)
        if not transcript.strip():
            continue

        try:
            decisions = extract_decisions(
                structured,
                transcript,
                conversation_id=getattr(conversation, 'id', 'unknown'),
            )
        except Exception as e:
            print(f"[preflight] FAILED conv={getattr(conversation, 'id', 'unknown')} error={type(e).__name__}: {e}")
            decisions = []

        n_actions = len(structured.action_items)
        linked_action_indexes: set[int] = set()
        for d in decisions:
            linked_action_indexes.update(d.related_action_item_ids)
        n_loose_actions = max(0, n_actions - len(linked_action_indexes))
        n_decisions_with_links = sum(1 for d in decisions if d.related_action_item_ids)
        invalid_pct = _invalid_index_pct(decisions, n_actions)

        record = {
            "conversation_id": getattr(conversation, 'id', 'unknown'),
            "title": (structured.title or '').strip(),
            "structured_action_items": _structured_action_items(structured),
            "extracted_decisions": [_decision_dict(d) for d in decisions],
            "n_decisions": len(decisions),
            "n_loose_actions": n_loose_actions,
            "n_decisions_with_links": n_decisions_with_links,
            "max_invalid_index_pct": invalid_pct,
        }

        out_path = output_dir / f"decisions_{record['conversation_id']}.json"
        with out_path.open("w") as fh:
            json.dump(record, fh, indent=2, default=str)

        summary_rows.append(
            {
                "conv_id": record["conversation_id"],
                "title": record["title"],
                "n_decisions": record["n_decisions"],
                "n_loose_actions": record["n_loose_actions"],
                "n_decisions_with_links": record["n_decisions_with_links"],
                "max_invalid_index_pct": f"{record['max_invalid_index_pct']:.4f}",
            }
        )

    csv_path = output_dir / "decisions_summary.csv"
    with csv_path.open("w", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "conv_id",
                "title",
                "n_decisions",
                "n_loose_actions",
                "n_decisions_with_links",
                "max_invalid_index_pct",
            ],
        )
        writer.writeheader()
        writer.writerows(summary_rows)

    n_total = len(summary_rows)
    decisions_counts = [r["n_decisions"] for r in summary_rows]
    invalid_pcts = [float(r["max_invalid_index_pct"]) for r in summary_rows]

    median_decisions = statistics.median(decisions_counts) if decisions_counts else 0.0
    pct_zero = (sum(1 for c in decisions_counts if c == 0) / n_total * 100.0) if n_total else 0.0
    max_invalid = max(invalid_pcts) if invalid_pcts else 0.0

    print(f"[preflight] conversations evaluated: {n_total}")
    print(f"[preflight] median decisions/meeting: {median_decisions}")
    print(f"[preflight] zero-decision rate: {pct_zero:.1f}%")
    print(f"[preflight] max invalid-index rate: {max_invalid:.4f}")
    print(f"[preflight] output dir: {output_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Decisions extraction over a uid's recent conversations.")
    parser.add_argument("--uid", required=True, help="Target user uid")
    parser.add_argument("--limit", type=int, default=50, help="Max conversations to evaluate")
    parser.add_argument(
        "--output-dir",
        default=os.path.join("/tmp", "decisions_preflight"),
        help="Directory to write per-conv JSON and the CSV summary",
    )
    args = parser.parse_args()
    run_preflight(args.uid, args.limit, Path(args.output_dir))


if __name__ == "__main__":
    main()
