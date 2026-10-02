#!/usr/bin/env python3
"""Convert Omi goal JSON exports into streaming JSON Lines (JSONL / NDJSON)."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple
import uuid


def text(value: Any) -> Optional[str]:
    """Render a field as safe text, dropping C0 control codes, surrogates, and noncharacters."""
    if value is None:
        return None
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    collapsed = " ".join(value.split())
    clean = "".join(
        ch for ch in collapsed
        if (ch >= " " or ch in "\n\t") and not ("\ud800" <= ch <= "\udfff") and ch not in ("\ufffe", "\uffff")
    )
    return clean if clean else None


def iso_utc(value: Any) -> Optional[str]:
    """Normalize timestamp string into ISO-8601 UTC format (YYYY-MM-DDTHH:MM:SSZ)."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (ValueError, OverflowError):
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc)
    else:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_float(value: Any) -> Optional[float]:
    """Parse a float value safely, rejecting non-finite numbers and handling overflow."""
    if value is None:
        return None
    try:
        val = float(value)
        if not math.isfinite(val):
            return None
        return val
    except (ValueError, TypeError, OverflowError):
        return None


def normalize_bool_flag(value: Any) -> Optional[bool]:
    """Normalize boolean flags, integer flags, and string aliases safely."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    s = str(value).strip().lower()
    if s in ("true", "1", "yes"):
        return True
    if s in ("false", "0", "no"):
        return False
    return None


def derive_status(goal: Dict[str, Any]) -> str:
    """Derive status strictly: inactive first, then completed/achieved, then active."""
    active_flag = normalize_bool_flag(goal.get("is_active"))
    if active_flag is False:
        return "inactive"

    achieved_flag = normalize_bool_flag(goal.get("is_achieved"))
    completed_flag = normalize_bool_flag(goal.get("is_completed"))
    if achieved_flag is True or completed_flag is True:
        return "completed"
    if achieved_flag is False or completed_flag is False:
        return "active"

    goal_type = str(goal.get("goal_type") or "").strip().lower()
    if goal_type == "boolean":
        c = parse_float(goal.get("current_value"))
        if c is not None and c >= 1.0:
            return "completed"
        return "active"

    curr = parse_float(goal.get("current_value"))
    target = parse_float(goal.get("target_value"))
    min_v = parse_float(goal.get("min_value"))
    max_v = parse_float(goal.get("max_value"))
    base = min_v if min_v is not None else 0.0
    denom = None
    if target is not None and target != base:
        denom = target - base
    elif max_v is not None and max_v != base:
        denom = max_v - base

    if curr is not None and denom is not None and denom > 0:
        if (curr - base) >= denom:
            return "completed"

    if target == 0.0 and curr == 0.0:
        return "completed"

    return "active"


def calc_progress_pct(goal: Dict[str, Any], is_completed: bool) -> Optional[float]:
    """Calculate progress percentage (0.0 to 100.0+) or None if qualitative and uncompleted."""
    if is_completed:
        return 100.0

    goal_type = str(goal.get("goal_type") or "").strip().lower()
    if goal_type == "boolean":
        c = parse_float(goal.get("current_value"))
        return 100.0 if (c is not None and c >= 1.0) else 0.0

    curr = parse_float(goal.get("current_value"))
    target = parse_float(goal.get("target_value"))
    min_v = parse_float(goal.get("min_value"))
    max_v = parse_float(goal.get("max_value"))

    if curr is None:
        return None

    base = min_v if min_v is not None else 0.0
    denom = None
    if target is not None and target != base:
        denom = target - base
    elif max_v is not None and max_v != base:
        denom = max_v - base

    if denom is not None and denom > 0:
        pct = round(((curr - base) / denom) * 100.0, 2)
        return pct

    if target == 0.0 and curr == 0.0:
        return 100.0

    return None


def unwrap_goals(raw: Any, source_label: str) -> List[Dict[str, Any]]:
    """Unwrap goals from standard response envelopes or bare lists."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("goals", "items", "data", "results"):
            candidate = raw.get(key)
            if isinstance(candidate, list):
                return candidate
        if "title" in raw or "id" in raw or "goal_type" in raw:
            return [raw]
        return []
    raise ValueError(f"{source_label}: root JSON must be a list or an object with a goals array")


def load(sources: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    """Load and deduplicate goals from files or stdin ('-')."""
    goals_by_id: Dict[str, Dict[str, Any]] = {}

    for source in sources:
        source_label = "stdin" if source == "-" else source
        if source == "-":
            content = sys.stdin.buffer.read()
        else:
            path = Path(source)
            if not path.is_file():
                raise FileNotFoundError(f"Input file not found: {source}")
            content = path.read_bytes()

        if not content.strip():
            continue

        raw = json.loads(content.decode("utf-8-sig"))
        items = unwrap_goals(raw, source_label)
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"{source_label} item {idx}: each goal must be an object")

            raw_id = item.get("id")
            clean_id = text(raw_id)
            if clean_id is not None:
                final_id = clean_id
            else:
                stable_sig = hashlib.sha256(
                    json.dumps(item, sort_keys=True, ensure_ascii=True).encode("utf-8")
                ).hexdigest()[:16]
                final_id = f"gen_{stable_sig}"
            item["id"] = final_id
            goals_by_id[final_id] = item
    return goals_by_id


def build_jsonl(
    goals_by_id: Dict[str, Dict[str, Any]],
    status_filter: str = "all",
) -> Tuple[str, int]:
    """Convert goals dict into formatted JSON Lines string with normalized records."""
    norm_filter = status_filter.strip().lower() if status_filter else "all"
    lines: List[str] = []
    count = 0

    for goal_id, item in goals_by_id.items():
        st = derive_status(item)
        if norm_filter != "all" and st != norm_filter:
            continue

        is_act = (st != "inactive")
        is_comp = (st == "completed")
        prog = calc_progress_pct(item, is_comp)

        record = {
            "id": goal_id,
            "title": text(item.get("title")) or "(untitled goal)",
            "goal_type": text(item.get("goal_type")),
            "current_value": parse_float(item.get("current_value")),
            "target_value": parse_float(item.get("target_value")),
            "min_value": parse_float(item.get("min_value")),
            "max_value": parse_float(item.get("max_value")),
            "unit": text(item.get("unit")),
            "is_active": is_act,
            "is_completed": is_comp,
            "progress_pct": prog,
            "created_at": iso_utc(item.get("created_at")),
            "updated_at": iso_utc(item.get("updated_at")),
        }

        line = json.dumps(record, ensure_ascii=False)
        lines.append(line)
        count += 1

    output = ("\n".join(lines) + "\n") if lines else ""
    return output, count


def convert(
    sources: Sequence[str],
    destination: Optional[str] = None,
    status_filter: str = "all",
    overwrite: bool = False,
) -> int:
    """Load goals, convert to JSONL, and write to destination file or stdout."""
    goals = load(sources)
    jsonl_str, count = build_jsonl(goals, status_filter=status_filter)
    payload = jsonl_str.encode("utf-8")

    if not destination or destination == "-":
        sys.stdout.buffer.write(payload)
        sys.stdout.buffer.flush()
        return count

    output_path = Path(destination)
    parent_dir = output_path.parent
    parent_dir.mkdir(parents=True, exist_ok=True)

    if not overwrite:
        try:
            output = output_path.open("xb")
        except FileExistsError:
            raise FileExistsError(
                f"Refusing to overwrite existing {output_path} (use --overwrite to replace)"
            ) from None
        try:
            with output:
                output.write(payload)
        except OSError:
            output_path.unlink(missing_ok=True)
            raise
    else:
        tmp_name = f".tmp_goals_jsonl_{uuid.uuid4().hex}.jsonl"
        tmp_path = parent_dir / tmp_name
        try:
            with tmp_path.open("xb") as tmp_file:
                tmp_file.write(payload)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())
            tmp_path.replace(output_path)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise

    return count


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert Omi goal JSON exports into streaming JSON Lines (JSONL / NDJSON)."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="One or more goal JSON export files, or '-' for stdin",
    )
    parser.add_argument("-o", "--output", help="Destination JSONL file path (defaults to stdout)")
    parser.add_argument(
        "--status",
        choices=["all", "active", "completed", "inactive"],
        default="all",
        help="Filter goals by status: all, active, completed, or inactive (default: all)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow overwriting existing destination file",
    )

    args = parser.parse_args(argv)

    try:
        count = convert(
            args.inputs,
            destination=args.output,
            status_filter=args.status,
            overwrite=args.overwrite,
        )
        if args.output and args.output != "-":
            print(f"JSONL written to {args.output} ({count} goals exported)")
        return 0
    except BrokenPipeError:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        os.close(devnull)
        return 1
    except (OSError, ValueError) as exc:
        sys.exit(f"JSONL export failed: {exc}")


if __name__ == "__main__":
    sys.exit(main())
