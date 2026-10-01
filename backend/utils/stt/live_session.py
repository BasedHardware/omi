"""Managed live-leg construction, VAD ownership and provider epoch timelines."""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING, Any, Awaitable, Callable, cast

from utils.observability.fallback import FirstTextDeadlineDiagnostics, ReplayLagDiagnostics, record_fallback
from utils.observability.transcription import record_live_stt_audio_seconds
from utils.stt import streaming as st
from utils.stt.live_failure import PendingLiveFailover
from utils.stt.live_rollout import window_allocation, window_language_supported
from utils.stt.resilient_stream import trim_window_replay_to_anchor
from utils.stt.live_health import health, mode as routing_mode
from utils.stt.socket import STTSocket, record_live_stt_socket_closed, record_live_stt_socket_open
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
        self.audio_seconds = 0.0
        self.last_end = 0.0
        self.generation = 0
        self.speech_ms = 0
        self.total_speech_ms = 0
        self.vad_mode = 'off'

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
                        translated = epoch.translate(seg_list)
                        if translated:
                            leg.note_selection_transcript(translated)
                            self.receiver._enqueue_epoch_segments(translated, provider=service.value)

                    self.receiver._run_on_listen_loop(translate_on_loop, segments)
                    return
                if epoch is not None:
                    # Clock-only capture clock: attach the window from the
                    # provider's own timestamps, then keep this leg's legacy
                    # offset/last_end rebase (and gate remap) exactly as the
                    # pre-timeline managed chain did — flag-off emitted times
                    # stay monotonic across legs and byte-identical to main.
                    def attach_then_rebase(seg_list: list[dict[str, Any]]) -> None:
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
                        self.receiver._enqueue_epoch_segments(translated, provider=service.value)

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
                self.receiver._enqueue_stt_segments(segments, provider=service.value)

            raw = None
            try:
                if is_window:
                    from utils.stt.parakeet_window import connect_window

                    raw = connect_window(callback, sample_rate)
                elif service == st.STTService.parakeet:
                    raw = await st.process_audio_parakeet(callback, language, sample_rate, 1, keywords=keywords)
                elif service == st.STTService.soniox:
                    raw = await st.process_audio_soniox(
                        callback, sample_rate, language, profile=host.language_profile, keywords=keywords
                    )
                elif service == st.STTService.modulate:
                    raw = await st.process_audio_modulate(callback, sample_rate, language)
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
        primary = callbacks.get(host.stt_service)
        primary_missing = primary is None
        if primary_missing:

            async def unavailable() -> STTSocket:
                raise st.ParakeetConnectionError('config_incomplete')

            primary = unavailable
        if same_provider:
            if primary_missing:
                raise st.ParakeetConnectionError('config_incomplete')
            socket, actual = await primary(), host.stt_service
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
                routing_pin_primary=host.stt_model == 'parakeet-window'
                or getattr(host.language_profile, 'arm', None) == 'hintable',
            )
        host.stt_service = actual
        host.stt_model = {
            st.STTService.parakeet: 'parakeet-window' if window else 'parakeet',
            st.STTService.soniox: 'soniox',
            st.STTService.modulate: 'velma-2',
            st.STTService.deepgram: dg_model,
        }[actual]
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
        self._dead = False
        self._seconds = 0.0
        self._replaying = False
        self._pending_selection: PendingLiveFailover | None = None
        self._ingest_gain: SessionPcmGain | None = None
        self._open_gauge_released = False
        self._first_speech_at: float | None = None
        self._speech_ms_for_health = 0
        self._transcript_outcome: str | None = None
        self._health_success: Callable[[], None] = lambda: None
        self._health_close: Callable[[], None] = lambda: None
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
            return None
        provider_sample = self.raw.replay_anchor_sample()
        if provider_sample is None:
            return None
        return self._send_tracker.send_map.map_sample(provider_sample)

    def window_replay_pending_sample(self) -> int | None:
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
        return getattr(self.raw, 'capacity_subtype', None)

    def _trim_window_replay_to_anchor(self) -> None:
        trim_window_replay_to_anchor(self.session.receiver._window_ring(), self)

    @property
    def is_connection_dead(self) -> bool:
        dead = self._dead or self.raw.is_connection_dead
        if dead and self._pending_selection is not None:
            self._pending_selection.note_failure(self.typed_death_reason)
        return dead

    def _release_open_gauge(self) -> None:
        if not self._open_gauge_released:
            self._open_gauge_released = True
            record_live_stt_socket_closed(self.service.value)

    @property
    def death_reason(self) -> str | None:
        return 'vad_failed' if self._dead else self.raw.death_reason

    @property
    def typed_death_reason(self) -> str | None:
        return getattr(self.raw, 'typed_death_reason', None)

    def set_selection_outcome(self, pending: PendingLiveFailover) -> None:
        self._pending_selection = pending

    def note_selection_transcript(self, segments: list[dict[str, Any]]) -> None:
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
        health.record(self.service.value, self.session.receiver.host.language, outcome)
        if routing_mode() == 'on':
            if outcome == 'text':
                self._health_success()
            else:
                self._health_close()
                circuit = st._circuit_for_primary(self.service)  # type: ignore[reportPrivateUsage]
                circuit.record_serve_failure()
                health.quarantine(self.service.value, 'selection', circuit.serve_error_bench_seconds)

    def _check_no_text_deadline(self) -> None:
        if self._first_speech_at is None or self._transcript_outcome is not None:
            return
        if time.monotonic() - self._first_speech_at >= max(1.0, float(os.getenv('STT_NO_TEXT_SECONDS', '30'))):
            self._record_transcript_outcome('no_text')

    @property
    def defers_selection_success(self) -> bool:
        return self.window or routing_mode() == 'on'

    def set_health_callbacks(self, on_success: Callable[[], None], on_close: Callable[[], None]) -> None:
        from utils.stt.parakeet_window import WindowedParakeetSocket

        if routing_mode() == 'on':
            self._health_success, self._health_close = on_success, on_close
        elif isinstance(self.raw, WindowedParakeetSocket):
            self.raw.set_health_callbacks(on_success, on_close)

    def send(self, data: bytes, start_sample: int | None = None) -> bool:
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
                    self._dead = True
                    try:
                        self.raw.finish()
                    finally:
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
        try:
            if audio and self.raw.send(audio) is not True:
                self.finish()
                self._dead = True
                return False
            if output is not None and output.should_finalize and not self.window:
                self.raw.finalize()
        except Exception:
            self._dead = True
            self.finish()
            return False
        if sent_spans and self._send_tracker is not None:
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

    def replay_send(self, data: bytes, start_sample: int) -> bool:
        self._replaying = True
        try:
            return self.send(data, start_sample=start_sample)
        finally:
            self._replaying = False

    def finalize(self) -> None:
        self.raw.finalize()

    def finish(self) -> None:
        try:
            if self.is_connection_dead and self._pending_selection is not None:
                self._pending_selection.note_failure(self.typed_death_reason)
            self.raw.finish()
        finally:
            self._check_no_text_deadline()
            if (
                self._transcript_outcome is None
                and self._first_speech_at is not None
                and self._speech_ms_for_health >= 1000
            ):
                self._record_transcript_outcome('no_text')
            elif self._transcript_outcome is None and routing_mode() == 'on':
                self._health_close()
            self._release_open_gauge()

    async def drain_and_close(self) -> None:
        try:
            await st.drain_stt_socket(self.raw)
        finally:
            self.finish()
