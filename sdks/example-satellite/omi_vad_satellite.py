#!/usr/bin/env python3
# Library file for WebSocket VAD Satellite
import asyncio
import logging
import math
import argparse
from pathlib import Path
from typing import Optional, Callable, Union

from pyring_buffer import RingBuffer

from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.asr import Transcript
from wyoming.error import Error
from wyoming.event import Event, async_write_event
from wyoming.info import Attribution, Info, Satellite
from wyoming.ping import Ping, Pong
from wyoming.server import AsyncEventHandler
from wyoming.satellite import (
    RunSatellite,
    PauseSatellite,
    SatelliteConnected,
    SatelliteDisconnected,
    StreamingStarted,
    StreamingStopped,
)
from wyoming.tts import Synthesize
from wyoming.timer import TimerCancelled, TimerFinished, TimerStarted, TimerUpdated

from wyoming_satellite import SatelliteBase, __version__
from wyoming_satellite.satellite import State, SoundEvent
from wyoming_satellite.settings import (
    SatelliteSettings,
)
from wyoming_satellite.vad import SileroVad
from wyoming_satellite.utils import DebugAudioWriter, run_event_command, multiply_volume


_LOGGER = logging.getLogger()

# Opus constants needed by the satellite class
OPUS_SAMPLE_RATE = 16000
OPUS_CHANNELS = 1
OPUS_FRAME_SIZE = 960 # 60ms
PCM_SAMPLE_WIDTH = 2 # 16-bit

# -----------------------------------------------------------------------------
# Custom Satellite Class
# -----------------------------------------------------------------------------

class WebSocketVadSatellite(SatelliteBase):
    """Satellite that receives PCM audio via method call and uses VAD."""
    def __init__(self, settings: SatelliteSettings):
        # --- Manual SatelliteBase Init --- 
        self.settings = settings # Store the *real* settings
        self.server_id: Optional[str] = None
        self._state = State.NOT_STARTED
        self._state_changed = asyncio.Event()
        self._writer: Optional[asyncio.StreamWriter] = None

        # Disable tasks not used
        self._mic_task: Optional[asyncio.Task] = None
        self._wake_task: Optional[asyncio.Task] = None
        self._mic_webrtc: Optional[Callable[[bytes], bytes]] = None

        # Keep tasks used
        self._snd_task: Optional[asyncio.Task] = None
        self._snd_queue: Optional[asyncio.Queue[SoundEvent]] = None
        self._event_task: Optional[asyncio.Task] = None
        self._event_queue: Optional[asyncio.Queue[Event]] = None

        self._ping_server_enabled: bool = False
        self._pong_received_event = asyncio.Event()
        self._ping_server_task: Optional[asyncio.Task] = None

        self.microphone_muted = False # Keep for snd events?
        self._unmute_microphone_task: Optional[asyncio.Task] = None
        # --- End Manual SatelliteBase Init --- 

        # VAD specific init from VadStreamingSatellite
        if not settings.vad or not settings.vad.enabled:
             raise ValueError("VAD must be enabled for WebSocketVadSatellite")

        self.is_streaming = False
        self.vad = SileroVad(
            threshold=settings.vad.threshold,
            trigger_level=settings.vad.trigger_level
        )
        self.timeout_seconds: Optional[float] = None
        self.vad_buffer: Optional[RingBuffer] = None
        if settings.vad.buffer_seconds > 0:
            vad_buffer_bytes = int(math.ceil(settings.vad.buffer_seconds * OPUS_SAMPLE_RATE * PCM_SAMPLE_WIDTH))
            self.vad_buffer = RingBuffer(maxlen=vad_buffer_bytes)

        self._is_paused = False # From VadStreamingSatellite

        # Debug audio
        self.stt_audio_writer: Optional[DebugAudioWriter] = None
        if settings.debug_recording_dir:
             self.stt_audio_writer = DebugAudioWriter(
                 settings.debug_recording_dir, "stt"
             )

    # --- Core Satellite Methods --- 
    async def run(self) -> None:
        """Override run to only start necessary tasks (snd, event)."""
        # Simplified run loop, focusing on managing snd/event tasks and state
        try:
            if self.state == State.NOT_STARTED:
                await self._start_internal_services()

            while self.is_running:
                await self._state_changed.wait()
                if self.state == State.STOPPING:
                    await self._stop_internal_services()
                    break
                elif self.state == State.RESTARTING:
                    _LOGGER.warning("Restarting... stopping internal services.")
                    await self._stop_internal_services()
                    _LOGGER.info("Restarting... starting internal services.")
                    await self._start_internal_services() # Re-start snd/event
                    self.state = State.STARTED # Back to started
                elif self.state == State.STOPPED:
                    await self.stopped()
                    break

        except asyncio.CancelledError:
            _LOGGER.info("Satellite run cancelled.")
        except Exception:
            _LOGGER.exception("Unexpected error in satellite run task")
        finally:
            if self.state != State.STOPPED:
                 await self._stop_internal_services() # Ensure cleanup
            self.state = State.STOPPED
            await self.stopped()

    async def _start_internal_services(self) -> None:
        """Starts snd and event service tasks if enabled."""
        self.state = State.STARTING
        if self.settings.snd and self.settings.snd.enabled:
            _LOGGER.debug("Connecting to snd service...")
            self._snd_task = asyncio.create_task(self._snd_task_proc(), name="snd")
        if self.settings.event and self.settings.event.enabled:
            _LOGGER.debug("Connecting to event service...")
            self._event_task = asyncio.create_task(self._event_task_proc(), name="event")
        self.state = State.STARTED
        await self.started()

    async def _stop_internal_services(self) -> None:
        """Stops snd and event service tasks."""
        tasks_to_stop = []
        if self._snd_task is not None:
            _LOGGER.debug("Stopping sound service")
            self._snd_task.cancel()
            tasks_to_stop.append(self._snd_task)
            self._snd_task = None

        if self._event_task is not None:
            _LOGGER.debug("Stopping event service")
            self._event_task.cancel()
            tasks_to_stop.append(self._event_task)
            self._event_task = None

        if tasks_to_stop:
            await asyncio.gather(*tasks_to_stop, return_exceptions=True)

        _LOGGER.debug("Disconnected from internal services")

    async def stop(self) -> None:
         """Initiates the satellite stop sequence."""
         if self.state != State.STOPPED:
             self.state = State.STOPPING

    async def stopped(self) -> None:
         """Called when satellite has stopped."""
         _LOGGER.info("Satellite stopped.")

    async def started(self) -> None:
         """Called when satellite has started."""
         _LOGGER.info("Satellite started and ready.")

    # --- Server Connection Handling (from SatelliteBase) --- 
    async def set_server(self, server_id: str, writer: asyncio.StreamWriter) -> None:
         self.server_id = server_id
         self._writer = writer
         _LOGGER.debug("Server set: %s", server_id)
         await self.trigger_server_connected()

    async def clear_server(self) -> None:
         self.server_id = None
         self._writer = None
         self._disable_ping()
         _LOGGER.debug("Server connection cleared")
         await self.trigger_server_disonnected()

    async def event_to_server(self, event: Event) -> None:
         if self._writer is None:
             return
         try:
             await asyncio.sleep(0) # Yield to allow other tasks
             await async_write_event(event, self._writer)
         except (ConnectionResetError, BrokenPipeError):
             _LOGGER.warning("Server disconnected unexpectedly")
             await self.clear_server()
         except Exception:
             _LOGGER.exception("Unexpected error sending event to server")
             await self.clear_server()

    # --- Ping/Pong Handling (from SatelliteBase) --- 
    def _enable_ping(self) -> None:
         if not self._ping_server_enabled:
             self._ping_server_enabled = True
             self._ping_server_task = asyncio.create_task(self._ping_server(), name="ping")

    def _disable_ping(self) -> None:
         self._ping_server_enabled = False
         if self._ping_server_task is not None:
             self._ping_server_task.cancel()
             self._ping_server_task = None

    async def _ping_server(self) -> None:
         # Simplified from SatelliteBase
         PING_SEND_DELAY = 2
         PONG_TIMEOUT = 5
         try:
             while self._ping_server_enabled and (self.server_id is not None):
                 await asyncio.sleep(PING_SEND_DELAY)
                 if not self._ping_server_enabled or (self.server_id is None):
                     break # Check again after sleep
                 
                 self._pong_received_event.clear()
                 ping_event = Ping().event()
                 _LOGGER.debug("Sending ping: %s", ping_event)
                 await self.event_to_server(ping_event)
                 try:
                     await asyncio.wait_for(
                         self._pong_received_event.wait(), timeout=PONG_TIMEOUT
                     )
                     _LOGGER.debug("Received pong")
                 except asyncio.TimeoutError:
                     if self.server_id is not None: # Avoid race condition on disconnect
                          _LOGGER.warning("Did not receive ping response within timeout")
                          await self.clear_server()
         except asyncio.CancelledError:
             pass
         except Exception:
             _LOGGER.exception("Unexpected error in ping server task")
             await self.clear_server() # Disconnect if ping fails badly
         finally:
             self._ping_server_task = None
             self._ping_server_enabled = False

    # --- Sound Output Handling (from SatelliteBase) --- 
    async def event_to_snd(self, event: Event, is_tts: bool = True) -> None:
        if self._snd_queue is not None:
            self._snd_queue.put_nowait(SoundEvent(event, is_tts))

    async def _snd_task_proc(self) -> None:
        # Simplified from SatelliteBase - assumes SndSettings exists if task is running
        snd_client = None
        try:
            if self._snd_queue is None:
                self._snd_queue = asyncio.Queue()

            while True:
                snd_event_wrapper = await self._snd_queue.get()
                event = snd_event_wrapper.event

                if snd_client is None:
                    # Assume make_snd_client works - need to import/define it?
                    # Let's inline the logic from SatelliteBase._make_snd_client
                    if self.settings.snd.uri:
                        from wyoming.client import AsyncClient
                        snd_client = AsyncClient.from_uri(self.settings.snd.uri)
                    elif self.settings.snd.command:
                        from wyoming.snd import SndProcessAsyncClient
                        program, *program_args = self.settings.snd.command
                        snd_client = SndProcessAsyncClient(
                            rate=self.settings.snd.rate,
                            width=self.settings.snd.width,
                            channels=self.settings.snd.channels,
                            program=program,
                            program_args=program_args,
                        )
                    else:
                         _LOGGER.error("No snd URI or command configured.")
                         continue # Skip this event

                    if snd_client:
                        await snd_client.connect()
                        _LOGGER.debug("Connected to snd service")
                    else:
                         _LOGGER.error("Failed to create snd client.")
                         continue

                # Process audio (volume)
                if AudioChunk.is_type(event.type):
                    chunk = AudioChunk.from_event(event)
                    audio_bytes = self._process_snd_audio(chunk.audio)
                    event = AudioChunk(
                        rate=chunk.rate,
                        width=chunk.width,
                        channels=chunk.channels,
                        audio=audio_bytes,
                    ).event()

                await snd_client.write_event(event)

                if AudioStop.is_type(event.type):
                     # Disconnect logic from SatelliteBase (optional, based on settings)
                     # if self.settings.snd.disconnect_after_stop:
                     #     await snd_client.disconnect()
                     #     snd_client = None 
                     if snd_event_wrapper.is_tts:
                        from wyoming.snd import Played # Import here
                        await self.event_to_server(Played().event())
                        await self.trigger_played()

        except asyncio.CancelledError:
            pass
        except Exception:
            _LOGGER.exception("Unexpected error in snd task")
        finally:
            if snd_client is not None:
                try:
                    await snd_client.disconnect()
                except Exception:
                    _LOGGER.debug("Error disconnecting snd client", exc_info=True)
            self._snd_task = None
            self._snd_queue = None # Clear queue on exit

    def _process_snd_audio(self, audio_bytes: bytes) -> bytes:
        if self.settings.snd and self.settings.snd.volume_multiplier != 1.0:
            audio_bytes = multiply_volume(
                audio_bytes, self.settings.snd.volume_multiplier
            )
        return audio_bytes

    # --- Event Forwarding Handling (from SatelliteBase) --- 
    async def forward_event(self, event: Event) -> None:
        if self._event_queue is not None:
            self._event_queue.put_nowait(event)

    async def _event_task_proc(self) -> None:
        # Simplified from SatelliteBase - assumes EventSettings exists if task is running
        event_client = None
        try:
            if self._event_queue is None:
                self._event_queue = asyncio.Queue()

            while True:
                event = await self._event_queue.get()

                if event_client is None:
                    if self.settings.event and self.settings.event.uri:
                        from wyoming.client import AsyncClient
                        event_client = AsyncClient.from_uri(self.settings.event.uri)
                        await event_client.connect()
                        _LOGGER.debug("Connected to event service")
                    else:
                         # No event service configured or client failed
                         _LOGGER.debug("Event service not configured/connected, skipping event forwarding.")
                         # We could just drop events, or maybe stop the task?
                         # Let's just drop future events if client fails once.
                         self._event_queue = None # Stop queueing
                         break # Exit task

                await event_client.write_event(event)

        except asyncio.CancelledError:
            pass
        except Exception:
            _LOGGER.exception("Unexpected error in event task")
        finally:
            if event_client is not None:
                try:
                    await event_client.disconnect()
                except Exception:
                     _LOGGER.debug("Error disconnecting event client", exc_info=True)
            self._event_task = None
            self._event_queue = None # Clear queue on exit

    # --- Muting Logic (Adapted from SatelliteBase) --- 
    async def _play_wav(self, wav_path: Optional[Union[str, Path]], mute: bool = False) -> None:
        # Needs wave, Union, Path imports
        # Needs wav_to_events from utils
        if (not wav_path) or not (self.settings.snd and self.settings.snd.enabled):
            return
        
        from pathlib import Path
        import wave
        from wyoming_satellite.utils import wav_to_events

        # Ensure wav_path is a Path object and exists
        wav_path_obj = Path(wav_path)
        if not wav_path_obj.is_file():
            _LOGGER.error(f"WAV file not found: {wav_path_obj}")
            return

        try:
            seconds_to_mute = 0
            if mute:
                with wave.open(str(wav_path_obj), "rb") as wav_file:
                    seconds_to_mute = wav_file.getnframes() / wav_file.getframerate()
                # Removed mic specific mute logic
                # seconds_to_mute += self.settings.mic.seconds_to_mute_after_awake_wav
                # _LOGGER.debug("Muting microphone for %s second(s)", seconds_to_mute)
                # self.microphone_muted = True
                # self._unmute_microphone_task = asyncio.create_task(
                #     self._unmute_microphone_after(seconds_to_mute)
                # )
                if seconds_to_mute > 0:
                    _LOGGER.debug("WAV duration: %s second(s) (muting info removed)", seconds_to_mute)

            # Assume snd samples_per_chunk exists - needs setting access?
            # Let's use a default or get from settings if available
            samples_per_chunk = 1024 # Default
            if self.settings.snd and hasattr(self.settings.snd, 'samples_per_chunk'):
                samples_per_chunk = self.settings.snd.samples_per_chunk
            
            # Pass the Path object to wav_to_events
            for event in wav_to_events(wav_path_obj, samples_per_chunk=samples_per_chunk):
                await self.event_to_snd(event, is_tts=False)
        except Exception:
            _LOGGER.exception(f"Error playing WAV: {wav_path_obj}")
            # Unmute? No longer relevant
            # self.microphone_muted = False

    # async def _unmute_microphone_after(self, seconds: float) -> None:
    #     await asyncio.sleep(seconds)
    #     self.microphone_muted = False
    #     _LOGGER.debug("Unmuted microphone")

    # --- Trigger Handlers (Copied & adapted from SatelliteBase) --- 
    # These call run_event_command (imported) and potentially _play_wav
    async def trigger_server_connected(self) -> None:
        _LOGGER.info("Connected to server")
        if self.settings.event and self.settings.event.connected:
            await run_event_command(self.settings.event.connected)
        await self.forward_event(SatelliteConnected().event()) # Need SatelliteConnected

    async def trigger_server_disonnected(self) -> None:
        _LOGGER.info("Disconnected from server")
        if self.settings.event and self.settings.event.disconnected:
            await run_event_command(self.settings.event.disconnected)
        await self.forward_event(SatelliteDisconnected().event()) # Need SatelliteDisconnected

    async def trigger_streaming_start(self) -> None:
        _LOGGER.info("Audio streaming started")
        if self.settings.event and self.settings.event.streaming_start:
            await run_event_command(self.settings.event.streaming_start)
        await self.forward_event(StreamingStarted().event()) # Need StreamingStarted

    async def trigger_streaming_stop(self) -> None:
        _LOGGER.info("Audio streaming stopped")
        if self.settings.event and self.settings.event.streaming_stop:
            await run_event_command(self.settings.event.streaming_stop)
        await self.forward_event(StreamingStopped().event()) # Need StreamingStopped

    # trigger_detect removed (no local wake)
    # trigger_detection removed (no local wake)

    async def trigger_played(self) -> None:
        _LOGGER.debug("TTS audio played")
        if self.settings.event and self.settings.event.played:
            await run_event_command(self.settings.event.played)
        # Played event is sent automatically by snd task

    async def trigger_transcript(self, transcript: Transcript) -> None:
        _LOGGER.info(f"Transcript: {transcript.text}")
        if self.settings.event and self.settings.event.transcript:
            await run_event_command(self.settings.event.transcript, transcript.text)
        if self.settings.snd and self.settings.snd.done_wav:
            await self._play_wav(self.settings.snd.done_wav)

    async def trigger_stt_start(self) -> None:
        _LOGGER.debug("STT started")
        if self.settings.event and self.settings.event.stt_start:
            await run_event_command(self.settings.event.stt_start)

    async def trigger_stt_stop(self) -> None:
        _LOGGER.debug("STT stopped")
        if self.settings.event and self.settings.event.stt_stop:
            await run_event_command(self.settings.event.stt_stop)

    async def trigger_synthesize(self, synthesize: Synthesize) -> None:
        _LOGGER.info(f"Synthesize: {synthesize.text}") # Need Synthesize - IMPORTED
        if self.settings.event and self.settings.event.synthesize:
            await run_event_command(self.settings.event.synthesize, synthesize.text)

    async def trigger_tts_start(self) -> None:
        _LOGGER.debug("TTS started")
        if self.settings.event and self.settings.event.tts_start:
            await run_event_command(self.settings.event.tts_start)

    async def trigger_tts_stop(self) -> None:
        _LOGGER.debug("TTS stopped")
        if self.settings.event and self.settings.event.tts_stop:
            await run_event_command(self.settings.event.tts_stop)

    async def trigger_error(self, error: Error) -> None:
        _LOGGER.error(f"Server error: {error.text}")
        if self.settings.event and self.settings.event.error:
            await run_event_command(self.settings.event.error, error.text)

    async def trigger_timer_started(self, timer_started: TimerStarted) -> None:
        _LOGGER.debug(timer_started)
        if self.settings.timer and self.settings.timer.started:
            await run_event_command(self.settings.timer.started, timer_started)

    async def trigger_timer_updated(self, timer_updated: TimerUpdated) -> None:
        _LOGGER.debug(timer_updated)
        if self.settings.timer and self.settings.timer.updated:
            await run_event_command(self.settings.timer.updated, timer_updated)

    async def trigger_timer_cancelled(self, timer_cancelled: TimerCancelled) -> None:
        _LOGGER.debug(timer_cancelled)
        if self.settings.timer and self.settings.timer.cancelled:
            await run_event_command(self.settings.timer.cancelled, timer_cancelled.id)

    async def trigger_timer_finished(self, timer_finished: TimerFinished) -> None:
        _LOGGER.debug(timer_finished)
        if self.settings.timer and self.settings.timer.finished:
            await run_event_command(self.settings.timer.finished, timer_finished.id)
        if self.settings.timer and self.settings.timer.finished_wav:
            plays = self.settings.timer.finished_wav_plays
            delay = self.settings.timer.finished_wav_delay
            for i in range(plays):
                await self._play_wav(self.settings.timer.finished_wav)
                if (i < plays - 1) and (delay > 0):
                    await asyncio.sleep(delay)

    # --- Pipeline Control (Adapted from SatelliteBase) --- 
    async def _send_run_pipeline(self, pipeline_name: Optional[str] = None) -> None:
        from wyoming.pipeline import PipelineStage, RunPipeline # Import here

        # VAD satellite always starts at ASR stage
        start_stage = PipelineStage.ASR
        restart_on_end = False # VAD manages restart implicitly

        end_stage = PipelineStage.HANDLE # Default end stage
        if self.settings.snd and self.settings.snd.enabled:
             end_stage = PipelineStage.TTS

        run_pipeline = RunPipeline(
            start_stage=start_stage,
            end_stage=end_stage,
            name=pipeline_name,
            restart_on_end=restart_on_end,
            snd_format=None, # Server uses its preferred format
        ).event()
        _LOGGER.debug(run_pipeline)
        await self.event_to_server(run_pipeline)
        await self.forward_event(run_pipeline) # Also forward to event service

    # --- VAD Processing (Core logic) --- 
    async def process_audio_chunk(self, pcm_data: bytes):
        """Receives PCM audio, performs VAD, and streams if needed."""
        if self._is_paused or (self.server_id is None): # Don't process if paused or no server
            return

        # Debug audio recording (if enabled)
        if self.stt_audio_writer is not None:
            self.stt_audio_writer.write(pcm_data)

        # VAD Logic (adapted from VadStreamingSatellite.event_from_mic)
        if not self.is_streaming:
            # Check VAD
            if not self.vad(pcm_data):
                # No speech
                if self.vad_buffer is not None:
                    self.vad_buffer.put(pcm_data)
                return

            # --- Speech detected --- 
            self.is_streaming = True
            _LOGGER.info("Speech detected, streaming audio")

            # Start pipeline on server
            await self._send_run_pipeline()
            await self.trigger_streaming_start()

            self.timeout_seconds = None # Server handles wake timeout

            # Send VAD buffer contents first
            if self.vad_buffer is not None:
                 buffered_audio = self.vad_buffer.getvalue()
                 if buffered_audio:
                     _LOGGER.debug(f"Sending {len(buffered_audio)} bytes from VAD buffer")
                     vad_chunk = AudioChunk(
                         rate=OPUS_SAMPLE_RATE,
                         width=PCM_SAMPLE_WIDTH,
                         channels=OPUS_CHANNELS,
                         audio=buffered_audio,
                     ).event()
                     await self.event_to_server(vad_chunk)

            # Reset VAD state
            self._reset_vad()

            # Start debug recording if enabled
            if self.stt_audio_writer is not None:
                 self.stt_audio_writer.start()

        # If streaming, forward the current chunk
        if self.is_streaming:
            chunk = AudioChunk(
                rate=OPUS_SAMPLE_RATE,
                width=PCM_SAMPLE_WIDTH,
                channels=OPUS_CHANNELS,
                audio=pcm_data,
            ).event()
            await self.event_to_server(chunk)

    def _reset_vad(self):
         """Reset state of VAD."""
         self.vad(None) # Reset internal VAD state
         if self.vad_buffer is not None:
             # Clear buffer (fill with zeros/silence)
             self.vad_buffer.put(bytes(self.vad_buffer.maxlen))

    # --- Server Event Processing --- 
    async def event_from_server(self, event: Event) -> None:
        # Handle base events (ping, pong, server audio, timers)
        forward_event = await self._handle_base_server_event(event)

        # Handle VAD state changes based on server events
        if RunSatellite.is_type(event.type):
            self._is_paused = False
            self.is_streaming = False # Ensure reset
            self._reset_vad()
            _LOGGER.info("Run command received, waiting for speech")
        elif PauseSatellite.is_type(event.type):
            self._is_paused = True
            self.is_streaming = False # Stop streaming if paused
            _LOGGER.info("Pause command received, pausing VAD")
        elif Transcript.is_type(event.type):
            # Pipeline finished successfully
            self.is_streaming = False
            await self.trigger_transcript(Transcript.from_event(event))
            self._reset_vad() # Prepare for next VAD trigger
            _LOGGER.info("Transcript received, waiting for speech")
        elif Error.is_type(event.type):
            # Pipeline finished with error
            self.is_streaming = False
            await self.trigger_error(Error.from_event(event))
            self._reset_vad() # Prepare for next VAD trigger
            _LOGGER.warning("Error received, waiting for speech")

        # Stop debug recording when streaming stops
        if not self.is_streaming and self.stt_audio_writer is not None:
            self.stt_audio_writer.stop()

        # Forward other events if event service is configured
        if forward_event:
            await self.forward_event(event)

    async def _handle_base_server_event(self, event: Event) -> bool:
        """Handles common server events like ping/pong, TTS audio, timers. Returns True if event should be forwarded."""
        if Ping.is_type(event.type):
            ping = Ping.from_event(event)
            await self.event_to_server(Pong(text=ping.text).event())
            if not self._ping_server_enabled:
                self._enable_ping()
                _LOGGER.debug("Ping enabled")
            return False # Don't forward ping
        elif Pong.is_type(event.type):
            self._pong_received_event.set()
            return False # Don't forward pong
        elif AudioChunk.is_type(event.type):
            await self.event_to_snd(event) # is_tts=True (default)
            return False # Don't forward TTS audio chunks
        elif AudioStart.is_type(event.type):
            await self.event_to_snd(event)
            await self.trigger_tts_start()
            return True # Forward TTS start
        elif AudioStop.is_type(event.type):
            await self.event_to_snd(event)
            await self.trigger_tts_stop()
            return True # Forward TTS stop
        elif Synthesize.is_type(event.type):
            await self.trigger_synthesize(Synthesize.from_event(event))
            return True # Forward synthesize request
        elif TimerStarted.is_type(event.type):
            await self.trigger_timer_started(TimerStarted.from_event(event))
            return True
        elif TimerUpdated.is_type(event.type):
            await self.trigger_timer_updated(TimerUpdated.from_event(event))
            return True
        elif TimerCancelled.is_type(event.type):
            await self.trigger_timer_cancelled(TimerCancelled.from_event(event))
            return True
        elif TimerFinished.is_type(event.type):
            await self.trigger_timer_finished(TimerFinished.from_event(event))
            return True
        
        # Forward unknown events by default
        return True

    # update_info method is not needed here as Info is built in SatelliteHandler

# -----------------------------------------------------------------------------
# Satellite Handler (Connects Satellite to Server)
# (Keep this class here as it's tightly coupled with WebSocketVadSatellite)
# -----------------------------------------------------------------------------

class SatelliteHandler(AsyncEventHandler):
    """Event handler connecting WebSocketVadSatellite to the Wyoming server."""

    # Store cli_args to construct Info object
    def __init__(self, satellite: WebSocketVadSatellite, cli_args: argparse.Namespace, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.satellite = satellite
        self.cli_args = cli_args

    async def handle_event(self, event, client_id, writer) -> bool:
        """Handle events from the server."""
        if self.satellite.server_id is None:
            await self.satellite.set_server(client_id, writer)

        # Let the satellite instance process the event
        await self.satellite.event_from_server(event)

        # Don't forward server events back to server
        return False

    async def get_info(self) -> Optional[Info]:
        """Return Info constructed from CLI args."""
        # Get base satellite info from settings if available
        # This part is tricky as SatelliteBase.__init__ wasn't called
        # Let's manually create the satellite part of Info
        info = Info(
            satellite=Satellite(
                name=self.cli_args.name,
                area=self.cli_args.area,
                description=f"{self.cli_args.name} (WebSocket VAD Input)",
                attribution=Attribution(name="", url=""),
                installed=True,
                version=__version__,
            )
            # We might want to add snd/event info here if possible
            # snd=...?
            # events=...?
        )
        return info

    async def disconnected(self) -> None:
        """Client disconnected."""
        _LOGGER.debug("Server disconnected")
        await self.satellite.clear_server()