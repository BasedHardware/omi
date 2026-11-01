"""
Tools for accessing screen/computer activity data from the desktop app.
"""

import contextvars
import json
import math
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, cast
from utils.model_text import (
    UNTRUSTED_LEGEND,
    ContextWindow,
    DisplayClock,
    ToolTimeError,
    count_header,
    format_instant,
    format_span,
    parse_tool_time,
    truncation_note,
    untrusted_block,
)
from utils.user_clock import clock_for_config

from langchain_core.tools import tool  # type: ignore[reportUnknownVariableType]  # langchain @tool decorator partially typed
from langchain_core.runnables import RunnableConfig

import database.screen_activity as screen_activity_db
import database.vector_db as vector_db
from database._client import db as firestore_db
from utils.llm.clients import gemini_embed_query
import logging

logger = logging.getLogger(__name__)

_KEYWORD_STOPWORDS = frozenset(
    {
        'a',
        'an',
        'the',
        'and',
        'or',
        'of',
        'in',
        'on',
        'at',
        'to',
        'for',
        'with',
        'was',
        'were',
        'is',
        'are',
        'be',
        'been',
        'i',
        'me',
        'my',
        'we',
        'you',
        'that',
        'this',
        'when',
        'where',
        'what',
        'which',
        'who',
        'how',
        'did',
        'do',
        'does',
        'last',
        'from',
        'it',
        'as',
        'by',
        'if',
        'not',
        'so',
        'than',
        'then',
        'too',
        'very',
        'can',
        'just',
        'about',
        'into',
        'over',
        'after',
        'before',
    }
)

try:
    from utils.retrieval.agentic import agent_config_context
except ImportError:
    agent_config_context = contextvars.ContextVar('agent_config', default=None)


def _agent_config() -> Optional[Dict[str, Any]]:
    """Retrieve the agent config dict from the context var, or None if unset."""
    try:
        return agent_config_context.get()
    except LookupError:
        return None


def _chat_context_window(config: Any, clock: DisplayClock) -> ContextWindow:
    """The chat turn's window: the attached chat timeframe when the client sent one, else the last 24 hours.

    Harness tool rule 1: a time-range tool defaults to the run's context window. Chat shows the
    model local times labelled with their zone, so naive scope bounds are read in that zone.
    """
    cfg: Dict[str, Any] = cast(Optional[Dict[str, Any]], config) or _agent_config() or {}
    configurable: Any = cfg.get('configurable')
    scope: Any = cast(Dict[str, Any], configurable).get('chat_scope') if isinstance(configurable, dict) else None
    if isinstance(scope, dict):
        bounds = cast(Dict[str, Any], scope)
        start, end = bounds.get('start_date'), bounds.get('end_date')
    else:
        start = end = None
    if start or end:
        try:
            return ContextWindow.from_bounds(start, end, label='chat timeframe', naive_tz=clock.tz)
        except ToolTimeError:
            logger.warning('screen activity: unreadable chat_scope dates; using the last 24 hours')
    return ContextWindow.trailing_day()


def _get_uid(config: RunnableConfig) -> Optional[str]:
    cfg: Optional[Dict[str, Any]] = cast(Optional[Dict[str, Any]], config)
    if cfg is None:
        cfg = _agent_config()
    if cfg is None:
        return None
    try:
        configurable = cfg.get('configurable')
        if isinstance(configurable, dict):
            conf: Dict[str, Any] = cast(Dict[str, Any], configurable)
            return conf.get('user_id')
        return None
    except (KeyError, TypeError):
        return None


# Bound the chat tool result so a wide-range desktop query ("what did I do last month") cannot
# flood the chat model's context and make it freeze or refuse (issue #4927; the same fix already
# shipped for the conversations, memories, and action items tools). The summary lists every app the
# user touched in the range, each with up to five window titles whose length is uncapped, so a long
# range on a busy machine can run to tens of thousands of characters. Cap the apps shown and the raw
# character size and tell the model to summarize and narrow.
MAX_APPS_FOR_LLM = 50
MAX_RESULT_CHARS = 60000
MAX_CHAT_EVIDENCE_REFERENCES = 24
MAX_SCREEN_EVIDENCE_ID_CHARS = 96
MAX_SCREEN_EVIDENCE_TITLE_CHARS = 160
MAX_SCREEN_EVIDENCE_SUMMARY_CHARS = 600
# datetime.fromtimestamp is defined through year 9999 on the supported runtimes.  Rejecting
# values outside that range keeps malformed vector metadata fail-soft before display conversion.
MAX_SCREEN_EVIDENCE_TIMESTAMP_MS = 253402300799999
_SAFE_SCREEN_EVIDENCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~-]*$")


def _evidence_references(config: RunnableConfig) -> Optional[List[Any]]:
    """Return the caller-owned evidence sink when this tool is running in agentic chat.

    The sink is deliberately optional: direct tool callers and older clients keep the
    existing text-only result.  Agentic chat passes the same list through both the
    RunnableConfig and ``agent_config_context``; use the former when present so direct
    unit/tool invocations are observable as well.
    """
    candidates: List[Any] = []
    raw_config: Any = config
    if isinstance(raw_config, dict):
        candidates.append(raw_config)
    context_config = _agent_config()
    if context_config is not config:
        candidates.append(context_config)
    for cfg in candidates:
        if not isinstance(cfg, dict):
            continue
        configurable = cfg.get('configurable')
        if not isinstance(configurable, dict):
            continue
        references = configurable.get('evidence_references')
        if isinstance(references, list):
            return references
    return None


def _validated_screen_evidence_id(value: Any) -> Optional[str]:
    """Accept only bounded, delimiter-safe screen activity document IDs."""
    if value is None or isinstance(value, bool):
        return None
    try:
        normalized = str(value).strip()
    except Exception:
        return None
    if (
        not normalized
        or len(normalized) > MAX_SCREEN_EVIDENCE_ID_CHARS
        or _SAFE_SCREEN_EVIDENCE_ID_RE.fullmatch(normalized) is None
    ):
        return None
    return normalized


def _normalized_captured_at_ms(value: Any) -> Optional[int]:
    """Normalize screen-vector timestamps to non-negative Unix milliseconds."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        parsed = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        try:
            numeric = parsed.timestamp()
        except (OverflowError, OSError, ValueError):
            return None
        if not math.isfinite(numeric) or numeric < 0 or numeric * 1000 > MAX_SCREEN_EVIDENCE_TIMESTAMP_MS:
            return None
        return int(numeric * 1000)

    numeric: Optional[float] = None
    if isinstance(value, (int, float)):
        numeric = float(value)
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            numeric = float(raw)
        except ValueError:
            try:
                parsed = datetime.fromisoformat(raw.replace('Z', '+00:00'))
            except ValueError:
                return None
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            try:
                numeric = parsed.timestamp()
            except (OverflowError, OSError, ValueError):
                return None
    if numeric is None or not math.isfinite(numeric) or numeric < 0:
        return None
    # Pinecone stores seconds; tolerate already-normalized millisecond values in fixtures
    # and future vector metadata without multiplying them a second time.
    if numeric < 100_000_000_000:
        numeric *= 1000
    if numeric > MAX_SCREEN_EVIDENCE_TIMESTAMP_MS:
        return None
    return int(numeric)


def _bounded_relevance(value: Any) -> str:
    """Format vector relevance without allowing malformed non-finite values into text."""
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 'unknown'
    return f'{score:.2f}' if math.isfinite(score) else 'unknown'


def _bounded_evidence_text(value: Any, limit: int) -> str:
    """Make display-only evidence strings compact and single-line."""
    if not isinstance(value, str):
        return ''
    return ' '.join(value.split()).strip()[:limit]


def _format_screen_untrusted_fields(
    *,
    ocr_text: str,
    raw_ocr: Any,
    window_title: str,
    raw_window_title: Any,
    lookup_failed: bool,
) -> Tuple[str, bool]:
    """Format OCR and title excerpts, returning whether a trust legend is needed."""
    result = ""
    has_untrusted = False
    if window_title:
        has_untrusted = True
        result += f"  Window: {untrusted_block('screen window title', window_title)}\n"
        if isinstance(raw_window_title, str):
            normalized_title = ' '.join(raw_window_title.split()).strip()
            if len(normalized_title) > len(window_title):
                result += (
                    "  "
                    + truncation_note(
                        shown=len(window_title),
                        total=len(normalized_title),
                        unit="window-title characters",
                        how_to_get_more="Ask about a specific screen record to inspect the full title.",
                    )
                    + "\n"
                )
    if ocr_text:
        has_untrusted = True
        preview = ocr_text[:200]
        if isinstance(raw_ocr, str) and len(raw_ocr) > 200:
            preview += "..."
        result += f"  Text: {untrusted_block('screen OCR text', preview)}\n"
        if isinstance(raw_ocr, str) and len(raw_ocr) > 200:
            result += (
                "  "
                + truncation_note(
                    shown=200,
                    total=len(raw_ocr),
                    unit="OCR characters",
                    how_to_get_more="Narrow the query to inspect the full screen record.",
                )
                + "\n"
            )
    elif lookup_failed:
        result += "  Text: OCR text unavailable (lookup failed).\n"
    return result, has_untrusted


def _append_screen_evidence_reference(
    evidence_references: Optional[List[Any]],
    *,
    screenshot_id: Any,
    captured_at_ms: Optional[int],
    app_name: Any,
    window_title: Any,
    ocr_preview: Any,
) -> bool:
    """Admit one metadata-only screen reference into the shared bounded envelope."""
    if evidence_references is None:
        return True
    screen_id = _validated_screen_evidence_id(screenshot_id)
    if screen_id is None or captured_at_ms is None:
        return False
    reference_id = f'screen:{screen_id}'
    for existing in evidence_references:
        if isinstance(existing, dict) and existing.get('id') == reference_id:
            return True
    if len(evidence_references) >= MAX_CHAT_EVIDENCE_REFERENCES:
        return False

    app = _bounded_evidence_text(app_name, MAX_SCREEN_EVIDENCE_TITLE_CHARS)
    window = _bounded_evidence_text(window_title, MAX_SCREEN_EVIDENCE_TITLE_CHARS)
    ocr = _bounded_evidence_text(ocr_preview, MAX_SCREEN_EVIDENCE_SUMMARY_CHARS)
    metadata: Dict[str, Any] = {
        'app_name': app,
        'window_title': window,
        'ocr_preview': ocr,
    }
    # Keep this invariant local to the producer, rather than relying on a later Pydantic
    # validation step to reject an otherwise useful chat response.
    if len(metadata) > 16 or len(json.dumps(metadata, sort_keys=True, separators=(',', ':'))) > 2_000:
        return False
    evidence_references.append(
        {
            'id': reference_id,
            'kind': 'screen',
            'state': 'available',
            'title': app or 'Screen activity',
            'summary': ocr or None,
            'frame_id': screen_id,
            'captured_at_ms': captured_at_ms,
            'metadata': metadata,
        }
    )
    return True


def _cap_apps_for_llm(apps: List[Tuple[str, Dict[str, Any]]]) -> Tuple[List[Tuple[str, Dict[str, Any]]], bool]:
    """Keep at most ``MAX_APPS_FOR_LLM`` apps for the chat model.

    Apps arrive sorted by observation count descending. Returns
    ``(capped_list, truncated)`` where ``truncated`` is True when some apps were dropped.
    """
    if len(apps) > MAX_APPS_FOR_LLM:
        return apps[:MAX_APPS_FOR_LLM], True
    return list(apps), False


def _bounded_screen_activity_result(result: str, truncated: bool) -> str:
    """Apply a hard character budget and, when the set was truncated, append a note telling the
    model to summarize what it has and to offer to narrow, so it answers instead of freezing.

    When clipping for size, cut back to the start of the last complete app record so a partial app
    block is never left dangling (each record starts with "**<app>**" on its own line, matching the
    record-boundary clipping the conversations tool uses). If the first (or only) record is itself
    larger than the budget, keep the hard-clipped text so its data is still returned truncated rather
    than dropping every app down to just the summary header.

    The note deliberately does not state a total count: callers may pass an already-paginated
    page whose length is not the true total, so claiming a total would mislead (cubic on #8527).
    """
    if len(result) > MAX_RESULT_CHARS:
        clipped = result[:MAX_RESULT_CHARS]
        first_record = result.find("\n**")  # boundary just before the first app record
        boundary = clipped.rfind("\n**")  # boundary just before the last record that fits
        if boundary > first_record >= 0:
            # A complete record precedes the cut, so drop only the partial trailing record.
            result = clipped[:boundary]
        else:
            # The first (or only) record overflows the budget; keep the hard-clipped text so its
            # data is still returned truncated rather than dropping every app to just the header.
            result = clipped
        truncated = True
    if truncated:
        shown = len(re.findall(r"(?m)^\*\*.*\*\* — \d+ observations$", result))
        result += "\n\n" + truncation_note(
            shown=shown,
            total=None,
            cut=True,
            unit="app records",
            how_to_get_more="Ask about a specific app or a narrower date range.",
        )
    return result


@tool
def get_screen_activity_tool(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    app_filter: Optional[str] = None,
    config: RunnableConfig = None,  # type: ignore[reportAssignmentType]  # langchain injects at runtime; None default for direct calls
) -> str:
    """
    Get a summary of the user's screen/computer activity for a date range.

    Use this for questions like "what did I do on my computer today/this week?" or
    "which apps did I use?". Shows per-app observation counts and sampled window titles.
    These are synced screen observations, not measured usage durations or proof of intent.

    Requires the Omi desktop app to be installed and running.

    Args:
        start_date: Optional start of the range, ISO 8601 (e.g. "2025-01-15T00:00:00-08:00"). Offsets are
            converted; a time without an offset is in the user's timezone. Omit start_date and end_date to use
            the attached chat timeframe, or the last 24 hours.
        end_date: Optional end of the range, same format.
        app_filter: Optional app name to filter to a single application

    Returns:
        Formatted summary of screen activity by app.
    """
    logger.info(
        f"get_screen_activity_tool called - start_date={start_date}, end_date={end_date}, app_filter={app_filter}"
    )

    uid = _get_uid(config)
    if not uid:
        return "Error: User ID not found in configuration"
    clock = clock_for_config(config or _agent_config(), uid)

    try:
        start_dt, end_dt = _chat_context_window(config, clock).resolve(
            start_date, end_date, naive_tz=clock.tz, start_field='start_date', end_field='end_date'
        )
    except ToolTimeError as error:
        return f"Error: {error}"

    try:
        summary = screen_activity_db.get_screen_activity_summary(uid, start_date=start_dt, end_date=end_dt)
    except Exception:
        logger.error("get_screen_activity_tool - summary query failed uid=%s", uid, exc_info=True)
        return "Error retrieving screen activity summary. Please try again."

    apps_dict: Dict[str, Dict[str, Any]] = cast(Dict[str, Dict[str, Any]], summary['apps'])
    if not apps_dict:
        return (
            "No synced screen observations are available for this date range. "
            "Capture and sync completeness are unknown; this does not establish that the user was inactive."
        )

    # Format output
    total = summary['total_screenshots']
    coverage = summary.get('coverage') or {}
    rows_truncated = coverage.get('truncated') is True
    result = (
        f"Screen Activity Summary ({total} synced screen observations, {format_span(start_dt, end_dt, clock)}):\n"
        "Observations are sampled, not measured usage durations or proof of intent. "
        "Capture and sync completeness are unknown.\n"
    )
    if rows_truncated:
        result += (
            truncation_note(
                shown=total,
                total=None,
                cut=True,
                unit="observations",
                how_to_get_more="Only the earliest observations were summarized; narrow the date range to inspect the rest.",
            )
            + "\n"
        )
    if coverage.get('first_observed_at') and coverage.get('last_observed_at'):
        result += (
            f"Summarized observations: {format_instant(coverage['first_observed_at'], clock)} to "
            f"{format_instant(coverage['last_observed_at'], clock)}. "
            "These bounds do not establish continuous activity or current capture status.\n"
        )
    result += "\n"

    # Sort apps by count descending
    sorted_apps: List[Tuple[str, Dict[str, Any]]] = sorted(apps_dict.items(), key=lambda x: x[1]['count'], reverse=True)

    if app_filter:
        sorted_apps = [(name, data) for name, data in sorted_apps if name.lower() == app_filter.lower()]
        if not sorted_apps:
            return result + f"No observations for app '{app_filter}' in the summarized rows."

    # Bound how many apps go to the chat model so a wide date range on a busy machine cannot
    # overflow its context (issue #4927). Apps are sorted by observation count.
    total_apps = len(sorted_apps)
    sorted_apps, apps_truncated = _cap_apps_for_llm(sorted_apps)
    if apps_truncated:
        result += (
            count_header(
                "Apps by observation count",
                shown=len(sorted_apps),
                total=total_apps,
                order="most observations first",
            )
            + "\n\n"
        )

    has_untrusted = False
    for app_name, data in sorted_apps:
        count = data['count']
        titles = data.get('window_titles', [])
        first = data.get('first_seen', '')
        last = data.get('last_seen', '')

        result += f"**{app_name}** — {count} observations\n"
        if first and last:
            result += f"  Observed: {format_instant(first, clock)} to {format_instant(last, clock)}\n"
        if titles:
            normalized_titles = [' '.join(title.split()).strip() for title in titles if isinstance(title, str)]
            shown_titles = normalized_titles[:5]
            if shown_titles:
                has_untrusted = True
                result += "  Sampled windows:\n"
                for title in shown_titles:
                    result += (
                        "  " + untrusted_block("screen window title", title[:MAX_SCREEN_EVIDENCE_TITLE_CHARS]) + "\n"
                    )
                    if len(title) > MAX_SCREEN_EVIDENCE_TITLE_CHARS:
                        result += (
                            "  "
                            + truncation_note(
                                shown=MAX_SCREEN_EVIDENCE_TITLE_CHARS,
                                total=len(title),
                                unit="window-title characters",
                                how_to_get_more="Ask about a specific window title for a narrower excerpt.",
                            )
                            + "\n"
                        )
                if len(normalized_titles) > len(shown_titles):
                    result += (
                        "  "
                        + truncation_note(
                            shown=len(shown_titles),
                            total=len(normalized_titles),
                            unit="window titles",
                            how_to_get_more="Ask about a specific app to inspect its other sampled windows.",
                        )
                        + "\n"
                    )
        result += "\n"

    if has_untrusted:
        result += "\n" + UNTRUSTED_LEGEND
    return _bounded_screen_activity_result(result.strip(), apps_truncated)


def _keyword_screen_matches(
    uid: str, query: str, start_ts: Optional[int], end_ts: Optional[int], limit: int
) -> Tuple[List[Dict[str, Any]], int]:
    """Bounded keyword recall; Firestore timestamps use sortable UTC strings."""
    from database.firestore_index_registry import SCREEN_ACTIVITY_KEYWORD_RANGE_QUERY
    from database.read_boundary import parse_snapshots
    from google.cloud.firestore_v1.base_query import FieldFilter

    end = datetime.fromtimestamp(end_ts, timezone.utc) if end_ts is not None else datetime.now(timezone.utc)
    start = datetime.fromtimestamp(start_ts, timezone.utc) if start_ts is not None else end - timedelta(days=7)
    start_bound = screen_activity_db.normalize_screen_activity_timestamp(start)
    end_bound = screen_activity_db.normalize_screen_activity_timestamp(end, end_of_second=True)
    start_ms = _normalized_captured_at_ms(start_bound)
    end_ms = _normalized_captured_at_ms(end_bound)
    collection = firestore_db.collection('users').document(uid).collection('screen_activity')
    scan = SCREEN_ACTIVITY_KEYWORD_RANGE_QUERY.build(
        collection,
        {'start': start_bound, 'end': end_bound},
        field_filter_factory=FieldFilter,
    )
    snapshots = list(scan.order_by('timestamp', direction='DESCENDING').limit(500).stream())
    rows = parse_snapshots(
        dict,
        snapshots,
        payload_from_snapshot=lambda snapshot: {**snapshot.to_dict(), '_document_id': snapshot.id},
    )
    tokens = set(re.findall(r'[^\W_]+', query.casefold()))
    tokens = {token for token in tokens if token not in _KEYWORD_STOPWORDS and len(token) > 1}
    ranked = []
    for row in rows:
        sid = _validated_screen_evidence_id(row.get('_document_id'))
        timestamp = _normalized_captured_at_ms(row.get('timestamp'))
        if sid is None or timestamp is None or start_ms is None or end_ms is None:
            continue
        if not start_ms <= timestamp <= end_ms:
            continue
        text = ' '.join(
            value for key in ('ocrText', 'windowTitle', 'appName') if isinstance(value := row.get(key), str)
        ).casefold()
        if tokens and all(token in text for token in tokens):
            ranked.append((sum(text.count(token) for token in tokens), timestamp, sid, row))
    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))
    matches = [
        dict(screenshot_id=sid, score='keyword', timestamp=timestamp, appName=row.get('appName', ''), keyword_doc=row)
        for _, timestamp, sid, row in ranked[:limit]
    ]
    return matches, len(snapshots)


def _keyword_fallback(
    uid: str, query: str, start_ts: Optional[int], end_ts: Optional[int], limit: int, reason: str
) -> Tuple[Optional[List[Dict[str, Any]]], int]:
    from utils.observability.fallback import record_fallback

    record_fallback(
        component='agent_tools',
        from_mode='screen_vectors',
        to_mode='screen_keyword',
        reason=reason,
        outcome='degraded',
        log=logger,
    )
    try:
        return _keyword_screen_matches(uid, query, start_ts, end_ts, limit)
    except Exception:
        # Never include provider errors: they may contain OCR or query text.
        logger.warning('Screen keyword search unavailable')
        return None, 0


def _parse_csv_tokens(raw: Optional[str]) -> List[str]:
    """Fail-closed CSV env parsing: whitespace-only and empty tokens are ignored."""
    if raw is None:
        return []
    return [part.strip() for part in raw.split(',') if part.strip()]


def _env_flag_enabled(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() not in {'0', 'false', 'off'}


def _screen_vectors_disabled(uid: str) -> bool:
    """Server-owned account opt-out; absent configuration preserves existing accounts."""
    from config.ladder_v1 import enabled

    if enabled('LADDER_V1_PRO_GATES_ENABLED'):
        from utils import ladder_v1

        if ladder_v1.feature_allowed(uid, 'screen_context') is False:
            return True
    tokens = _parse_csv_tokens(os.getenv('SCREEN_ACTIVITY_VECTORS_DISABLED_UIDS'))
    return uid in tokens or '*' in tokens


@tool
def search_screen_activity_tool(
    query: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 10,
    config: RunnableConfig = None,  # type: ignore[reportAssignmentType]  # langchain injects at runtime; None default for direct calls
) -> str:
    """
    Search the user's screen/computer activity using vectors when available, otherwise keywords.

    Vector search can find related concepts. Keyword fallback matches content terms
    (stopwords ignored) and scans at most 500 recent screens in the date window
    (default last 7 days). Use concise keywords.

    **When to use:**
    - "When was I last working on the budget spreadsheet?"
    - "Find when I was looking at that Python error"
    - "When did I last use Figma for the landing page design?"
    - "Show me when I was reading about machine learning"

    **When NOT to use:**
    - General "what did I do" questions (use get_screen_activity_tool)
    - Questions about spoken conversations (use search_conversations_tool)

    Args:
        query: Natural language description of what to search for in screen content
        start_date: Optional start date filter, ISO 8601; offsets are converted and a time without an
            offset is in the user's timezone
        end_date: Optional end date filter, same format
        limit: Number of results to return (default 10, max 20)

    Returns:
        Matching screen activity entries with timestamps, app names, and text snippets.
    """
    logger.info("search_screen_activity_tool called")

    uid = _get_uid(config)
    if not uid:
        return "Error: User ID not found in configuration"

    limit = max(1, min(limit, 20))

    # Parse optional date filters to unix timestamps. An unreadable date is an error, never a
    # silently unfiltered search.
    clock = clock_for_config(config or _agent_config(), uid)
    try:
        start_dt = parse_tool_time(start_date, field='start_date', naive_tz=clock.tz)
        end_dt = parse_tool_time(end_date, field='end_date', naive_tz=clock.tz)
    except ToolTimeError as error:
        return f"Error: {error}"
    start_ts = int(start_dt.timestamp()) if start_dt else None
    end_ts = int(end_dt.timestamp()) if end_dt else None

    fallback_enabled = _env_flag_enabled('SCREEN_ACTIVITY_KEYWORD_FALLBACK_ENABLED', default=True)
    reason = None
    matches = []
    if _screen_vectors_disabled(uid):
        reason = 'dispatch_disabled'
    else:
        try:
            query_vector = gemini_embed_query(query)
        except Exception:
            reason = 'capability_mismatch'
        else:
            try:
                matches = vector_db.search_screen_activity_vectors(
                    uid=uid, query_vector=query_vector, start_date=start_ts, end_date=end_ts, k=limit
                )
            except Exception:
                reason = 'provider_5xx'

    # Pinecone metadata is external input: keep the runtime shape check even though the
    # provider signature promises dicts, so a malformed hit never reaches the Firestore lookup.
    valid_matches = [
        m
        for m in cast(List[Any], matches or [])
        if isinstance(m, dict) and _validated_screen_evidence_id(m.get('screenshot_id')) is not None
    ]
    if not valid_matches:
        if not fallback_enabled:
            return 'Screen vector search unavailable or no matches; keyword fallback is disabled.'
        valid_matches, scanned = _keyword_fallback(uid, query, start_ts, end_ts, limit, reason or 'none')
        if valid_matches is None:
            return 'Screen search unavailable: keyword search could not read screens in the requested window.'
        if not valid_matches:
            return f'No matches (keyword search over {scanned} screens in window).'

    # Fetch full metadata from Firestore for matched screenshot IDs
    screenshot_ids = [cast(str, _validated_screen_evidence_id(m.get('screenshot_id'))) for m in valid_matches]
    scores_by_id = {sid: m.get('score', 0) for sid, m in zip(screenshot_ids, valid_matches)}
    app_by_id = {sid: m.get('appName', '') for sid, m in zip(screenshot_ids, valid_matches)}
    ts_by_id = {sid: m.get('timestamp', 0) for sid, m in zip(screenshot_ids, valid_matches)}

    docs_by_id = {m['screenshot_id']: m['keyword_doc'] for m in valid_matches if 'keyword_doc' in m}
    evidence_references = _evidence_references(config)
    result = (
        count_header(
            f"Screen activity matches for '{query}'",
            shown=len(valid_matches),
            order="screen search rank order",
            more_may_exist=len(valid_matches) >= limit,
        )
        + "\n\n"
    )
    has_untrusted = False

    for sid in screenshot_ids:
        score = scores_by_id.get(sid, 0)
        app_name = app_by_id.get(sid, 'Unknown')
        ts = ts_by_id.get(sid, 0)
        captured_at_ms = _normalized_captured_at_ms(ts) if ts else None
        if captured_at_ms is None:
            ts_str = 'Unknown'
        else:
            try:
                ts_str = format_instant(captured_at_ms / 1000, clock)
            except (OverflowError, OSError, ValueError):
                ts_str = 'Unknown'

        # Fetch OCR text from Firestore
        ocr_text = ''
        ocr_preview = ''
        window_title = ''
        raw_ocr: Any = None
        raw_window_title: Any = None
        ocr_lookup_failed = False
        try:
            doc_data = docs_by_id.get(sid)
            if doc_data is None:
                from database.read_boundary import parse_snapshot_or_none

                doc = (
                    firestore_db.collection('users')
                    .document(uid)
                    .collection('screen_activity')
                    .document(str(sid))
                    .get()
                )
                doc_data = parse_snapshot_or_none(dict, doc)
            if doc_data is not None:
                raw_ocr = doc_data.get('ocrText')
                raw_window_title = doc_data.get('windowTitle')
                # Keep the legacy text result's 200-character behavior; the normalized, longer
                # preview is only for the structured evidence reference.
                ocr_text = raw_ocr[:200] if isinstance(raw_ocr, str) else ''
                ocr_preview = _bounded_evidence_text(raw_ocr, MAX_SCREEN_EVIDENCE_SUMMARY_CHARS)
                window_title = _bounded_evidence_text(raw_window_title, MAX_SCREEN_EVIDENCE_TITLE_CHARS)
        except Exception:
            ocr_lookup_failed = True

        result += (
            f"- **{ts_str}** | {app_name} (relevance: {score if score == 'keyword' else _bounded_relevance(score)})\n"
        )
        untrusted_fields, match_has_untrusted = _format_screen_untrusted_fields(
            ocr_text=ocr_text,
            raw_ocr=raw_ocr,
            window_title=window_title,
            raw_window_title=raw_window_title,
            lookup_failed=ocr_lookup_failed,
        )
        result += untrusted_fields
        has_untrusted = has_untrusted or match_has_untrusted
        result += "\n"

        _append_screen_evidence_reference(
            evidence_references,
            screenshot_id=sid,
            captured_at_ms=captured_at_ms,
            app_name=app_name,
            window_title=window_title,
            ocr_preview=ocr_preview,
        )

    if has_untrusted:
        result += "\n" + UNTRUSTED_LEGEND
    if len(valid_matches) >= limit:
        result += "\n" + truncation_note(
            shown=len(valid_matches),
            total=None,
            cut=True,
            unit="screen activity matches",
            how_to_get_more="Narrow the date range or use a more specific query to inspect additional matches.",
        )
    return result.strip()
