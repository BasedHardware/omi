#!/usr/bin/env python3
"""Convert Omi action items JSON exports into JSON Lines (JSONL / NDJSON).

This script reads one or more Omi action items JSON export files or reads from
standard input (Unix pipeline), deduplicates items across pages, normalizes timestamps
to ISO-8601 / RFC 3339 UTC strings, normalizes completion booleans, and writes
newline-delimited JSON records (RFC 8259) to an output file or standard output.

Zero external dependencies: 100% Python standard library only.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Dict, Iterable, List, Optional, Tuple


def _parse_timestamp(raw_val: Any) -> Optional[datetime]:
    """Parse various timestamp representations into an aware UTC datetime."""
    if raw_val is None:
        return None
    if isinstance(raw_val, (int, float)):
        try:
            # Handle millisecond timestamps
            ts = float(raw_val)
            if ts > 1e11:
                ts /= 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            return None

    str_val = str(raw_val).strip()
    if not str_val:
        return None

    # Handle numeric timestamp formatted as string
    try:
        ts = float(str_val)
        if ts > 1e11:
            ts /= 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except (ValueError, OverflowError, OSError):
        pass

    # Normalize trailing Z to +00:00 for fromisoformat
    iso_candidate = str_val
    if iso_candidate.endswith("Z") or iso_candidate.endswith("z"):
        iso_candidate = iso_candidate[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(iso_candidate)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except (ValueError, TypeError):
        pass

    # Try common fallback patterns
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(str_val, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt
        except (ValueError, TypeError):
            continue

    return None


def _format_timestamp(raw_val: Any) -> Optional[str]:
    """Format timestamp as ISO-8601 / RFC 3339 UTC string with Z suffix."""
    dt = _parse_timestamp(raw_val)
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _coerce_bool(val: Any) -> bool:
    """Coerce various boolean representations to a python bool."""
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    if isinstance(val, str):
        normalized = val.strip().lower()
        if normalized in ("true", "1", "yes", "completed", "done", "t", "y"):
            return True
        if normalized in ("false", "0", "no", "open", "pending", "f", "n", ""):
            return False
    return bool(val)


def _safe_str(val: Any) -> str:
    """Safely convert any value to string without leading/trailing whitespace."""
    if val is None:
        return ""
    return str(val).strip()


def _generate_synthetic_id(
    description: str,
    created_at: Optional[str] = None,
    due_date: Optional[str] = None,
    conversation_id: Optional[str] = None,
    extra_entropy: Optional[str] = None,
) -> str:
    """Generate a deterministic fallback ID incorporating all stable record attributes."""
    hasher = hashlib.sha256()
    hasher.update((description or "").encode("utf-8"))
    hasher.update(b"::")
    hasher.update((created_at or "").encode("utf-8"))
    hasher.update(b"::")
    hasher.update((due_date or "").encode("utf-8"))
    hasher.update(b"::")
    hasher.update((conversation_id or "").encode("utf-8"))
    if extra_entropy:
        hasher.update(b"::")
        hasher.update(extra_entropy.encode("utf-8"))
    return f"syn_{hasher.hexdigest()[:16]}"


def unwrap_action_items(payload: Any) -> List[Dict[str, Any]]:
    """Unwrap action items from list or standard envelope structures."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if isinstance(payload, dict):
        for key in ("action_items", "items", "data", "results"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                return [item for item in candidate if isinstance(item, dict)]
        # Single action item record provided as top-level dict
        if "description" in payload or "id" in payload:
            return [payload]

    return []


def normalize_record(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a raw action item record into canonical JSONL schema."""
    description = _safe_str(raw.get("description"))

    # Parse and normalize timestamps
    created_at = _format_timestamp(raw.get("created_at"))
    updated_at = _format_timestamp(raw.get("updated_at"))
    due_date = _format_timestamp(raw.get("due_date") or raw.get("due_at"))

    if not updated_at:
        updated_at = created_at

    conversation_id = raw.get("conversation_id")
    conv_id_str = _safe_str(conversation_id) if conversation_id is not None else None
    if conv_id_str == "":
        conv_id_str = None

    # Normalize ID
    item_id = _safe_str(raw.get("id"))
    if not item_id:
        # Include full raw dump (excluding id) to ensure distinct records never collide
        raw_entropy = json.dumps({k: v for k, v in raw.items() if k != "id"}, sort_keys=True, default=str)
        item_id = _generate_synthetic_id(
            description=description,
            created_at=created_at,
            due_date=due_date,
            conversation_id=conv_id_str,
            extra_entropy=raw_entropy,
        )

    # Normalize completion and status
    raw_completed = raw.get("completed")
    raw_status = _safe_str(raw.get("status")).lower()

    if raw_completed is not None:
        completed = _coerce_bool(raw_completed)
    elif raw_status:
        completed = raw_status in ("completed", "done", "closed", "resolved")
    else:
        completed = False

    status = "completed" if completed else "open"

    conversation_id = raw.get("conversation_id")
    conv_id_str = _safe_str(conversation_id) if conversation_id is not None else None
    if conv_id_str == "":
        conv_id_str = None

    return {
        "id": item_id,
        "description": description,
        "completed": completed,
        "status": status,
        "created_at": created_at,
        "updated_at": updated_at,
        "due_date": due_date,
        "conversation_id": conv_id_str,
    }


def deduplicate_records(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplicate records by id, retaining the record with the latest updated_at."""
    merged: Dict[str, Tuple[Optional[datetime], Dict[str, Any]]] = {}

    for rec in records:
        rec_id = rec.get("id")
        if not rec_id:
            continue

        updated_dt = _parse_timestamp(rec.get("updated_at")) or _parse_timestamp(rec.get("created_at"))

        if rec_id not in merged:
            merged[rec_id] = (updated_dt, rec)
        else:
            existing_dt, _ = merged[rec_id]
            # If current record has a newer timestamp (or existing has none), replace
            if existing_dt is None and updated_dt is not None:
                merged[rec_id] = (updated_dt, rec)
            elif existing_dt is not None and updated_dt is not None and updated_dt > existing_dt:
                merged[rec_id] = (updated_dt, rec)

    return [item[1] for item in merged.values()]


def filter_and_sort_records(
    records: List[Dict[str, Any]],
    status_filter: str = "all",
    sort_mode: str = "created_desc",
) -> List[Dict[str, Any]]:
    """Filter records by status and apply requested ordering."""
    filtered = records
    if status_filter == "open":
        filtered = [r for r in records if not r.get("completed")]
    elif status_filter == "completed":
        filtered = [r for r in records if r.get("completed")]

    if sort_mode == "none":
        return filtered

    def _sort_key(r: Dict[str, Any]) -> Tuple[datetime, str]:
        if sort_mode in ("created_desc", "created_asc"):
            dt = _parse_timestamp(r.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc)
        elif sort_mode == "due_date":
            dt = _parse_timestamp(r.get("due_date")) or datetime.max.replace(tzinfo=timezone.utc)
        else:
            dt = datetime.min.replace(tzinfo=timezone.utc)
        return (dt, r.get("id", ""))

    reverse = sort_mode in ("created_desc",)
    return sorted(filtered, key=_sort_key, reverse=reverse)


def check_path_traversal(destination: Path) -> None:
    """Validate that path traversal sequences (..) are not used in destination path."""
    dest_str = str(destination)
    parts = Path(dest_str).parts
    if ".." in parts or "../" in dest_str or "..\\" in dest_str:
        raise ValueError(f"Path traversal ('..') is not permitted: {destination}")


def write_jsonl_atomic(
    records: List[Dict[str, Any]],
    destination: Path,
    overwrite: bool = False,
) -> None:
    """Atomically write JSON Lines records to the target destination file."""
    check_path_traversal(destination)

    destination = destination.resolve()

    if destination.exists() and not overwrite:
        raise FileExistsError(
            f"Destination file already exists: {destination}. Use -f or --overwrite to replace it."
        )

    parent_dir = destination.parent
    parent_dir.mkdir(parents=True, exist_ok=True)

    temp_file = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=parent_dir,
        delete=False,
        suffix=".tmp",
    )
    temp_path = Path(temp_file.name)

    try:
        for record in records:
            line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
            temp_file.write(line + "\n")
        temp_file.flush()
        os.fsync(temp_file.fileno())
        temp_file.close()

        os.replace(temp_path, destination)
    except Exception:
        temp_file.close()
        if temp_path.exists():
            temp_path.unlink()
        raise


def format_jsonl_stream(records: Iterable[Dict[str, Any]]) -> str:
    """Format records into newline-delimited JSON string."""
    lines = [json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in records]
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Convert Omi action items JSON exports into JSON Lines (JSONL / NDJSON).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="One or more input JSON files, or '-' to read from standard input.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Target output .jsonl file path (writes to stdout if omitted).",
    )
    parser.add_argument(
        "-f",
        "--overwrite",
        action="store_true",
        help="Overwrite output file if it already exists.",
    )
    parser.add_argument(
        "--status",
        choices=["all", "open", "completed"],
        default="all",
        help="Filter action items by status.",
    )
    parser.add_argument(
        "--sort",
        choices=["created_desc", "created_asc", "due_date", "none"],
        default="created_desc",
        help="Sort order for the exported records.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """Main entrypoint for action-items to JSONL converter."""
    args = parse_args(argv)

    raw_items: List[Dict[str, Any]] = []

    for src in args.inputs:
        if src == "-":
            try:
                content = sys.stdin.read()
                if not content.strip():
                    sys.stderr.write(
                        "Error: Empty input received from stdin. If piping from omi, verify that upstream command succeeded.\n"
                    )
                    return 1
                data = json.loads(content)
                raw_items.extend(unwrap_action_items(data))
            except json.JSONDecodeError as exc:
                sys.stderr.write(f"Error: Invalid JSON from stdin: {exc}\n")
                return 1
            except Exception as exc:
                sys.stderr.write(f"Error reading stdin: {exc}\n")
                return 1
        else:
            path = Path(src)
            if not path.is_file():
                sys.stderr.write(f"Error: Input file not found: {path}\n")
                return 1
            try:
                with path.open("r", encoding="utf-8") as f:
                    content = f.read()
                    if not content.strip():
                        sys.stderr.write(f"Error: Empty file: {path}\n")
                        return 1
                    data = json.loads(content)
                    raw_items.extend(unwrap_action_items(data))
            except json.JSONDecodeError as exc:
                sys.stderr.write(f"Error: Invalid JSON in {path}: {exc}\n")
                return 1
            except Exception as exc:
                sys.stderr.write(f"Error reading {path}: {exc}\n")
                return 1

    # Normalize each item
    normalized = [normalize_record(item) for item in raw_items]

    # Deduplicate across pages / files
    deduped = deduplicate_records(normalized)

    # Filter and sort
    final_records = filter_and_sort_records(
        deduped,
        status_filter=args.status,
        sort_mode=args.sort,
    )

    if args.output:
        try:
            write_jsonl_atomic(final_records, args.output, overwrite=args.overwrite)
        except (FileExistsError, ValueError) as exc:
            sys.stderr.write(f"Error: {exc}\n")
            return 1
        except Exception as exc:
            sys.stderr.write(f"Error writing to {args.output}: {exc}\n")
            return 1
    else:
        try:
            output_str = format_jsonl_stream(final_records)
            sys.stdout.write(output_str)
            sys.stdout.flush()
        except BrokenPipeError:
            # Devnull stderr and exit cleanly when downstream consumer closes pipe
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, sys.stderr.fileno())
            return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
