import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from models import ExtractedTask

HIGH_PATTERNS = [
    r"\bremind me to (?P<task>[^.?!]+)",
    r"\bdon't let me forget to (?P<task>[^.?!]+)",
    r"\bdo not let me forget to (?P<task>[^.?!]+)",
    r"\bi(?:'ll| will) (?P<task>send|call|email|follow up|reply|finish|submit|book|schedule)[^.?!]*",
    r"\bi need to follow up with (?P<task>[^.?!]+)",
]
MEDIUM_PATTERNS = [
    r"\bwe should (?P<task>[^.?!]+)",
    r"\bi probably need to (?P<task>[^.?!]+)",
    r"\blet's remember to (?P<task>[^.?!]+)",
    r"\bcan you make sure (?P<task>[^.?!]+)",
]
LOW_PATTERNS = [
    r"\bmaybe (?P<task>[^.?!]+)",
    r"\bit would be nice to (?P<task>[^.?!]+)",
    r"\bif we ever (?P<task>[^.?!]+)",
]
DATE_PATTERNS = [
    (r"\btomorrow\b", lambda now: now + timedelta(days=1)),
    (r"\bnext week\b", lambda now: now + timedelta(days=7)),
    (r"\btoday\b", lambda now: now),
]


def extract_tasks_from_text(
    text: str,
    source_conversation_id: Optional[str] = None,
    source_segment_ids: Optional[Iterable[str]] = None,
    now: Optional[datetime] = None,
) -> List[ExtractedTask]:
    now = now or datetime.now(timezone.utc)
    tasks: List[ExtractedTask] = []
    for pattern in HIGH_PATTERNS:
        tasks.extend(_matches(pattern, text, 0.9, source_conversation_id, source_segment_ids, now))
    for pattern in MEDIUM_PATTERNS:
        tasks.extend(_matches(pattern, text, 0.62, source_conversation_id, source_segment_ids, now))
    for pattern in LOW_PATTERNS:
        tasks.extend(_matches(pattern, text, 0.35, source_conversation_id, source_segment_ids, now))
    return _dedupe(tasks)


def extract_tasks_from_webhook(payload: Dict[str, Any]) -> List[ExtractedTask]:
    text = payload.get("transcript") or payload.get("text") or ""
    if not text and payload.get("segments"):
        text = " ".join(str(segment.get("text", "")) for segment in payload["segments"])
    segment_ids = [str(segment.get("id")) for segment in payload.get("segments", []) if segment.get("id")]
    return extract_tasks_from_text(
        text,
        source_conversation_id=payload.get("conversation_id") or payload.get("memory_id"),
        source_segment_ids=segment_ids,
    )


def _matches(
    pattern: str,
    text: str,
    confidence: float,
    source_conversation_id: Optional[str],
    source_segment_ids: Optional[Iterable[str]],
    now: datetime,
) -> List[ExtractedTask]:
    results = []
    for match in re.finditer(pattern, text, flags=re.IGNORECASE):
        task_text = _clean_task(match.group("task") if "task" in match.groupdict() else match.group(0))
        if not task_text:
            continue
        due = _extract_due_at(match.group(0), now)
        results.append(
            ExtractedTask(
                title=task_text[:120],
                description=match.group(0).strip(),
                source_conversation_id=source_conversation_id,
                source_segment_ids=list(source_segment_ids or []),
                due_at=due,
                owner="user" if confidence >= 0.6 else "unknown",
                confidence=confidence,
                destination="none",
                requires_confirmation=True,
            )
        )
    return results


def _clean_task(text: str) -> str:
    text = re.sub(r"\b(by|before|tomorrow|today|next week|at \d{1,2}(:\d{2})?\s*(am|pm)?)\b.*", "", text, flags=re.I)
    return " ".join(text.strip(" .?!").split())


def _extract_due_at(text: str, now: datetime) -> Optional[datetime]:
    for pattern, resolver in DATE_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return resolver(now).replace(hour=9, minute=0, second=0, microsecond=0)
    return None


def _dedupe(tasks: List[ExtractedTask]) -> List[ExtractedTask]:
    seen = set()
    deduped = []
    for task in sorted(tasks, key=lambda item: item.confidence, reverse=True):
        key = task.title.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(task)
    return deduped
