"""Managed live-leg construction, VAD ownership and provider epoch timelines."""

from __future__ import annotations

import asyncio
import os
import time
from typing import TYPE_CHECKING, Any, Awaitable, Callable, cast

from starlette.websockets import WebSocketState

from utils.observability.fallback import FirstTextDeadlineDiagnostics, ReplayLagDiagnostics, record_fallback
from utils.observability.transcription import record_live_stt_audio_seconds
from utils.observability.routing_cohort import current_routing_cohort
from utils.stt import streaming as st
from utils.stt.live_failure import PendingLiveFailover, settle_terminal_socket
from utils.stt.live_outcome import LiveLegOutcome, record_managed_leg_handoff
from utils.stt.live_metrics import MANAGED_LEGS_OPEN
from utils.stt.live_reason import normalize_live_stt_reason
from utils.stt.live_rollout import window_allocation, window_language_supported
from utils.stt import replay_delivery
from utils.stt.replay_delivery import abort_replay_socket
from utils.stt.resilient_stream import trim_window_replay_to_anchor
from utils.stt.live_health import health, bounded_language
from utils.stt.live_router import connecting_target, target_circuit, TargetEngineMismatch, engine_matches
from utils.stt.live_target_connect import connect_modulate
from config.live_stt_registry import DEFAULT_IDS, Target, routing_on
from config.audio_timeline import soniox_wire_ledger_enabled
from utils.stt.soniox_wire_ledger import capture_spans
from utils.stt.soniox_capture_axis import disable_socket_diagnostics, enabled as capture_axis_diagnostics_enabled
from config.live_stt_replay import ReplayLimits
from config.audio_timeline import live_capture_window_translator_sends_enabled
from config.live_stt_recovery import session_recovery_enabled
from utils.stt.recovery_state import current_recovery
from utils.stt.stream_close import ACCOUNT_REJECTION_REASONS
from utils.stt.no_text_rescue import NoTextRescue
from utils.stt.replay_capture_accounting import note_observed_spans
from utils.stt.socket import STTSocket, record_live_stt_socket_closed, record_live_stt_socket_open
from utils.stt.speaker_identity import SpeakerProviderEpoch
from utils.stt.vad_gate import VAD_GATE_MODE, VADStreamingGate, is_gate_enabled
from utils.transcribe_decisions import should_initialize_vad_gate, vad_gate_mode

if TYPE_CHECKING:
    from utils.stt.parakeet_window import SessionPcmGain

# Windowed TDT admits speech-only audio with a short hangover. The billed Deepgram
# gate keeps VAD_GATE_SPEECH_THRESHOLD (0.65) and a 4s tail; this leg keeps the same
# start threshold but a much shorter tail, because a growing window re-posts its own
# prefix and does not need 4s of trailing silence to avoid clipping a word.
#
# The threshold was briefly lowered to 0.5/0.35 to admit quiet far-field speech. That
# is no longer what admits it: the gate now scores a level-corrected copy (see
# SessionPcmGain), which lifts far-field admission from 73.7s to 91.7s on its own. The
# extra hysteresis bought only 5.6s more on that clip while costing words on dense
# speech, so the start threshold stays at the Deepgram value and gain does the work.
WINDOW_VAD_HANGOVER_MS = 300
WINDOW_VAD_SPEECH_THRESHOLD = 0.65
WINDOW_VAD_CONTINUE_THRESHOLD = 0.65


class LiveChainSession:
    def __init__(self, receiver: Any) -> None:
        self.receiver = receiver
        self.recovery_enabled = session_recovery_enabled(receiver)
        self.no_text_rescue = NoTextRescue(recovery_enabled=self.recovery_enabled)
        if not hasattr(receiver, '_stt_failed_targets'):
            receiver._stt_failed_targets = set()
        self.audio_seconds = 0.0
        self.last_end = 0.0
        self.generation = 0
        self.speech_ms = 0
        self.total_speech_ms = 0
        self.vad_mode = 'off'
        self._routing_target_entry: Target | None = None

    def consume_speech_ms_delta(self) -> int:
        delta, self.speech_ms = self.speech_ms, 0
        return delta

    def get_metrics(self) -> dict[str, Any]:
        return {'mode': self.vad_mode, 'speech_ms_total': self.total_speech_ms}

    def to_json_log(self) -> dict[str, Any]:
        return {'event': 'managed_live_vad_metrics', **self.get_metrics()}

    async def connect(
        self, sample_rate: int, epoch: Any = None, *, same_provider: bool = False, replay_start_sample: int = 0
    ) -> STTSocket:
        host = self.receiver.host
        constructed: list[LiveLegSocket] = []
        language = host.stt_language
        uid = host.request.uid
        models = [m.strip() for m in st.stt_service_models]
        keywords: list[str] = host.vocabulary[:100] if host.vocabulary else []
        dg_model = st.deepgram_fallback_model(language)
        window_eligible = (
            window_allocation(uid)
            and window_language_supported(host.language, language)
            and bool(os.getenv('HOSTED_PARAKEET_API_URL'))
        )
        rnnt_eligible = st.parakeet_is_configured_fallback(language)
        parakeet_models = ([host.stt_model] if host.stt_service == st.STTService.parakeet else []) + models
        parakeet_token = next(
            (
                token
                for token in parakeet_models
                if (token == 'parakeet-window' and window_eligible) or (token == 'parakeet' and rnnt_eligible)
            ),
            None,
        )
        window = parakeet_token == 'parakeet-window'
        parakeet_allowed = parakeet_token is not None
        engine_models = {
            'parakeet': parakeet_token,
            'modulate': 'velma-2',
            'soniox': 'soniox',
            'deepgram': dg_model,
        }
        if any(token in models for token in ('parakeet', 'parakeet-window')) and not parakeet_allowed:
            record_fallback(
                component='stt_selection',
                from_mode='parakeet',
                to_mode=host.stt_service.value,
                reason=(
                    'capability_mismatch'
                    if not (
                        window_language_supported(host.language, language)
                        if 'parakeet-window' in models
                        else st.parakeet_supports_language(st.STTServingSurface.STREAMING, language)
                    )
                    else 'allocation_rejected'
                ),
                outcome='degraded',
            )
        generation = self.generation + 1
        offset = replay_start_sample / sample_rate if same_provider else self.audio_seconds

        def build_gate(is_window: bool) -> VADStreamingGate | None:
            if is_window:
                # No four-second silence tail: each early-flushed window must
                # contain speech, with only a short boundary hangover.
                gate = VADStreamingGate(
                    sample_rate=sample_rate,
                    channels=1,
                    mode='active',
                    speech_threshold=WINDOW_VAD_SPEECH_THRESHOLD,
                    continue_threshold=WINDOW_VAD_CONTINUE_THRESHOLD,
                    hangover_ms=WINDOW_VAD_HANGOVER_MS,
                )
                self.vad_mode = 'active'
                return gate
            override = getattr(getattr(host, 'request', None), 'vad_gate_override', None)
            if not should_initialize_vad_gate(override=override, global_gate_enabled=is_gate_enabled()):
                replay_ring = getattr(self.receiver, '_window_ring', None)
                if callable(replay_ring) and replay_ring() is not None:
                    # Accounting only: downstream providers still receive
                    # every byte and no new finalize signals. Otherwise an
                    # idle replacement with VAD disabled treats all silence
                    # as pending speech and fills the retained window ring.
                    self.vad_mode = 'shadow'
                    return VADStreamingGate(
                        sample_rate=sample_rate,
                        channels=1,
                        mode='shadow',
                        speech_threshold=WINDOW_VAD_SPEECH_THRESHOLD,
                        continue_threshold=WINDOW_VAD_CONTINUE_THRESHOLD,
                    )
                self.vad_mode = 'off'
                return None
            try:
                gate = VADStreamingGate(
                    sample_rate=sample_rate,
                    channels=1,
                    mode=vad_gate_mode(override=override, default_mode=VAD_GATE_MODE),
                )
            except Exception:
                self.vad_mode = 'off'
                record_fallback(
                    component='vad', from_mode='gated', to_mode='direct', reason='config_incomplete', outcome='degraded'
                )
                return None
            self.vad_mode = gate.mode
            return gate

        async def build(service: st.STTService) -> STTSocket:
            is_window = service == st.STTService.parakeet and window
            stream_epoch = SpeakerProviderEpoch()
            target = connecting_target.get()
            if target is not None and (
                target.family != service.value
                or not engine_matches(target, engine_models)
                or (target.id == 'parakeet-window' and not os.getenv('HOSTED_PARAKEET_API_URL'))
            ):
                raise TargetEngineMismatch('Selected target differs from the session engine')
            try:
                gate = build_gate(is_window)
            except Exception:
                if is_window:
                    raise st.ParakeetConnectionError('config_incomplete')
                gate = None
                self.vad_mode = 'off'
                record_fallback(
                    component='vad', from_mode='gated', to_mode='direct', reason='config_incomplete', outcome='degraded'
                )
            passthrough = service == st.STTService.modulate
            if epoch is not None:
                epoch.set_validation_callback(
                    lambda provider, interval: self.receiver._record_elapsed_validation(provider, interval, gate)
                )

            def callback(segments: list[dict[str, Any]]) -> None:
                if leg.retired_for_replay:
                    return
                if generation != self.generation and not (epoch is not None and epoch.project_times):
                    return
                if epoch is not None:
                    epoch.provider_label = service.value
                if epoch is not None and epoch.project_times:
                    # Audio-timeline v2: the translator maps provider
                    # times through its accepted send spans onto the capture
                    # timeline's wall axis. It replaces this leg's own
                    # offset/last_end clock, so no generation offset is added.
                    # The translate itself reads unsynchronized timeline state,
                    # so it runs on the listen loop (Deepgram calls this from
                    # its SDK thread); the enqueue then follows the receiver's
                    # pinned persistence mode (v2 owner fencing vs clock-only).
                    def translate_on_loop(seg_list: list[dict[str, Any]]) -> None:
                        if leg.retired_for_replay:
                            return
                        translated = epoch.translate(seg_list)
                        if translated:
                            leg.note_selection_transcript(translated)
                            self.receiver._enqueue_epoch_segments(
                                translated, provider=service.value, speaker_epoch=stream_epoch
                            )

                    self.receiver._run_on_listen_loop(translate_on_loop, segments)
                    return
                if epoch is not None:
                    # Clock-only capture clock: attach the window from the
                    # provider's own timestamps, then keep this leg's legacy
                    # offset/last_end rebase (and gate remap) exactly as the
                    # pre-timeline managed chain did — flag-off emitted times
                    # stay monotonic across legs and byte-identical to main.
                    def attach_then_rebase(seg_list: list[dict[str, Any]]) -> None:
                        if leg.retired_for_replay:
                            return
                        translated = epoch.translate(seg_list)
                        if not translated:
                            return
                        if epoch.replay_origin_sample is not None:
                            epoch.stitch_replayed_timestamps(translated)
                        elif gate is not None and not passthrough:
                            gate.remap_segments(translated)
                        translated.sort(key=lambda item: item['start'])
                        for segment in translated:
                            segment_offset = 0.0 if epoch.replay_origin_sample is not None else offset
                            start = max(self.last_end, segment_offset + max(0.0, float(segment['start'])))
                            end = max(start, segment_offset + max(0.0, float(segment['end'])))
                            segment['start'], segment['end'] = start, end
                            self.last_end = end
                        leg.note_selection_transcript(translated)
                        self.receiver._enqueue_epoch_segments(
                            translated, provider=service.value, speaker_epoch=stream_epoch
                        )

                    self.receiver._run_on_listen_loop(attach_then_rebase, segments)
                    return
                if gate is not None and not passthrough:
                    gate.remap_segments(segments)
                segments.sort(key=lambda item: item['start'])
                for segment in segments:
                    start = max(self.last_end, offset + max(0.0, float(segment['start'])))
                    end = max(start, offset + max(0.0, float(segment['end'])))
                    segment['start'], segment['end'] = start, end
                    self.last_end = end
                leg.note_selection_transcript(segments)
                self.receiver._enqueue_stt_segments(segments, provider=service.value, speaker_epoch=stream_epoch)

            raw = None
            try:
                if is_window:
                    from utils.stt.parakeet_window import connect_window

                    raw = connect_window(callback, sample_rate)
                    if self.no_text_rescue.enabled:
                        raw.allow_no_text_rescue = self.no_text_rescue.allow_window_rescue
                        raw.progress_deadline_enabled = True
                elif service == st.STTService.parakeet:
                    raw = await st.process_audio_parakeet(callback, language, sample_rate, 1, keywords=keywords)
                elif service == st.STTService.soniox:
                    raw = await st.process_audio_soniox(
                        callback,
                        sample_rate,
                        language,
                        profile=host.language_profile,
                        keywords=keywords,
                        idle_budget=getattr(self.receiver, 'soniox_idle_budget', None),
                    )
                elif service == st.STTService.modulate:
                    raw = await connect_modulate(callback, sample_rate, language)
                else:
                    raw = await st.process_audio_dg(
                        callback,
                        language,
                        sample_rate,
                        1,
                        model=dg_model or host.stt_model,
                        keywords=keywords,
                        is_active=lambda: host.state.active,
                    )
                if raw is None:
                    raise RuntimeError('Provider returned no socket')
                if epoch is not None:
                    # The selected fallback may differ from the receiver's
                    # initial service. Set its clock policy before first send.
                    epoch.provider_label = service.value
                leg = LiveLegSocket(raw, gate, self, service, sample_rate, is_window, passthrough, send_tracker=epoch)
                leg.speaker_provider_epoch = stream_epoch
                replay_ring = getattr(self.receiver, '_window_ring', None)
                if not is_window and callable(replay_ring) and replay_ring() is not None:
                    # An empty snapshot still carries the obligation to retain
                    # future speech until this replacement emits text.
                    leg.enable_window_replay_tracking()
                constructed.append(leg)
                return leg
            except BaseException:
                if raw is not None:
                    raw.finish()
                raise

        callbacks: dict[st.STTService, Callable[[], Awaitable[STTSocket]] | None] = {
            st.STTService.parakeet: (lambda: build(st.STTService.parakeet)) if parakeet_allowed else None,
            st.STTService.soniox: (
                (lambda: build(st.STTService.soniox)) if 'soniox' in models and os.getenv('SONIOX_API_KEY') else None
            ),
            st.STTService.modulate: (
                (lambda: build(st.STTService.modulate))
                if st.modulate_is_configured_fallback(language) and os.getenv('MODULATE_API_KEY')
                else None
            ),
            st.STTService.deepgram: (lambda: build(st.STTService.deepgram)) if dg_model else None,
        }
        if self.no_text_rescue.returning:
            # The lease is exhausted. Failback cannot silently re-admit a
            # paid successor when cheap capacity/permission is unavailable.
            callbacks = {
                service: callback if service == st.STTService.parakeet else None
                for service, callback in callbacks.items()
            }
            models = ['parakeet-window']
        primary = callbacks.get(host.stt_service)
        primary_missing = primary is None
        if primary_missing:

            async def unavailable() -> STTSocket:
                raise st.ParakeetConnectionError('config_incomplete')

            primary = unavailable
        try:
            if same_provider:
                if primary_missing:
                    raise st.ParakeetConnectionError('config_incomplete')
                try:
                    target = self._routing_target_entry if routing_on(uid) else None
                except ValueError:
                    target = None
                recovery = current_recovery.get()
                if recovery is not None:
                    if target is not None:
                        identity = target.id
                    elif host.stt_service.value == 'parakeet':
                        identity = engine_models.get('parakeet') or 'parakeet'
                    else:
                        identity = DEFAULT_IDS.get(host.stt_service.value) or host.stt_service.value
                    if not recovery.reserve(identity, host.stt_service.value):
                        raise st.ParakeetConnectionError('config_incomplete')
                token = connecting_target.set(target)
                try:
                    dial_budget = recovery.dial_budget() if recovery is not None else None
                    if dial_budget is not None:
                        async with asyncio.timeout(dial_budget):
                            socket, actual = await primary(), host.stt_service
                    else:
                        socket, actual = await primary(), host.stt_service
                    record_managed_leg_handoff(socket)
                finally:
                    connecting_target.reset(token)
            else:
                socket, actual = await st.connect_stt_socket_with_fallback(
                    primary_service=host.stt_service,
                    connect_primary=primary,
                    connect_parakeet=callbacks[st.STTService.parakeet],
                    connect_soniox=callbacks[st.STTService.soniox],
                    connect_modulate=callbacks[st.STTService.modulate],
                    connect_deepgram=callbacks[st.STTService.deepgram],
                    failed=self.receiver._stt_failed_providers,
                    use_config=True,
                    routing_uid=uid,
                    routing_language=host.language,
                    routing_languages=tuple(getattr(host.language_profile, 'expected', ())),
                    routing_models=engine_models,
                    failed_targets=self.receiver._stt_failed_targets,
                )
        except asyncio.CancelledError:
            # A setup timeout/disconnect can arrive after a raw socket opens
            # but before the connector hands it back to the receiver.
            if self.recovery_enabled:
                for candidate in constructed:
                    candidate.retire_for_replay()
                    candidate.mark_owner_teardown()
                    await abort_replay_socket(candidate)
            raise
        host.stt_service = actual
        if self.no_text_rescue.returning:
            self.no_text_rescue.returning = False
        self._routing_target_entry = getattr(socket, '_routing_target_entry', None)
        host.stt_model = {
            st.STTService.parakeet: 'parakeet-window' if window else 'parakeet',
            st.STTService.soniox: 'soniox',
            st.STTService.modulate: 'velma-2',
            st.STTService.deepgram: dg_model,
        }[actual]
        selected_epoch = getattr(socket, 'speaker_provider_epoch', None)
        if selected_epoch is not None:
            self.receiver.speaker_provider_epoch = selected_epoch
        self.generation = generation
        self.receiver.vad_gate = self
        return socket


class LiveLegSocket(STTSocket):
    manages_vad = True

    def __init__(
        self,
        raw: STTSocket,
        gate: VADStreamingGate | None,
        session: LiveChainSession,
        service: st.STTService,
        sample_rate: int,
        window: bool,
        passthrough: bool,
        send_tracker: Any = None,
    ) -> None:
        self.raw, self.gate, self.session = raw, gate, session
        self.service, self.sample_rate, self.window, self.passthrough = service, sample_rate, window, passthrough
        # Audio-timeline v2: the provider epoch translator that records
        # accepted sends and maps provider times to the capture timeline.
        self._send_tracker = send_tracker
        self._soniox_wire_ledger = service == st.STTService.soniox and soniox_wire_ledger_enabled()
        if self._soniox_wire_ledger and send_tracker is not None:
            bind_wire = getattr(raw, 'set_wire_ledger', None)
            if not callable(bind_wire):
                raise RuntimeError('Managed Soniox transport has no wire ledger')
            cast(Callable[[Any], None], bind_wire)(send_tracker)
        try:
            if service == st.STTService.soniox and send_tracker is not None and capture_axis_diagnostics_enabled():
                bind = getattr(raw, 'set_capture_axis_ledger', None)
                if callable(bind):
                    bind(
                        lambda: (
                            None
                            if send_tracker.soniox_elapsed_mode == 'on'
                            else (
                                send_tracker.wire_audio_samples
                                if self._soniox_wire_ledger
                                else (send_tracker.send_map.last_provider_sample or 0)
                            )
                        )
                    )
        except Exception:
            disable_socket_diagnostics(raw)
        self.speaker_provider_epoch: SpeakerProviderEpoch | None = None
        self._dead = False
        self._local_death_reason: str | None = None
        self._terminal_reason: str | None = None
        self._seconds = 0.0
        self._replaying = False
        self._pending_selection: PendingLiveFailover | None = None
        self._ingest_gain: SessionPcmGain | None = None
        self._open_gauge_released = False
        self._first_speech_at: float | None = None
        self._speech_ms_for_health = 0
        self._transcript_outcome: str | None = None
        target = connecting_target.get()
        self._routing_target_entry = target
        self._routing_cohort = current_routing_cohort.get()
        self.routing_target = (
            target.id
            if target
            else (
                'parakeet'
                if service.value == 'parakeet' and not window
                else DEFAULT_IDS.get(service.value, service.value)
            )
        )
        self.routing_model = (
            'parakeet-window' if window else 'parakeet' if service.value == 'parakeet' else service.value
        )
        self.routing_endpoint = getattr(raw, 'routing_endpoint', None)
        self._health_language = bounded_language(session.receiver.host.language)
        self._cost_generations = health.cost_generations(self.routing_target, self._health_language)
        self.leg_outcome = LiveLegOutcome(
            self.routing_target,
            self._health_language,
            getattr(getattr(session.receiver.host, 'request', None), 'uid', None),
            self._cost_generations,
            health.record_session,
            client_has_left=self._client_has_left,
            text_seen=lambda: self._cost_text_seen,
        )
        self.recovery_enabled = session_recovery_enabled(session.receiver)
        self.leg_outcome.recovery_enabled = self.recovery_enabled
        self._cost_text_seen = False
        self._target_death_recorded = False
        self._closing_for_health = False
        try:
            self._routing_active = target is not None and routing_on(
                getattr(getattr(session.receiver.host, 'request', None), 'uid', None)
            )
        except ValueError:
            self._routing_active = False
        self._health_success: Callable[[], None] = lambda: None
        self._health_close: Callable[[], None] = lambda: None
        self.retired_for_replay = False
        self._no_text_rescue = getattr(session, 'no_text_rescue', None) or NoTextRescue(recovery_enabled=False)
        self._rescue_timer = None
        if self._no_text_rescue.active and not window:
            self._rescue_timer = asyncio.get_running_loop().call_later(
                self._no_text_rescue.remaining(), self._expire_rescue
            )
        self._replay_failure_reason: str | None = None
        self._replay_capacity_subtype: str | None = None
        self._emitted_capture_sample = 0
        self._pending_capture_sample: int | None = None
        self._speech_capture_end = 0
        self._tracks_window_replay = False
        self._replay_passthrough = False
        record_live_stt_socket_open(service.value)
        if window:
            from utils.stt.parakeet_window import SessionPcmGain, WINDOW_INGEST_AGC, WindowedParakeetSocket

            if isinstance(raw, WindowedParakeetSocket):
                raw.set_replay_progress_callback(self._trim_window_replay_to_anchor)
            if WINDOW_INGEST_AGC:
                self._ingest_gain = SessionPcmGain()

    def window_replay_anchor_sample(self) -> int | None:
        from utils.stt.parakeet_window import WindowedParakeetSocket

        if not isinstance(self.raw, WindowedParakeetSocket) or self._send_tracker is None:
            return self._emitted_capture_sample if not self.window else None
        provider_sample = self.raw.replay_anchor_sample()
        if provider_sample is None:
            return None
        return self._send_tracker.send_map.map_sample(provider_sample)

    def window_replay_pending_sample(self) -> int | None:
        if not self.window:
            return self._pending_capture_sample
        boundary = getattr(self.raw, 'replay_pending_sample', None)
        if not self.window or self._send_tracker is None or not callable(boundary):
            return None
        sample = cast(Callable[[], int | None], boundary)()
        return self._send_tracker.send_map.map_sample(sample) if sample is not None else None

    def window_replay_accounted_span(self) -> tuple[int, int] | None:
        boundary = getattr(self.raw, 'replay_accounted_span', None)
        if not self.window or self._send_tracker is None or not callable(boundary):
            return None
        span = cast(Callable[[], tuple[int, int] | None], boundary)()
        if span is None:
            return None
        # Map the last included sample, avoiding the next accepted span across
        # a gated gap at a provider boundary. An evicted start keeps more audio.
        first = self._send_tracker.send_map.map_sample(span[0])
        last = self._send_tracker.send_map.map_sample(span[1] - 1)
        if last is None:
            return None
        return (0 if first is None else first, last + 1)

    def window_replay_diagnostics(self, first: int, end: int, projected_samples: int) -> ReplayLagDiagnostics | None:
        from utils.stt.parakeet_window import WindowedParakeetSocket

        if not isinstance(self.raw, WindowedParakeetSocket) or self._send_tracker is None:
            return None
        send_map = self._send_tracker.send_map
        admitted = send_map.accepted_samples_in_capture_range(first, end)
        rate = send_map.provider_sample_rate
        return self.raw.replay_diagnostics(projected_samples / rate, admitted / rate)

    @property
    def replay_lag_diagnostics(self) -> ReplayLagDiagnostics | None:
        return getattr(self.raw, 'replay_lag_diagnostics', None)

    @property
    def first_text_diagnostics(self) -> FirstTextDeadlineDiagnostics | None:
        return getattr(self.raw, 'first_text_diagnostics', None)

    @property
    def capacity_subtype(self) -> str | None:
        return self._replay_capacity_subtype or getattr(self.raw, 'capacity_subtype', None)

    def has_untranscribed_speech(self) -> bool:
        if self.window:
            return bool(getattr(self.raw, 'has_untranscribed_speech')())
        return self._speech_capture_end > self._emitted_capture_sample

    def fail(self, reason: str, *, capacity_subtype: str | None = None) -> None:
        if self.window:
            getattr(self.raw, 'fail')(reason, capacity_subtype=capacity_subtype)
            return
        if self._replay_failure_reason is None:
            self._replay_failure_reason = reason
            self._replay_capacity_subtype = capacity_subtype
        self._dead = True
        self._finish_transport()

    def retire_for_replay(self) -> None:
        # A failed epoch's accepted audio is being replayed elsewhere. Fence
        # callbacks already queued on the listen loop as well as future ones.
        self.retired_for_replay = True

    def _trim_window_replay_to_anchor(self) -> None:
        trim_window_replay_to_anchor(self.session.receiver._window_ring(), self)

    @property
    def is_connection_dead(self) -> bool:
        # Observing liveness never settles evidence. Only the serving owner
        # knows whether this death caused failover or was found during teardown.
        raw_dead = self.raw.is_connection_dead
        if raw_dead:
            self._latch_failure()
        elif self._dead and self._terminal_reason is not None:
            self.leg_outcome.observe_death()
        return self._dead or raw_dead

    def record_target_death(self, reason: str) -> bool:
        target = self._routing_target_entry
        if (
            not self._routing_active
            or target is None
            or (target.id == DEFAULT_IDS.get(target.family) and target.endpoint is None)
        ):
            return False
        if self._target_death_recorded:
            return True
        self._target_death_recorded = True
        circuit = target_circuit(target)
        if reason in ACCOUNT_REJECTION_REASONS:
            circuit.record_account_failure(float(os.getenv('STT_ACCOUNT_CIRCUIT_COOLDOWN_SECONDS', '1800')))
            health.quarantine_target(target.id, circuit.account_cooldown_seconds_remaining)
            health.quarantine(self.service.value, 'account', circuit.account_cooldown_seconds_remaining)
        elif getattr(self.raw, 'idle_reopen_failed', False) is True:
            circuit.record_failure()
        else:
            circuit.record_serve_failure()
            health.quarantine(
                self.service.value, 'selection', circuit.serve_error_bench_seconds, endpoint=self.routing_endpoint
            )
        return True

    def _release_open_gauge(self) -> None:
        if not self._open_gauge_released:
            self._open_gauge_released = True
            record_live_stt_socket_closed(self.service.value)
            if self.leg_outcome.handed_off and not self.leg_outcome.transport_released:
                self.leg_outcome.transport_released = True
                MANAGED_LEGS_OPEN.labels(target=self.routing_target).dec()

    @property
    def death_reason(self) -> str | None:
        return self._terminal_reason or self._replay_failure_reason or self._local_death_reason or self.raw.death_reason

    @property
    def typed_death_reason(self) -> str | None:
        return (
            self._terminal_reason
            or self._replay_failure_reason
            or getattr(self.raw, 'typed_death_reason', None)
            or self._local_death_reason
        )

    @property
    def normalized_death_reason(self) -> str:
        # The serving decision owns the cause; observing raw liveness is pure.
        return (
            self.leg_outcome.reason
            or self._terminal_reason
            or normalize_live_stt_reason(self.typed_death_reason, self.death_reason)
        )

    def set_selection_outcome(self, pending: PendingLiveFailover) -> None:
        self._pending_selection = pending

    def note_selection_transcript(self, segments: list[dict[str, Any]]) -> None:
        if any(str(segment.get('text') or '').strip() for segment in segments):
            self._cost_text_seen = True
            if self._no_text_rescue.active and not self.window:
                self._no_text_rescue.note_transcript(segments)
        if self._tracks_window_replay:
            for segment in segments:
                end = segment.get('_capture_end_sample')
                if isinstance(end, int) and str(segment.get('text') or '').strip():
                    self._emitted_capture_sample = max(self._emitted_capture_sample, end)
            if not self.has_untranscribed_speech():
                self._pending_capture_sample = None
            elif self._pending_capture_sample is not None:
                self._pending_capture_sample = max(self._pending_capture_sample, self._emitted_capture_sample)
        if any(str(segment.get('text') or '').strip() for segment in segments) and self._transcript_outcome is None:
            deadline = max(1.0, float(os.getenv('STT_NO_TEXT_SECONDS', '30')))
            if self._first_speech_at is not None and time.monotonic() - self._first_speech_at <= deadline:
                self._record_transcript_outcome('text')
            elif self._first_speech_at is not None:
                self._record_transcript_outcome('no_text')
        if self._pending_selection is not None:
            self._pending_selection.note_transcript(segments)

    def _record_transcript_outcome(self, outcome: str) -> None:
        if self._transcript_outcome is not None:
            return
        self._transcript_outcome = outcome
        if self.routing_endpoint:
            health.record(
                self.service.value, self.session.receiver.host.language, outcome, endpoint=self.routing_endpoint
            )
        else:
            health.record(self.service.value, self.session.receiver.host.language, outcome)
        if self._routing_active:
            if outcome == 'text':
                self._health_success()
            else:
                self._health_close()

    def _check_no_text_deadline(self) -> None:
        if self._first_speech_at is None or self._transcript_outcome is not None:
            return
        if time.monotonic() - self._first_speech_at >= max(1.0, float(os.getenv('STT_NO_TEXT_SECONDS', '30'))):
            self._record_transcript_outcome('no_text')

    @property
    def defers_selection_success(self) -> bool:
        return self.window or self._routing_active

    def set_health_callbacks(self, on_success: Callable[[], None], on_close: Callable[[], None]) -> None:
        from utils.stt.parakeet_window import WindowedParakeetSocket

        if self._routing_active:
            self._health_success, self._health_close = on_success, on_close
        elif isinstance(self.raw, WindowedParakeetSocket):
            self.raw.set_health_callbacks(on_success, on_close)

    def _note_replay_capture(self, data: bytes, start_sample: int | None) -> None:
        if start_sample is None:
            return
        if self._pending_capture_sample is None:
            self._pending_capture_sample = max(start_sample, self._emitted_capture_sample)
        self._speech_capture_end = max(self._speech_capture_end, start_sample + len(data) // 2)

    def _send_unscored_replay_capture(self, data: bytes, start_sample: int | None = None) -> bool:
        self._note_replay_capture(data, start_sample)
        return LiveLegSocket.send(self, data, start_sample=start_sample)

    def enable_window_replay_tracking(self) -> None:
        """Retain future speech on a window-origin replacement, even without replay."""
        if self._tracks_window_replay:
            return
        self._tracks_window_replay = True
        gate = self.gate
        if gate is None:
            # Only a window-origin replacement without VAD uses this wrapper.
            setattr(self, 'send', self._send_unscored_replay_capture)
            return
        process = gate.process_audio

        def process_replay_capture(data, wall_time, score_pcm=None, *, start_sample=None):
            try:
                if self._replay_passthrough:
                    mode = gate.mode
                    gate.mode = 'shadow'
                    try:
                        output = process(data, wall_time, score_pcm, start_sample=start_sample)
                    finally:
                        gate.mode = mode
                else:
                    output = process(data, wall_time, score_pcm, start_sample=start_sample)
            except Exception:
                # send() keeps its existing VAD fail-open policy. Account this
                # unscored packet and future direct packets conservatively.
                self._note_replay_capture(data, start_sample)
                setattr(self, 'send', self._send_unscored_replay_capture)
                raise
            if output.is_speech:
                self._note_replay_capture(data, start_sample)
            return output

        # Install once, after failover. Never-failed sessions retain the original
        # send path, with no additional per-send branches or progress writes.
        setattr(gate, 'process_audio', process_replay_capture)

    def send(self, data: bytes, start_sample: int | None = None) -> bool:
        if self._closing_for_health:
            return False
        if self.is_connection_dead:
            return False
        from utils.stt.parakeet_window import WindowedParakeetSocket

        score_pcm: bytes | None = None
        if self._ingest_gain is not None:
            # Gain a copy for Silero only. Stored / posted bytes stay original
            # so the posted stage is the only scale the decoder sees.
            score_pcm = self._ingest_gain.apply(data)
            if isinstance(self.raw, WindowedParakeetSocket):
                self.raw.observe_session_peak(self._ingest_gain.peak)
        output = None
        if self.gate is not None:
            try:
                # Synthetic wall clock follows received audio. Positive epoch
                # avoids VAD's zero sentinel. Silero scores the level-corrected
                # copy; pre-roll and audio_to_send stay original-level.
                output = self.gate.process_audio(data, 1.0 + self._seconds, score_pcm, start_sample=start_sample)
            except Exception:
                if self.window:
                    self._local_death_reason = 'vad_failed'
                    self._dead = True
                    try:
                        self.raw.finish()
                    finally:
                        self._latch_failure()
                        self._release_open_gauge()
                    record_fallback(
                        component='vad',
                        from_mode='gated',
                        to_mode='none',
                        reason='connection_lost',
                        outcome='exhausted',
                    )
                    return False
                record_fallback(
                    component='vad', from_mode='gated', to_mode='direct', reason='other', outcome='degraded'
                )
                self.gate.mode = 'off'
                self.gate = None
                self.session.vad_mode = 'off'
        observe = getattr(self.raw, 'observe_vad', None)
        if (
            getattr(self.raw, 'idle_close_enabled', False) is True
            and callable(observe)
            and output is not None
            and self.gate is not None
            and not self._replaying
        ):
            observe(output, self.gate.mode)
        audio = data if output is None or self.passthrough else output.audio_to_send
        if output is not None and output.is_speech and self._first_speech_at is None:
            self._first_speech_at = time.monotonic()
        if output is not None and output.is_speech:
            self._speech_ms_for_health += int(len(data) / (self.sample_rate * 2) * 1000)
        self._check_no_text_deadline()
        if self.window and output is not None and output.is_speech:
            if isinstance(self.raw, WindowedParakeetSocket):
                self.raw.mark_speech()
        sent_spans: tuple[tuple[int, int], ...] = ()
        if start_sample is not None and audio:
            if audio is data:
                sent_spans = ((start_sample, len(data) // 2),)
            else:
                sent_spans = tuple(output.send_spans) if output is not None else ()
        record_before_finalize = live_capture_window_translator_sends_enabled()
        try:
            if audio:
                if not self.window and not self._no_text_rescue.can_admit(len(audio) / (self.sample_rate * 2)):
                    self._expire_rescue()
                    return False
                try:
                    token = capture_spans.set(sent_spans) if self._soniox_wire_ledger else None
                    try:
                        sent = self.raw.send(audio)
                    finally:
                        if token is not None:
                            capture_spans.reset(token)
                except Exception:
                    # A raised send is transport evidence unless the socket
                    # already owns a more specific bounded cause.
                    self._latch_failure(reason='connection_lost')
                    self._dead = True
                    self._finish_transport()
                    return False
                if sent is not True:
                    # False is a send symptom only while the raw socket still
                    # reports alive. A dead socket with unknown diagnostics is
                    # a connection loss, and typed causes win in normalization.
                    try:
                        raw_dead = bool(self.raw.is_connection_dead)
                    except Exception:
                        raw_dead = True
                    self._latch_failure(reason='connection_lost' if raw_dead else 'send_failed')
                    self._finish_transport()
                    self._dead = True
                    return False
                if self._routing_cohort is not None and getattr(self.raw, 'idle_close_enabled', False) is not True:
                    self._routing_cohort.paid_audio(self.service.value, len(audio) / (self.sample_rate * 2))
                if not self.window:
                    self._no_text_rescue.audio(self.service.value, len(audio) / (self.sample_rate * 2))
            if record_before_finalize and self._send_tracker is not None and not self._soniox_wire_ledger:
                note_observed_spans(self._send_tracker, sent_spans, 'managed_chain')
            if output is not None and output.should_finalize:
                if self.window and isinstance(self.raw, WindowedParakeetSocket):
                    self.raw.finalize(vad_pause=True)
                else:
                    self.raw.finalize()
        except Exception:
            self._local_death_reason = 'send_failed'
            self._dead = True
            self._finish_transport()
            return False
        self._idle_send_spans = sent_spans
        if (
            sent_spans
            and self._send_tracker is not None
            and not record_before_finalize
            and not self._soniox_wire_ledger
        ):
            self._send_tracker.send_path = 'managed_chain'
            self._send_tracker.note_accepted_spans(sent_spans)
        duration = len(data) / (self.sample_rate * 2)
        if self.window and output is not None and isinstance(self.raw, WindowedParakeetSocket):
            self.raw.observe_capture(output.is_speech, duration)
        self._seconds += duration
        speech_ms = self.gate.consume_speech_ms_delta() if self.gate is not None else 0
        if not self._replaying:
            self.session.audio_seconds += duration
            self.session.speech_ms += speech_ms
            self.session.total_speech_ms += speech_ms
        if speech_ms and not self._replaying:
            record_live_stt_audio_seconds(
                provider=self.service.value,
                platform=self.session.receiver._telemetry_platform(),
                seconds=speech_ms / 1000,
            )
        return True

    @property
    def replay_limits(self) -> Any:
        """Typed endpoint limits: the selected target's declaration first."""
        target = self._routing_target_entry
        declared = getattr(target, 'replay', None) if target is not None else None
        if isinstance(declared, ReplayLimits):
            return declared
        declared = getattr(self.raw, 'replay_limits', None)
        if isinstance(declared, ReplayLimits):
            return declared
        return ReplayLimits(max_frame_bytes=replay_delivery.REPLAY_PACKET_BYTES)

    def _leg_recovery_enabled(self) -> bool:
        pinned = getattr(getattr(self, 'leg_outcome', None), 'recovery_enabled', None)
        if isinstance(pinned, bool):
            return pinned
        enabled = getattr(self, 'recovery_enabled', None)
        if isinstance(enabled, bool):
            return enabled
        return session_recovery_enabled(getattr(self, 'session', None))

    async def wait_send_capacity(self, limit: int | None = None, timeout: float | None = None) -> bool:
        if not self._leg_recovery_enabled():
            return not self.is_connection_dead
        wait = getattr(self.raw, 'wait_send_capacity', None)
        if not callable(wait):
            return not self.is_connection_dead
        try:
            return await cast(Callable[..., Awaitable[bool]], wait)(limit=limit, timeout=timeout)
        except TypeError:
            return await cast(Callable[[], Awaitable[bool]], wait)()

    def replay_send(self, data: bytes, start_sample: int) -> bool:
        ring = getattr(self.session.receiver, '_window_ring', None)
        # Source admission and capture retention already decided this replay
        # span. A different VAD score must not discard or finalize its middle.
        self._replay_passthrough = callable(ring) and ring() is not None
        if self._replay_passthrough and not self.window:
            self.enable_window_replay_tracking()
            # The source epoch admitted this span. A different VAD decision
            # during replay cannot erase its still-unfulfilled obligation.
            if self._pending_capture_sample is None:
                self._pending_capture_sample = start_sample
            self._speech_capture_end = max(self._speech_capture_end, start_sample + len(data) // 2)
        self._replaying = True
        try:
            return self.send(data, start_sample=start_sample)
        finally:
            self._replaying = False
            self._replay_passthrough = False

    @property
    def idle_close_enabled(self) -> bool:
        return getattr(self.raw, 'idle_close_enabled', False) is True

    async def complete_send(self) -> bool:
        offset = getattr(self.raw, 'set_resume_provider_offset', None)
        if self._send_tracker is not None and callable(offset):
            offset(
                self._send_tracker.wire_provider_samples or 0
                if self._soniox_wire_ledger
                else self._send_tracker.last_send_provider_start
            )
        complete = getattr(self.raw, 'complete_send', None)
        completed = (
            await cast(Callable[[], Awaitable[bool]], complete)() if callable(complete) else not self.is_connection_dead
        )
        if not completed and getattr(self.raw, 'idle_reopen_failed', False) is True:
            self.leg_outcome.claim(self.typed_death_reason or 'connection_lost', connect=True)
        return completed

    def commit_send(self) -> None:
        commit = getattr(self.raw, 'commit_send', None)
        if callable(commit):
            commit()

    def send_admitted_audio(self, data: bytes, spans: Any) -> bool:
        from utils.stt.soniox_idle import unaccepted_onset

        data, spans = unaccepted_onset(data, spans, self._send_tracker)
        if not data:
            return True
        self._idle_send_spans = spans
        token = capture_spans.set(tuple(spans)) if self._soniox_wire_ledger else None
        try:
            accepted = self.raw.send(data)
        finally:
            if token is not None:
                capture_spans.reset(token)
        if accepted and self._routing_cohort is not None and getattr(self.raw, 'idle_close_enabled', False) is not True:
            self._routing_cohort.paid_audio(self.service.value, len(data) / (self.sample_rate * 2))
        if accepted and self._send_tracker is not None and spans:
            if not self._soniox_wire_ledger:
                self._send_tracker.note_accepted_spans(spans)
            self._note_replay_capture(data, spans[0][0])
        return accepted

    def take_unsent_packet(self) -> Any:
        data = self.take_unsent_audio()
        return (data, getattr(self, '_idle_send_spans', ())) if data else None

    def take_unsent_audio(self) -> bytes:
        take = getattr(self.raw, 'take_unsent_audio', None)
        return cast(Callable[[], bytes], take)() if callable(take) else b''

    def finalize(self) -> None:
        self.raw.finalize()

    def _expire_rescue(self) -> None:
        self._rescue_timer = None
        if not self.retired_for_replay and not self._closing_for_health and not self._client_has_left():
            self.fail('no_text_rescue_complete')

    def _latch_failure(self, *, reason: str | None = None) -> None:
        if self._terminal_reason is None:
            self._terminal_reason = normalize_live_stt_reason(self.typed_death_reason, self.death_reason, reason)
        self.leg_outcome.observe_death()

    def _finish_transport(self) -> None:
        if self._rescue_timer is not None:
            self._rescue_timer.cancel()
            self._rescue_timer = None
        self._closing_for_health = True
        try:
            self.raw.finish()
        finally:
            self._check_no_text_deadline()
            if (
                self._transcript_outcome is None
                and self._first_speech_at is not None
                and self._speech_ms_for_health >= 1000
            ):
                self._record_transcript_outcome('no_text')
            elif self._transcript_outcome is None and self._routing_active:
                self._health_close()
            self._release_open_gauge()

    def _client_has_left(self) -> bool:
        controller = getattr(self.session.receiver, 'recovery', None)
        if controller is not None:
            return controller.client_has_left()
        host = self.session.receiver.host
        state = getattr(host, 'state', None)
        if getattr(state, 'active', None) is False:
            return True
        shutdown = getattr(state, 'shutdown_event', None)
        if shutdown is not None and shutdown.is_set() is True:
            return True
        client = getattr(getattr(host, 'request', None), 'websocket', None)
        return (
            getattr(client, 'client_state', None) == WebSocketState.DISCONNECTED
            or getattr(client, 'application_state', None) == WebSocketState.DISCONNECTED
        )

    def mark_owner_teardown(self) -> None:
        if self.leg_outcome.owner_closing:
            return
        # Snapshot the already-published death latch before the owner fence or
        # any close/await. Provider callbacks run on this same serving loop.
        # A pre-existing death stays evidence if the client is still eligible
        # at the first claim, even if the 1s monitor lost the race.
        if not self.leg_outcome.claimed and self.is_connection_dead:
            self._latch_failure()
            if self._leg_recovery_enabled():
                settle_terminal_socket(self, self.service.value, self.normalized_death_reason, departing=True)
            else:
                settle_terminal_socket(self, self.service.value, self.normalized_death_reason)
        self.leg_outcome.owner_closing = True

    def finish(self) -> None:
        if not self.leg_outcome.claimed:
            self.mark_owner_teardown()
        try:
            self._finish_transport()
        finally:
            if self._pending_selection is not None:
                self._pending_selection.note_failure(None)
            self.leg_outcome.close(self._cost_text_seen)

    async def drain_and_close(self) -> None:
        if not self.leg_outcome.claimed:
            self.mark_owner_teardown()
        self._closing_for_health = True
        try:
            await st.drain_stt_socket(self.raw)
        finally:
            self.finish()
