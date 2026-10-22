"""Atomically delegate a frozen held piece to hash-fenced uncovered source slices."""

from bisect import bisect_left, bisect_right
import hashlib
import json
import wave

from utils.capture.sync_coverage import failed
from utils.executors import run_blocking, storage_executor
from utils.sync.held_coverage import covered_receipt, observe
from utils.sync.files import get_timestamp_from_path

MAX_CHILDREN = 32
MAX_PLAN_PIECES = 256
MAX_CHECKPOINT_BYTES = 600_000


def attempt_floor(entry):
    value = entry.get('coverage_attempt_floor', 1)
    return value if type(value) is int and value in (1, 2) else 1


def children(uid, hold_id, name, path, context, entry, decision, attempt):
    from utils.encryption import encrypt

    if not 0 < len(decision.uncovered) <= MAX_CHILDREN or not entry.get('audio_path'):
        raise ValueError('bounded held source slices required')
    timestamp = float(get_timestamp_from_path(path))
    rate = decision.mapping['claim']['rate_hz']
    original_start = (entry.get('source_slice') or {}).get('start', 0)
    result = {}
    with wave.open(path, 'rb') as audio:
        for low, high in decision.uncovered:
            relative, count = low - decision.sample_start, high - low
            audio.setpos(relative)
            payload = audio.readframes(count)
            if len(payload) != count * 2:
                raise ValueError('held source slice truncated')
            offsets = decision.mapping['offsets']
            first, last = bisect_right(offsets, low) - 1, bisect_left(offsets, high)
            base = offsets[first]
            compact = {
                **decision.mapping,
                'claim': {
                    **decision.mapping['claim'],
                    'source_frame_start': decision.mapping['claim']['source_frame_start'] + first,
                    'frame_count': last - first,
                },
                'offsets': [value - base for value in offsets[first : last + 1]],
            }
            child_context = {**context, 'source_position_map': (compact, low - base)}
            selection = {
                'start': original_start + relative,
                'frames': count,
                'sha256': hashlib.sha256(payload).hexdigest(),
            }
            identity = hashlib.sha256(
                json.dumps([hold_id, name, selection, child_context], sort_keys=True, separators=(',', ':')).encode()
            ).hexdigest()
            child_name = f'coverage-{identity[:24]}_{timestamp + relative / rate:.9f}.wav'
            fields = {
                key: value for key, value in entry.items() if key not in ('metadata_path', 'metadata', 'source_slice')
            }
            result[child_name] = {
                **fields,
                'metadata': encrypt(json.dumps(child_context, sort_keys=True), uid),
                'seconds': count / rate,
                'source_slice': selection,
                'coverage_attempt_floor': attempt,
            }
    return result


async def delegate(uid, snapshot, row, piece, plan, receipts, processed, *, save):
    """No parent ACK exists until every child pointer commits in the same fence."""
    name, path, context, decision, attempt = piece
    try:
        additions = await run_blocking(
            storage_executor, children, uid, snapshot.id, name, path, context, plan[name], decision, attempt
        )
        if set(additions).intersection(plan) or len(plan) + len(additions) > MAX_PLAN_PIECES:
            raise ValueError('held child plan capacity exceeded')
        parent = {
            **covered_receipt(receipts.get(name)),
            'coverage_committed': False,
            'coverage_delegated': True,
            'coverage_children': sorted(additions),
        }
        next_plan = {**plan, **additions}
        next_receipts = {**receipts, name: parent}
        next_processed = sorted(processed | {name})
        updates = {'piece_plan': next_plan, 'piece_receipts': next_receipts, 'processed_paths': next_processed}
        if len(json.dumps({**row, **updates}, separators=(',', ':')).encode()) > MAX_CHECKPOINT_BYTES:
            raise ValueError('held child checkpoint capacity exceeded')
        if not await save(uid, snapshot, row, updates):
            return False
        plan.update(additions)
        receipts.update(next_receipts)
        processed.add(name)
        observe(decision, 'sync', 'skipped')
        return True
    except Exception as error:
        failed('held_split', error)
        return False
