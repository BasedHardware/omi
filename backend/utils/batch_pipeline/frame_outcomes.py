"""Experiment ``batch_frame_outcomes``: source-frame verdicts for a completed batch upload.

The status of a completed upload names, per ``(capture_root, clock_epoch)``, which
source frames ended as transcript text and which were evaluated and are empty. A
frame without certain evidence gets no verdict; nothing here infers a position
from capture clocks or file order.

Each piece is called from the production function it extends, behind the switch:

- intake (``accept_upload``) records which source frames each staged unit holds.
  The only other copy is inside the encrypted staged audio, which the status
  route cannot read and which is erased 24 h after projection.
- projection (``Projector.assign_parts``) records, once a part settled, where its
  transcript segments lie on the unit's sample clock. The only other copies are
  the encrypted result artifact and the conversation itself.
- status (``durable_status``) joins both with the unit rows it already read.

Both records live on the upload's intake row, so the polled status read adds no
document read and they expire with the upload.
"""

from collections import defaultdict
import json
import logging

from google.cloud.firestore_v1.field_path import FieldPath

from config import reliability_experiments
from utils.batch_pipeline.contracts import MAX_PROJECTION_PARTS
from utils.batch_pipeline.held_terminal import OPERATOR_INTENTS
from utils.batch_pipeline.repair_lineage import recorded_lineage
from utils.capture_evidence import Span, coverage_union, novel_coverage

logger = logging.getLogger(__name__)

FIELD = 'frame_outcomes_v1'
RUNS_FIELD = 'frame_outcome_runs_v1'
TEXT_FIELD = 'frame_outcome_text_v1'
RATE = 16000
# A unit that finished and that nothing automatic or reviewed can still change.
SETTLED_OUTCOMES = frozenset({'success', 'silence', 'no_recoverable_speech'})
SETTLED_RECOVERY_STATES = (None, 'recovered')
MAX_RUNS_BYTES = 256 * 1024
MAX_PART_SPANS = 1024
MAX_RANGES = 4096


def intake_fields(uid: str, units: dict) -> dict:
    """What an accepted upload adds to its intake row: the frame runs for an account the flag admits, else nothing."""
    return intake_runs(units) if reliability_experiments.enabled('batch_frame_outcomes', uid) else {}


def intake_runs(units: dict) -> dict:
    """Intake-row field for the frames each unit holds, or nothing when no unit has any.

    ``units`` maps a unit's segment id to its ``coverage_runs``. A run becomes
    ``[capture_root, clock_epoch, start, end, sample_start, samples_per_frame]``;
    the list is stored as JSON because Firestore rejects nested arrays.
    """
    rows = {}
    for segment_id, runs in units.items():
        try:
            encoded = [
                [
                    run['key']['capture_root'],
                    int(run['key']['clock_epoch']),
                    run['start'],
                    run['end'],
                    run['sample_start'],
                    run['samples_per_frame'],
                ]
                for run in runs
            ]
        except (KeyError, TypeError, ValueError):
            continue
        if encoded and all(_valid_run(run) for run in encoded):
            rows[segment_id] = encoded
    if not rows:
        return {}
    body = json.dumps(rows, allow_nan=False, sort_keys=True, separators=(',', ':'))
    return {RUNS_FIELD: body} if len(body) <= MAX_RUNS_BYTES else {}


def segment_samples(incoming: dict, capture_at: float) -> list[int] | None:
    """Unit-sample spans of a part's transcript segments as ``[a0, b0, a1, b1, ...]``.

    The same clock arithmetic as ``claims_for_segments``. ``None`` means the spans
    are unknown and the part must stay without a record.
    """
    try:
        origin = incoming['started_at'].timestamp() - capture_at
        spans = []
        for segment in incoming.get('transcript_segments', []):
            start = round((origin + segment['start']) * RATE)
            end = round((origin + segment['end']) * RATE)
            if start < 0 or end < start:
                return None
            # A point word has text but no duration: it still marks its frame.
            spans.append(Span(start, max(end, start + 1)))
        merged = coverage_union(spans)
    except Exception:
        return None
    if len(merged) > MAX_PART_SPANS:
        return None
    return [value for span in merged for value in (span.start, span.end)]


def record_part(store, binding, item, entry: dict, index: int, part_count: int, spans: list[int] | None) -> None:
    """Record one settled part's text spans on the intake row. Never raises.

    A missing record only withholds that unit's verdicts. The record names the
    result it was built from, so a later result for the same unit cannot inherit it.
    """
    if spans is None:
        return
    try:
        store.ref('intakes', binding.job_id).update(
            {
                FieldPath(TEXT_FIELD, item.segment_id, str(index)).to_api_repr(): {
                    'of': part_count,
                    'uri': (entry.get('result') or {}).get('result_uri'),
                    'spans': spans,
                }
            }
        )
    except Exception as error:
        logger.warning(
            'event=batch_frame_outcomes action=record outcome=skipped exception_type=%s', type(error).__name__
        )


def attach(result: dict, intake: dict, jobs: list[dict]) -> dict:
    """A completed result with its frame verdicts, or the result unchanged. Never raises."""
    try:
        ranges = completed_ranges(intake, jobs)
    except Exception as error:
        logger.warning('event=batch_frame_outcomes action=read outcome=skipped exception_type=%s', type(error).__name__)
        return result
    return result if ranges is None else {**result, FIELD: ranges}


def completed_ranges(intake: dict, jobs: list[dict]) -> list[dict] | None:
    """Merged, sorted, non-overlapping verdict ranges; ``None`` when nothing can be attributed.

    ``None`` (field omitted): the upload carried no valid capture-evidence claim or
    no unit-to-frame record. An empty list: both exist, but no frame has a certain
    verdict.
    """
    claimed = _claimed(intake.get('repair_lineage'))
    units = _runs(intake.get(RUNS_FIELD))
    if not claimed or not units:
        return None
    records = intake.get(TEXT_FIELD)
    records = records if isinstance(records, dict) else {}
    by_id = {job.get('segment_id'): job for job in jobs}
    domains, settled, text = defaultdict(list), defaultdict(list), defaultdict(list)
    for segment_id, runs in units.items():
        spans = _unit_text(by_id.get(segment_id) or {}, records.get(segment_id))
        for root, epoch, start, end, sample_start, step in runs:
            key = root, epoch
            frames = Span(start, end)
            if novel_coverage(frames, claimed.get(key, ())):
                # The unit record names frames this upload never claimed.
                return []
            domains[key].append(frames)
            if spans is None:
                continue
            settled[key].append(frames)
            for a, b in spans:
                # Every frame a segment touches is text, including a partly covered one.
                first = start + max(0, (a - sample_start) // step)
                last = min(end, start - ((sample_start - b) // step))
                if first < last:
                    text[key].append(Span(first, last))
    for parts in domains.values():
        # Two units holding the same frames cannot establish which bytes were processed.
        if sum(s.end - s.start for s in parts) != sum(s.end - s.start for s in coverage_union(parts)):
            return []
    ranges = []
    for root, epoch in sorted(settled):
        spoken = coverage_union(text[root, epoch])
        quiet = [gap for span in coverage_union(settled[root, epoch]) for gap in novel_coverage(span, spoken)]
        for status, spans in (('text', spoken), ('empty', quiet)):
            ranges.extend(
                {'capture_root': root, 'clock_epoch': epoch, 'start': s.start, 'end': s.end, 'status': status}
                for s in spans
            )
    if len(ranges) > MAX_RANGES:
        return None
    return sorted(ranges, key=lambda r: (r['capture_root'], r['clock_epoch'], r['start']))


def _claimed(record) -> dict:
    """Frames the upload's valid claims name, per ``(capture_root, clock_epoch)``."""
    try:
        claims = recorded_lineage(record)['capture_evidence_claims']
    except (TypeError, ValueError):
        return {}
    if not isinstance(claims, dict):
        return {}
    spans = defaultdict(list)
    for claim in claims.values():
        if not isinstance(claim, dict):
            continue
        root = claim.get('capture_root')
        epoch, start, count = claim.get('clock_epoch'), claim.get('source_frame_start'), claim.get('frame_count')
        if not isinstance(root, str) or not root:
            continue
        # Whole numbers only; a bool is not a frame count.
        if type(epoch) is not int or type(start) is not int or type(count) is not int:
            continue
        if epoch >= 0 and start >= 0 and count > 0:
            spans[root, epoch].append(Span(start, start + count))
    return {key: coverage_union(parts) for key, parts in spans.items()}


def _valid_run(run) -> bool:
    if not isinstance(run, list) or len(run) != 6:
        return False
    root, epoch, start, end, sample_start, step = run
    return (
        isinstance(root, str)
        and bool(root)
        and all(type(value) is int for value in (epoch, start, end, sample_start, step))
        and epoch >= 0
        and 0 <= start < end
        and sample_start >= 0
        and step > 0
    )


def _runs(body) -> dict:
    try:
        rows = json.loads(body)
    except (TypeError, ValueError):
        return {}
    if not isinstance(rows, dict) or any(
        not isinstance(runs, list) or not all(_valid_run(run) for run in runs) for runs in rows.values()
    ):
        return {}
    return rows


def _unit_text(job: dict, records) -> list[tuple[int, int]] | None:
    """Text spans of a settled unit on its sample clock; ``None`` when the unit has no verdict."""
    result = job.get('result')
    result = result if isinstance(result, dict) else {}
    outcome = result.get('outcome')
    if (
        job.get('state') != 'committed'
        or job.get('recovery_state') not in SETTLED_RECOVERY_STATES
        or outcome not in SETTLED_OUTCOMES
        or job.get('shadow')
        # A reused result was projected for another unit's audio; nothing here ties it to these frames.
        or job.get('source_alias')
        or job.get('source_alias_of')
        or any(
            isinstance(job.get(key), dict) and job[key].get('state') not in {'completed', 'failed_held'}
            for key in OPERATOR_INTENTS
        )
    ):
        return None
    if outcome != 'success':
        return []
    # A unit with words needs a record of every part, built from the result it holds now.
    records = records if isinstance(records, dict) else {}
    first = records.get('0')
    count = first.get('of') if isinstance(first, dict) else None
    if type(count) is not int or not 1 <= count <= MAX_PROJECTION_PARTS:
        return None
    spans = []
    for index in range(count):
        record = records.get(str(index))
        flat = record.get('spans') if isinstance(record, dict) else None
        if (
            not isinstance(record, dict)
            or record.get('of') != count
            or record.get('uri') != result.get('result_uri')
            or not isinstance(flat, list)
            or len(flat) % 2
            or len(flat) > 2 * MAX_PART_SPANS
            or any(type(value) is not int or value < 0 for value in flat)
        ):
            return None
        pairs = list(zip(flat[::2], flat[1::2]))
        if any(a >= b for a, b in pairs):
            return None
        spans.extend(pairs)
    return spans
