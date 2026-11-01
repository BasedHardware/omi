# LIFECYCLE: permanent
"""Accepted-send bookkeeping for raw legacy replay, before live-tail adoption."""

from typing import Any, Callable, Sequence, cast

from config.audio_timeline import live_capture_window_translator_sends_enabled
from utils.audio_timeline import ProviderEpochTranslator


class ObservedReplaySocket:
    """Delegate transport admission unchanged; register only observed accepted PCM.

    Managed legs already account for their own gated/replayed bytes. This wrapper
    is only for raw replacements, whose prefix previously bypassed bookkeeping.
    It deliberately bypasses VAD: replay chunks carry their original admission.
    """

    def __init__(self, raw: Any, epoch: ProviderEpochTranslator):
        self.raw = raw
        self.epoch = epoch

    def __getattr__(self, name: str) -> Any:
        return getattr(self.raw, name)

    def send(self, data: bytes, start_sample: int | None = None) -> bool:
        try:
            accepted = self.raw.send(data, start_sample=start_sample)
        except TypeError:
            accepted = self.raw.send(data)
        self._record(accepted, data, start_sample)
        return accepted

    def replay_send(self, data: bytes, start_sample: int) -> bool:
        replay = getattr(self.raw, 'replay_send', None)
        if not callable(replay):
            return self.send(data, start_sample=start_sample)
        accepted = cast(Callable[[bytes, int], bool], replay)(data, start_sample)
        self._record(accepted, data, start_sample)
        return accepted

    def _record(self, accepted: bool, data: bytes, start: int | None) -> None:
        if (
            accepted is True
            and start is not None
            and len(data) >= 2
            and len(data) % 2 == 0
            and 0 <= start < start + len(data) // 2 <= self.epoch.timeline.next_sample
        ):
            note_observed_spans(self.epoch, ((start, len(data) // 2),), 'replay_failover')


def record_replay_sends(raw: Any, epoch: ProviderEpochTranslator | None) -> Any:
    """Default-off; managed legs and absent clocks keep their exact send path."""
    if not live_capture_window_translator_sends_enabled() or epoch is None or getattr(raw, 'manages_vad', False):
        return raw
    return ObservedReplaySocket(raw, epoch)


def note_observed_spans(epoch: ProviderEpochTranslator, spans: Sequence[tuple[int, int]], send_path: str) -> None:
    """An admission cannot grant capture proof beyond receiver-observed samples."""
    if spans and all(
        length > 0 and 0 <= start < start + length <= epoch.timeline.next_sample for start, length in spans
    ):
        epoch.require_observed_send_mapping = True
        epoch.send_path = send_path
        epoch.note_accepted_spans(spans)
