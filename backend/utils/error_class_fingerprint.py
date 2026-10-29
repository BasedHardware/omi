"""Error-class fingerprints for prod ERROR+ log entries.

A class is ``exception type + raising site + logger`` when the entry carries an
exception, else ``app level + normalized message template + logger``. Ids,
numbers, addresses, quoted values and digit-bearing slugs are normalized out so
one code defect maps to one class regardless of the per-instance payload.

Container logs arrive one line per entry, so multi-line tracebacks are stitched
back together per source before fingerprinting. Everything here operates on
already-normalized text: fingerprints and labels are the only payload-derived
strings that may leave this module, and they never contain raw log content.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import unquote, urlparse

UUID_RE = re.compile(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')
EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')
IP_RE = re.compile(r'\b\d{1,3}(?:\.\d{1,3}){3}\b')
HEX_RE = re.compile(r'\b[0-9a-fA-F]{12,}\b')
# A slug carries a 4+ digit run AND at least one letter; pure numbers stay
# numbers and pure hex falls through to HEX_RE above.
SLUG_RE = re.compile(r'\b(?=[A-Za-z0-9_-]*[A-Za-z])[A-Za-z0-9_-]*\d{4,}[A-Za-z0-9_-]*\b')
QUOTED_RE = re.compile(r"'[^']*'|\"[^\"]*\"")
NUM_RE = re.compile(r'\b\d+(?:\.\d+)?\b')
WS_RE = re.compile(r'\s+')

LEVEL_LOGGER_RE = re.compile(r'^(DEBUG|INFO|WARNING|ERROR|CRITICAL)(?::|\s)\s*([A-Za-z_][\w.]*)?(?::|\s)\s*(.*)')
EXC_SUFFIX = 'Error|Exception|Conflict|Interrupt|Exit|Failure|Cancelled|Timeout|Refused|Denied|Expired|Reset'
EXC_RE = re.compile(r'^([A-Za-z_][\w.]*(?:' + EXC_SUFFIX + r'))\s*(?::|$)', re.M)
EXC_LINE_RE = re.compile(r'^([A-Za-z_][\w.]*(?:' + EXC_SUFFIX + r'))\s*:')
FRAME_LINE_RE = re.compile(r'^\s+File "([^"]+)", line (\d+), in (\w+)')
FRAME_RE = re.compile(r'File "([^"]+)", line (\d+), in (\w+)')
TRACEBACK_START = 'Traceback (most recent call last):'
SITE_FIELD_RE = re.compile(r'\bsite=([\w./:-]+)')
PYLOC_RE = re.compile(r'\b([\w./-]+\.py):(\d+)')

TEMPLATE_MAX = 100
LABEL_TEMPLATE_MAX = 60
FP_LABEL_MAX = 120


def normalize(text: str) -> str:
    """Replace id-like tokens so templates stay stable across instances."""
    text = UUID_RE.sub('<uid>', text)
    text = EMAIL_RE.sub('<email>', text)
    text = IP_RE.sub('<ip>', text)
    text = HEX_RE.sub('<hex>', text)
    text = SLUG_RE.sub('<id>', text)
    text = QUOTED_RE.sub('<q>', text)
    text = NUM_RE.sub('<n>', text)
    return WS_RE.sub(' ', text).strip()


def _first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ''


def extract_exception(text: str) -> str | None:
    """Last exception-like line wins: it is the raised exception, not a cause."""
    exc = None
    for match in EXC_RE.finditer(text):
        exc = match.group(1).rsplit('.', 1)[-1]
    return exc


def extract_site(text: str, payload: Mapping[str, Any] | None = None) -> str | None:
    """Raising site: innermost traceback frame, ``site=`` field, or file:line."""
    frames = FRAME_RE.findall(text)
    if frames:
        path, line, _ = frames[-1]
        return '%s:%s' % (path.rsplit('/', 1)[-1].rsplit('\\', 1)[-1], line)
    match = SITE_FIELD_RE.search(text)
    if match:
        return match.group(1)
    for key in ('site', 'location', 'where'):
        value = (payload or {}).get(key)
        if value:
            return str(value)
    match = PYLOC_RE.search(text)
    if match:
        return '%s:%s' % (match.group(1).rsplit('/', 1)[-1], match.group(2))
    return None


@dataclass(frozen=True)
class ErrorClassFingerprint:
    fingerprint: str
    label: str
    level: str
    exception: str | None


def entry_text(entry: Mapping[str, Any]) -> str:
    """Best-effort message text from a Cloud Logging entry, never the payload."""
    if entry.get('textPayload'):
        return str(entry['textPayload'])
    payload = entry.get('jsonPayload') or {}
    if 'message' in payload:
        return str(payload['message'])
    proto = entry.get('protoPayload') or {}
    parts = []
    if proto.get('statusMessage'):
        parts.append(str(proto['statusMessage']))
    if proto.get('requestUrl'):
        # Path only: scheme and host churn would split one class in two.
        parts.append('url ' + urlparse(str(proto['requestUrl'])).path)
    return '\n'.join(parts)


def entry_logger(entry: Mapping[str, Any]) -> str:
    payload = entry.get('jsonPayload') or {}
    if payload.get('logger'):
        return str(payload['logger'])
    log_name = unquote(entry.get('logName') or '')
    return log_name.rsplit('/', 1)[-1] if log_name else '-'


def fingerprint_entry(entry: Mapping[str, Any]) -> ErrorClassFingerprint:
    """Classify one log entry (already traceback-stitched) into a class."""
    text = entry_text(entry)
    log_name = entry_logger(entry)
    first = _first_line(text)
    match = LEVEL_LOGGER_RE.match(first)
    if match:
        level, logger, rest = match.group(1), match.group(2), match.group(3)
    else:
        # No app-level prefix: keep the whole (multi-line) text so entries like
        # request-log "status + url" pairs stay in one template.
        level, logger, rest = '?', None, text
    exc = extract_exception(text)
    site = extract_site(text, entry.get('jsonPayload') or {})
    if exc:
        source = logger or log_name
        return ErrorClassFingerprint(
            fingerprint=('%s|%s|%s' % (exc, site or '-', source))[:FP_LABEL_MAX],
            label='%s at %s [%s]' % (exc, site or '?', source),
            # Keep the parsed app level so warning-threshold gating still
            # applies to exceptions logged at WARNING.
            level=level,
            exception=exc,
        )
    template = normalize(rest or first)[:TEMPLATE_MAX] or '<empty>'
    source = logger or log_name
    return ErrorClassFingerprint(
        fingerprint=('%s|%s|%s' % (level, template, source))[:FP_LABEL_MAX],
        label='%s %s: %s' % (level, source, template[:LABEL_TEMPLATE_MAX]),
        level=level,
        exception=None,
    )


def entry_source_key(entry: Mapping[str, Any]) -> str:
    """Entries from the same container interleave; stitching groups by source."""
    return json.dumps(entry.get('resource', {}).get('labels', {}), sort_keys=True)


def stitch_tracebacks(entries: list[dict]) -> list[dict]:
    """Reassemble per-source traceback blocks so exception and site join.

    Container stdout/stderr is one Cloud Logging entry per line. A block starts
    at the marker line, collects indented frame lines, and closes at the
    exception line, which carries the class; frame-only output without a
    closing exception line is flushed unchanged. Non-block lines pass through.
    A level-header line ("WARNING x: ...") immediately preceding the marker is
    absorbed into the block so the app level survives into the fingerprint -
    without it, a warning-logged exception would use the standard thresholds.
    """
    out: list[dict | None] = []
    blocks: dict[str, list[str]] = {}
    last_header: dict[str, tuple[int, str]] = {}
    for entry in entries:
        if not entry.get('textPayload'):
            out.append(entry)
            continue
        key = entry_source_key(entry)
        line = str(entry['textPayload']).rstrip('\n')
        pending = blocks.get(key)
        if line == TRACEBACK_START or line.endswith(TRACEBACK_START):
            head = last_header.pop(key, None)
            if head is not None:
                position, header = head
                out[position] = None  # absorbed into the block below
                blocks[key] = [header, line]
            else:
                blocks[key] = [line]
            continue
        if pending is not None:
            if FRAME_LINE_RE.match(line) or line.startswith('    ') or EXC_LINE_RE.match(line):
                pending.append(line)
                if EXC_LINE_RE.match(line):
                    merged = dict(entry)
                    merged['textPayload'] = '\n'.join(pending)
                    out.append(merged)
                    blocks.pop(key, None)
                continue
            merged = dict(entry)
            merged['textPayload'] = '\n'.join(pending)
            out.append(merged)
            blocks.pop(key, None)
        # Only the immediately preceding line from this source can be the
        # header of the block: any other pass-through line clears the candidate.
        if LEVEL_LOGGER_RE.match(line):
            last_header[key] = (len(out), line)
        else:
            last_header.pop(key, None)
        out.append(entry)
    for key, lines in blocks.items():
        if len(lines) > 1:
            out.append({'resource': {'labels': json.loads(key)}, 'textPayload': '\n'.join(lines)})
    return [entry for entry in out if entry is not None]
