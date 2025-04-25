#!/usr/bin/env python3
import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

# WebSocket and Opus decoding
import websockets

# Local imports for satellite and settings
from omi_satellite.omi_vad_satellite import (
    OPUS_CHANNELS,
    OPUS_FRAME_SIZE,
    OPUS_SAMPLE_RATE,
    SatelliteHandler,
    WebSocketVadSatellite,
)
from opuslib import Decoder as OpusDecoder
from wyoming.server import AsyncServer
from wyoming_satellite.settings import (
    EventSettings,
    MicSettings,
    SatelliteSettings,
    SndSettings,
    TimerSettings,
    VadSettings,
    WakeSettings,
)
from wyoming_satellite.utils import run_event_command, split_command

_LOGGER = logging.getLogger(__name__) # Use module name

async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser()

    # --- Server Connection ---
    parser.add_argument("--server-uri", required=True, help="unix:// or tcp:// URI of the central Wyoming server (e.g., Home Assistant)")

    # --- WebSocket Audio Input ---
    parser.add_argument("--websocket-host", default="0.0.0.0", help="Host for WebSocket audio input server")
    parser.add_argument("--websocket-port", type=int, default=8765, help="Port for WebSocket audio input server")

    # --- VAD Settings ---
    parser.add_argument("--vad-threshold", type=float, default=0.5)
    parser.add_argument("--vad-trigger-level", type=int, default=1)
    parser.add_argument("--vad-buffer-seconds", type=float, default=2)
    parser.add_argument(
        "--vad-wake-word-timeout",
        type=float,
        default=5.0,
        help="Seconds before stopping stream if wake word isn't detected by server (used by server pipeline)",
    )

    # --- Sound Output ---
    parser.add_argument("--snd-uri", help="URI of Wyoming sound service")
    parser.add_argument("--snd-command", help="Program to run for sound output")
    parser.add_argument(
        "--snd-command-rate",
        type=int,
        default=22050,
        help="Sample rate of snd-command (hertz, default: 22050)",
    )
    parser.add_argument(
        "--snd-command-width",
        type=int,
        default=2,
        help="Sample width of snd-command (bytes, default: 2)",
    )
    parser.add_argument(
        "--snd-command-channels",
        type=int,
        default=1,
        help="Sample channels of snd-command (default: 1)",
    )
    parser.add_argument("--snd-volume-multiplier", type=float, default=1.0)

    # --- External Event Handlers ---
    parser.add_argument(
        "--event-uri", help="URI of Wyoming service to forward events to"
    )
    parser.add_argument(
        "--startup-command", help="Command run when the satellite starts"
    )
    parser.add_argument(
        "--transcript-command",
        help="Command to run when speech to text transcript is returned",
    )
    parser.add_argument(
        "--stt-start-command",
        help="Command to run when the user starts speaking",
    )
    parser.add_argument(
        "--stt-stop-command",
        help="Command to run when the user stops speaking",
    )
    parser.add_argument(
        "--synthesize-command",
        help="Command to run when text to speech text is returned",
    )
    parser.add_argument(
        "--tts-start-command",
        help="Command to run when text to speech response starts",
    )
    parser.add_argument(
        "--tts-stop-command",
        help="Command to run when text to speech response stops",
    )
    parser.add_argument(
        "--tts-played-command",
        help="Command to run when text-to-speech audio stopped playing",
    )
    parser.add_argument(
        "--streaming-start-command",
        help="Command to run when audio streaming starts",
    )
    parser.add_argument(
        "--streaming-stop-command",
        help="Command to run when audio streaming stops",
    )
    parser.add_argument(
        "--error-command",
        help="Command to run when an error occurs",
    )
    parser.add_argument(
        "--connected-command",
        help="Command to run when connected to the server",
    )
    parser.add_argument(
        "--disconnected-command",
        help="Command to run when disconnected from the server",
    )
    parser.add_argument(
        "--timer-started-command",
        help="Command to run when a timer starts",
    )
    parser.add_argument(
        "--timer-updated-command",
        help="Command to run when a timer is paused, resumed, or has time added or removed",
    )
    parser.add_argument(
        "--timer-cancelled-command",
        "--timer-canceled-command",
        help="Command to run when a timer is cancelled",
    )
    parser.add_argument(
        "--timer-finished-command",
        help="Command to run when a timer finishes",
    )

    # --- Sounds ---
    parser.add_argument(
        "--done-wav", help="WAV file to play when voice command is done"
    )
    parser.add_argument(
        "--timer-finished-wav", help="WAV file to play when a timer finishes"
    )
    parser.add_argument(
        "--timer-finished-wav-repeat",
        nargs=2,
        metavar=("repeat", "delay"),
        type=float,
        default=(1, 0),
        help="Number of times to play timer finished WAV and delay between repeats in seconds",
    )

    # --- Satellite Details ---
    parser.add_argument(
        "--name", default="Omi WebSocket VAD Satellite", help="Name of the satellite"
    )
    parser.add_argument("--area", help="Area name of the satellite")

    # --- Debugging/Misc ---
    parser.add_argument(
        "--debug-recording-dir", help="Directory to store audio for debugging (PCM after decode)"
    )
    parser.add_argument("--debug", action="store_true", help="Log DEBUG messages")
    parser.add_argument(
        "--log-format", default=logging.BASIC_FORMAT, help="Format for log messages"
    )
    parser.add_argument(
        "--version",
        action="version",
        version="69.0",
        help="Print version and exit",
    )
    args = parser.parse_args()

    # --- Validate Args & Setup Logging ---
    # VAD dependency check
    try:
        import pysilero_vad  # noqa: F401
    except ImportError:
        _LOGGER.exception("Extras for silerovad are not installed (pip install wyoming_satellite[silerovad])")
        sys.exit(1)

    # Opus dependency check
    try:
        import opuslib  # noqa: F401
    except ImportError:
        _LOGGER.exception("python-opus is not installed (pip install python-opus)")
        sys.exit(1)

    # WebSocket dependency check
    try:
        import websockets  # noqa: F401
    except ImportError:
        _LOGGER.exception("websockets is not installed (pip install websockets)")
        sys.exit(1)

    if args.done_wav and (not Path(args.done_wav).is_file()):
        _LOGGER.fatal("%s does not exist", args.done_wav)
        sys.exit(1)

    if args.timer_finished_wav and (not Path(args.timer_finished_wav).is_file()):
        _LOGGER.fatal("%s does not exist", args.timer_finished_wav)
        sys.exit(1)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO, format=args.log_format
    )
    _LOGGER.debug(args)

    debug_recording_path: Optional[Path] = None
    if args.debug_recording_dir:
        debug_recording_path = Path(args.debug_recording_dir)
        _LOGGER.info("Recording audio to %s", debug_recording_path)

    # --- Construct settings from args ---
    settings = SatelliteSettings(
        mic=MicSettings(), # Default empty MicSettings
        vad=VadSettings(
            enabled=True, # Force VAD enabled
            threshold=args.vad_threshold,
            trigger_level=args.vad_trigger_level,
            buffer_seconds=args.vad_buffer_seconds,
            wake_word_timeout=args.vad_wake_word_timeout,
        ),
        wake=WakeSettings(), # Default empty object
        snd=SndSettings(
            uri=args.snd_uri,
            command=split_command(args.snd_command),
            rate=args.snd_command_rate,
            width=args.snd_command_width,
            channels=args.snd_command_channels,
            volume_multiplier=args.snd_volume_multiplier,
            awake_wav=None, # Not used
            done_wav=args.done_wav,
        ),
        event=EventSettings(
            uri=args.event_uri,
            startup=split_command(args.startup_command),
            streaming_start=split_command(args.streaming_start_command),
            streaming_stop=split_command(args.streaming_stop_command),
            detect=None, # Not used
            detection=None, # Not used
            played=split_command(args.tts_played_command),
            transcript=split_command(args.transcript_command),
            stt_start=split_command(args.stt_start_command),
            stt_stop=split_command(args.stt_stop_command),
            synthesize=split_command(args.synthesize_command),
            tts_start=split_command(args.tts_start_command),
            tts_stop=split_command(args.tts_stop_command),
            error=split_command(args.error_command),
            connected=split_command(args.connected_command),
            disconnected=split_command(args.disconnected_command),
        ),
        timer=TimerSettings(
            started=split_command(args.timer_started_command),
            updated=split_command(args.timer_updated_command),
            cancelled=split_command(args.timer_cancelled_command),
            finished=split_command(args.timer_finished_command),
            finished_wav=args.timer_finished_wav,
            finished_wav_plays=int(args.timer_finished_wav_repeat[0]),
            finished_wav_delay=args.timer_finished_wav_repeat[1],
        ),
        # Pass the Path object for debug recording dir
        debug_recording_dir=debug_recording_path,
    )

    if settings.event and settings.event.startup:
        await run_event_command(settings.event.startup)

    _LOGGER.info("Starting WebSocket VAD satellite")

    # --- Create Satellite Instance ---
    satellite = WebSocketVadSatellite(settings)

    # --- Wyoming Server Connection (to Home Assistant) ---
    server = AsyncServer.from_uri(args.server_uri)

    # Use a factory function for the handler, passing args for info generation
    def handler_factory(*args_factory, **kwargs_factory):
        # Pass the parsed args namespace, not the satellite settings object
        return SatelliteHandler(satellite, args, *args_factory, **kwargs_factory)

    # --- Start Tasks ---
    # Task for the satellite's internal processing (event handling, sound output, etc.)
    satellite_task = asyncio.create_task(satellite.run(), name="satellite run")

    # Task for connecting to the main Wyoming server (Home Assistant)
    server_task = asyncio.create_task(server.run(handler_factory), name="server connection")

    # Task for the WebSocket audio input server
    websocket_server_task = asyncio.create_task(
        run_websocket_server(satellite, args.websocket_host, args.websocket_port),
        name="websocket server"
    )

    _LOGGER.info(f"WebSocket audio server listening on ws://{args.websocket_host}:{args.websocket_port}")
    _LOGGER.info(f"Waiting for Wyoming server to connect to {args.server_uri}")

    # --- Wait for Tasks --- 
    try:
        # Wait for any task to finish (likely an error or cancellation)
        done, pending = await asyncio.wait(
            [satellite_task, server_task, websocket_server_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Check for exceptions in completed tasks
        for task in done:
            exc = task.exception()
            if exc:
                # Log specific connection errors differently
                if isinstance(exc, ConnectionRefusedError):
                     _LOGGER.fatal("Connection refused to server at %s", args.server_uri)
                elif isinstance(exc, websockets.exceptions.WebSocketException):
                     _LOGGER.error(f"WebSocket server error: {exc}")
                else:
                     _LOGGER.error(f"Task {task.get_name()} failed: {exc}", exc_info=exc)

    except asyncio.CancelledError:
        _LOGGER.info("Main task cancelled, shutting down...")
    except Exception:
        _LOGGER.exception("Unexpected error in main task loop")
    finally:
        _LOGGER.info("Shutting down...")
        # Gracefully stop tasks
        all_tasks = [websocket_server_task, server_task, satellite_task]
        for task in all_tasks:
            if task and not task.done():
                task.cancel()
        
        # Wait for tasks to actually cancel
        await asyncio.gather(*all_tasks, return_exceptions=True)

        _LOGGER.info("Shutdown complete")

# -----------------------------------------------------------------------------
# WebSocket Server Implementation (belongs in main.py)
# -----------------------------------------------------------------------------

async def run_websocket_server(satellite: WebSocketVadSatellite, host: str, port: int):
    """Runs the WebSocket server for audio input."""
    
    # Use partial to pass satellite instance to the handler factory
    # handler_with_satellite = partial(websocket_audio_handler, satellite=satellite)
    
    # Need to define the handler inside or pass satellite differently
    # because serve() expects a coroutine websocket_handler(websocket, path)
    async def websocket_audio_handler(websocket: websockets.ServerConnection):
        """Handles a single WebSocket client connection."""
        _LOGGER.info(f"WebSocket client connected: {websocket.remote_address}")
        decoder = OpusDecoder(OPUS_SAMPLE_RATE, OPUS_CHANNELS)
        try:
            while True:
                # Set a timeout for receiving data to detect stalled connections
                try:
                    opus_data = await asyncio.wait_for(websocket.recv(), timeout=30.0)
                except asyncio.TimeoutError:
                    _LOGGER.warning(f"WebSocket timeout receiving from {websocket.remote_address}")
                    # Send a ping to see if client is still responsive
                    try:
                        await websocket.ping()
                        continue # Continue loop if ping is acked implicitly or successful
                    except websockets.exceptions.ConnectionClosed:
                        _LOGGER.warning(f"WebSocket client {websocket.remote_address} closed after ping timeout.")
                        break
                except asyncio.CancelledError:
                    raise # Propagate cancellation

                if not isinstance(opus_data, bytes):
                    _LOGGER.warning(f"Received non-bytes data from {websocket.remote_address}, ignoring.")
                    continue
                
                if not opus_data:
                    _LOGGER.info(f"Received empty bytes from {websocket.remote_address}, client may be closing.")
                    continue # Or break?

                try:
                    # Decode Opus packet
                    pcm_data = decoder.decode(opus_data, OPUS_FRAME_SIZE, decode_fec=False)
                    if pcm_data:
                        # Pass PCM data to the satellite for VAD processing
                        await satellite.process_audio_chunk(pcm_data)
                except Exception as e:
                    _LOGGER.error(f"Opus decode error for client {websocket.remote_address}: {e}")
                    # Optionally break or continue depending on desired robustness
                    continue

        except websockets.exceptions.ConnectionClosedOK:
            _LOGGER.info(f"WebSocket client disconnected normally: {websocket.remote_address}")
        except websockets.exceptions.ConnectionClosedError as e:
            _LOGGER.warning(f"WebSocket client {websocket.remote_address} disconnected with error: {e}")
        except asyncio.CancelledError:
            _LOGGER.info(f"WebSocket handler for {websocket.remote_address} cancelled.")
            # Do not re-raise cancellation here, allow server to handle shutdown
        except Exception as e:
            _LOGGER.exception(f"Unexpected error in WebSocket handler for {websocket.remote_address}: {e}")
        finally:
            _LOGGER.info(f"WebSocket connection closed: {websocket.remote_address}")

    try:
        # The serve function runs the server until cancelled
        server = await websockets.serve(websocket_audio_handler, host, port)
        _LOGGER.info(f"WebSocket server started on ws://{host}:{port}")
        await server.wait_closed() # Keep server running until stopped
    except asyncio.CancelledError:
        _LOGGER.info("WebSocket server task cancelled.")
    except Exception as e:
        _LOGGER.exception(f"WebSocket server failed to start or run: {e}")
    finally:
        _LOGGER.info("WebSocket server stopped.")

# -----------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _LOGGER.info("Received KeyboardInterrupt, shutting down...")
    except Exception as e:
        _LOGGER.exception(f"Unhandled error in main execution: {e}")
