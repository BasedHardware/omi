import json
import struct
from typing import Any, Deque, Dict, List, NotRequired, Optional, TypedDict, TypeVar

from utils.metrics import PUSHER_QUEUE_DROPPED_BYTES, PUSHER_QUEUE_DROPS
from utils.observability.journeys import JourneyOutcome
from config.audio_outbox import enabled as audio_outbox_enabled
from utils.other.audio_outbox_metrics import BACKPRESSURE, record_would_drop

PRIVATE_CLOUD_QUEUE_MAX_SIZE = 20  # ~18MB/connection max (30 conns × 18MB = 540MB) — prevents OOM with headroom
MIN_SAMPLE_RATE = 8000
MAX_SAMPLE_RATE = 48000
BUFFERED_AUDIO_MAX_BYTES = 20 * 1024 * 1024
PRIVATE_CLOUD_PENDING_MAX_CONVERSATIONS = PRIVATE_CLOUD_QUEUE_MAX_SIZE

# Audio-timeline v2 wire contract. The opt-in is a bounded WebSocket query
# parameter (an old pusher ignores an unknown key); the answer is a dedicated
# pusher->listen acknowledgment opcode with a fixed version. No new
# listen->pusher opcode exists during negotiation because an old pusher
# rejects unknown opcodes outright.
AUDIO_TIMELINE_QUERY_PARAM = 'audio_timeline'
AUDIO_TIMELINE_PROTOCOL = 2
PUSHER_AUDIO_TIMELINE_ACK_OPCODE = 202
PUSHER_AUDIO_CUSTODY_ACK_OPCODE = 203


def audio_custody_ack_frame(receipt: Dict[str, Any]) -> bytes:
    return struct.pack('<I', PUSHER_AUDIO_CUSTODY_ACK_OPCODE) + json.dumps(
        {'type': 'audio_custody', 'version': 1, 'receipt': receipt}, allow_nan=False
    ).encode('utf-8')


def audio_timeline_ack_frame() -> bytes:
    """The pusher->listen v2 acknowledgment frame (opcode 202 + JSON)."""
    return struct.pack('<I', PUSHER_AUDIO_TIMELINE_ACK_OPCODE) + json.dumps(
        {'type': 'audio_timeline_ack', 'version': AUDIO_TIMELINE_PROTOCOL}
    ).encode('utf-8')


_QueueItem = TypeVar('_QueueItem')


class AudioBackpressure(RuntimeError):
    """No custody transfer: caller/producer must retain and retry the input."""

    def __init__(self, stage: str, pending: Any = None):
        super().__init__('audio custody capacity exhausted; input remains unacknowledged')
        self.pending = pending
        record_would_drop(stage)
        BACKPRESSURE.labels(stage=stage).inc()


class ByteBudget:
    def __init__(self, limit: int):
        self.limit = limit
        self.used = 0

    def reserve(self, size: int) -> bool:
        if size < 0 or self.used + size > self.limit:
            return False
        self.used += size
        return True

    def release(self, size: int) -> None:
        self.used = max(0, self.used - size)


def record_queue_drop(queue_name: str, size: int = 0) -> None:
    PUSHER_QUEUE_DROPS.labels(queue=queue_name).inc()
    if size:
        PUSHER_QUEUE_DROPPED_BYTES.labels(queue=queue_name).inc(size)


def append_bounded(
    queue: Deque[_QueueItem],
    item: _QueueItem,
    queue_name: str,
    *,
    byte_budget: Optional[ByteBudget] = None,
    size_of: Optional[Any] = None,
) -> bool:
    dropped = len(queue) == queue.maxlen
    if dropped:
        if audio_outbox_enabled() and (byte_budget is not None or 'audio' in queue_name or 'private' in queue_name):
            raise AudioBackpressure('pusher_queue', item)
        removed = queue.popleft()
        removed_size = size_of(removed) if size_of else 0
        if byte_budget:
            byte_budget.release(removed_size)
        record_queue_drop(queue_name, removed_size)
    queue.append(item)
    return dropped


def extend_bounded(buffer: bytearray, data: bytes, queue_name: str, byte_budget: ByteBudget) -> bool:
    if not byte_budget.reserve(len(data)):
        if audio_outbox_enabled():
            raise AudioBackpressure('pusher_budget', data)
        record_queue_drop(queue_name, len(data))
        return False
    buffer.extend(data)
    return True


def bound_private_pending(pending: Dict[str, Dict[str, Any]], byte_budget: ByteBudget) -> None:
    if len(pending) < PRIVATE_CLOUD_PENDING_MAX_CONVERSATIONS:
        return
    if audio_outbox_enabled():
        raise AudioBackpressure('pusher_pending')
    oldest_id = next(iter(pending))
    removed = pending.pop(oldest_id)
    removed_size = len(removed['data'])
    byte_budget.release(removed_size)
    record_queue_drop('private_cloud_pending', removed_size)


def frame_header(data: bytes) -> int:
    if len(data) < 4:
        raise ValueError('frame header is incomplete')
    header_type = struct.unpack('<I', data[:4])[0]
    if header_type not in {100, 101, 102, 103, 104, 105}:
        raise ValueError('unknown frame type')
    if header_type == 101 and len(data) < 12:
        raise ValueError('audio frame is incomplete')
    return header_type


def json_object(data: bytes) -> Dict[str, Any]:
    value = json.loads(bytes(data[4:]).decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError('frame payload must be an object')
    return value


def pusher_session_outcome(close_code: int, *, application_failed: bool = False) -> JourneyOutcome:
    """Classify accepted sessions without counting normal disconnects as failures."""
    if application_failed or close_code == 1011:
        return 'failure'
    if close_code in {1000, 1001}:
        return 'success'
    return 'cancelled'


class SpeakerSampleRequest(TypedDict):
    person_id: str
    conversation_id: str
    segment_ids: List[str]
    queued_at: float


class TranscriptQueueItem(TypedDict):
    segments: List[Dict[str, Any]]
    memory_id: Optional[str]


class AudioBytesQueueItem(TypedDict):
    type: str
    sample_rate: int
    data: bytearray


class PrivateCloudSpan(TypedDict):
    samples: int
    sample_rate: int


class PrivateCloudChunk(TypedDict):
    data: bytes
    conversation_id: str
    timestamp: float
    # Audio-timeline v2 only: the chunk's authoritative PCM sample count.
    span: NotRequired[PrivateCloudSpan]
    # Continuity window (per-connection generation) the chunk was buffered
    # under; the pusher reconcile-skip compares it against the conversation's
    # clean-upload window. Always set by the pusher flush path.
    timeline_generation: NotRequired[int]
