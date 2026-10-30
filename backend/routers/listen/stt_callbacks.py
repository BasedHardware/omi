"""STT callback factory for ``ListenReceiver``.

Kept out of receiver.py for the file budget; every helper reads the receiver it
was built for, so the module stays a pure call-site with no state of its own.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from config.audio_timeline import live_capture_window_strict_projection_enabled
from utils.audio_timeline import CaptureTimeline, ProviderEpochTranslator
from utils.metrics import (
    AUDIO_TIMELINE_REJECT_REASONS,
    OMI_AUDIO_TIMELINE_MAPPED_TOTAL,
    OMI_AUDIO_TIMELINE_PAST_SEND_TOTAL,
    OMI_AUDIO_TIMELINE_OUTSIDE_SENDS_TOTAL,
    OMI_AUDIO_TIMELINE_REJECTS_TOTAL,
    OMI_AUDIO_TIMELINE_SEGMENTS_TOTAL,
    audio_timeline_past_send_bucket,
    audio_timeline_provider_label,
    audio_timeline_send_path_label,
)
from utils.stt.speaker_identity import SpeakerProviderEpoch
from utils.stt.streaming import make_stream_callback


def build_stt_callbacks(receiver: Any) -> Tuple[Any, Any, Optional[ProviderEpochTranslator]]:
    """Fresh legacy callbacks bound to one provider epoch's translator.

    Every selected socket — initial fallback and send-path failover — gets
    its own epoch translator created at callback-creation time, so a late
    callback from an obsolete epoch can never be mapped through a later
    epoch's accepted send spans. Without a capture timeline the callbacks
    keep today's gate-remapping behavior exactly.

    With the clock on and v2 persistence off (flag-off prod), the
    non-passthrough callback keeps today's ``make_stream_callback``
    semantics: the active gate's ``remap_segments`` runs on provider
    timestamps before anything is persisted or emitted, and the epoch
    translation only *attaches* the capture window (it never rewrites
    ``start``/``end``), so stored and WebSocket times are byte-identical
    to the flag-off baseline. With v2 on, the send-map translation
    replaces the gate mapper — both must never apply.

    Each build also mints one SpeakerProviderEpoch: a reconnect under the
    same provider name opens a fresh scope, and a late callback from a dead
    stream stamps its own scope instead of the current epoch's.
    """
    stream_epoch = SpeakerProviderEpoch()
    receiver.speaker_provider_epoch = stream_epoch
    timeline = receiver.capture_timeline
    if timeline is None:

        def plain(segments: List[Dict[str, Any]]) -> None:
            receiver._enqueue_stt_segments(segments, speaker_epoch=stream_epoch)

        return (
            make_stream_callback(plain, receiver.vad_gate, False),
            make_stream_callback(plain, receiver.vad_gate, True),
            None,
        )

    def record_reject(reason: str) -> None:
        mode = 'v2' if receiver.capture_timeline_v2 else 'legacy'
        OMI_AUDIO_TIMELINE_SEGMENTS_TOTAL.labels(mode=mode, outcome='rejected').inc()
        OMI_AUDIO_TIMELINE_REJECTS_TOTAL.labels(
            mode=mode,
            reason=reason if reason in AUDIO_TIMELINE_REJECT_REASONS else 'other',
            provider=audio_timeline_provider_label(epoch.provider_label),
            send_path=audio_timeline_send_path_label(epoch.send_path),
        ).inc()

    def record_mapped() -> None:
        OMI_AUDIO_TIMELINE_MAPPED_TOTAL.labels(
            mode='v2' if receiver.capture_timeline_v2 else 'legacy',
            provider=audio_timeline_provider_label(epoch.provider_label),
            send_path=audio_timeline_send_path_label(epoch.send_path),
        ).inc()
        if not receiver.capture_timeline_v2:
            OMI_AUDIO_TIMELINE_SEGMENTS_TOTAL.labels(mode='legacy', outcome='mapped').inc()

    def record_recovered(reason: str) -> None:
        OMI_AUDIO_TIMELINE_SEGMENTS_TOTAL.labels(mode='v2', outcome='recovered').inc()

    epoch = ProviderEpochTranslator(
        timeline,
        int(receiver.host.request.sample_rate),
        on_reject=record_reject,
        on_mapped=record_mapped,
        on_recover=record_recovered,
        on_past_send=lambda seconds: OMI_AUDIO_TIMELINE_PAST_SEND_TOTAL.labels(
            provider=audio_timeline_provider_label(epoch.provider_label),
            send_path=audio_timeline_send_path_label(epoch.send_path),
            bucket=audio_timeline_past_send_bucket(seconds),
        ).inc(),
        on_outside=lambda subreason: OMI_AUDIO_TIMELINE_OUTSIDE_SENDS_TOTAL.labels(
            provider=audio_timeline_provider_label(epoch.provider_label),
            send_path=audio_timeline_send_path_label(epoch.send_path),
            subreason=subreason,
        ).inc(),
        owner_at_send=receiver._proven_send_owner,
        project_times=receiver.capture_timeline_v2,
    )
    epoch.set_validation_callback(
        lambda provider, interval: receiver._record_elapsed_validation(provider, interval, receiver.vad_gate)
    )
    epoch.provider_label = audio_timeline_provider_label(getattr(receiver.host.stt_service, 'value', None))

    if receiver.capture_timeline_v2:
        # v2: the translation projects start/end onto the capture wall
        # axis; the gate's provider-time mapper must not also apply.
        def translate_and_enqueue(segments: List[Dict[str, Any]]) -> None:
            translated = epoch.translate(segments)
            if translated:
                receiver._enqueue_translated_segments(
                    translated, provider=epoch.provider_label, speaker_epoch=stream_epoch
                )

        return (
            receiver._loop_hop(translate_and_enqueue),
            receiver._loop_hop(translate_and_enqueue),
            epoch,
        )

    def clock_only(passthrough: bool):
        def translate_remap_enqueue(segments: List[Dict[str, Any]]) -> None:
            # Attach the capture window from the *provider* timestamps
            # (they index the accepted send spans); start/end are not
            # rewritten, so the gate remap below sees exactly the values
            # origin/main's make_stream_callback saw.
            translated = epoch.translate(segments)
            if not translated:
                return
            if epoch.replay_origin_sample is not None:
                epoch.stitch_replayed_timestamps(translated)
            elif receiver.vad_gate is not None and not passthrough:
                receiver.vad_gate.remap_segments(translated)
            receiver._enqueue_clock_positioned_segments(
                translated, provider=epoch.provider_label, speaker_epoch=stream_epoch
            )

        return translate_remap_enqueue

    return (
        receiver._loop_hop(clock_only(False)),
        receiver._loop_hop(clock_only(True)),
        epoch,
    )


def attach_legacy_capture_window(segment: Dict[str, Any], timeline: CaptureTimeline) -> None:
    """Project translator-proven samples; preserve the original refusal when absent."""
    start_sample = segment.pop('_capture_start_sample', None)
    end_sample = segment.pop('_capture_end_sample', None)
    if start_sample is not None and end_sample is not None and end_sample >= start_sample:
        window = timeline.project_window(
            start_sample, end_sample, strict=live_capture_window_strict_projection_enabled()
        )
        if window is not None:
            segment['_capture_abs_start'], segment['_capture_abs_end'] = window
            return
        segment['_capture_window_reason'] = (
            'anchor_compacted' if timeline.wall_strict(start_sample) is None else 'translator_discontinuous_interval'
        )
    segment['_capture_window_unavailable'] = True
