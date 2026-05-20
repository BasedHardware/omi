#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def run(command, cwd=None, env=None):
    result = subprocess.run(command, cwd=cwd, env=env, text=True)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def make_generated_audio(text, work_dir):
    aiff_path = work_dir / "generated.aiff"
    wav_path = work_dir / "generated.wav"
    pcm_path = work_dir / "generated.pcm"
    run(["say", "-o", str(aiff_path), text])
    run(
        [
            "afconvert",
            str(aiff_path),
            "-f",
            "WAVE",
            "-d",
            "LEI16@16000",
            "-c",
            "1",
            str(wav_path),
        ]
    )
    extract_wav_pcm(wav_path, pcm_path)
    return pcm_path


def convert_audio(audio_path, work_dir):
    if audio_path.suffix.lower() == ".pcm":
        return audio_path
    wav_path = work_dir / "input.wav"
    pcm_path = work_dir / "input.pcm"
    run(
        [
            "afconvert",
            str(audio_path),
            "-f",
            "WAVE",
            "-d",
            "LEI16@16000",
            "-c",
            "1",
            str(wav_path),
        ]
    )
    extract_wav_pcm(wav_path, pcm_path)
    return pcm_path


def extract_wav_pcm(wav_path, pcm_path):
    import wave

    with wave.open(str(wav_path), "rb") as wav:
        if wav.getframerate() != 16000 or wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise SystemExit(f"{wav_path} is not 16 kHz mono 16-bit PCM")
        pcm_path.write_bytes(wav.readframes(wav.getnframes()))


def main():
    parser = argparse.ArgumentParser(
        description="Run desktop local background ASR through the Swift chunker/queue/merge harness."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--audio",
        type=Path,
        help="Input audio file. .pcm is used directly; other formats use afconvert.",
    )
    source.add_argument(
        "--generate-speech",
        help="Generate a deterministic macOS speech sample with `say`.",
    )
    parser.add_argument("--mode", choices=["fixture", "local"], default="fixture")
    parser.add_argument("--output", type=Path, default=Path("/tmp/omi-local-background-asr-report.json"))
    parser.add_argument("--engine", choices=["mlx-whisper", "faster-whisper"], default="mlx-whisper")
    parser.add_argument("--model", default="base")
    parser.add_argument("--quality", default="fast")
    parser.add_argument("--language", default="en")
    parser.add_argument("--max-chunk-seconds", default="15")
    parser.add_argument("--min-chunk-seconds", default="1")
    parser.add_argument("--overlap-seconds", default="1")
    parser.add_argument("--reference", help="Optional reference transcript for WER/CER scoring.")
    parser.add_argument(
        "--deepgram-compare",
        action="store_true",
        help="Reserved extension point. Requires DEEPGRAM_API_KEY and is not used for local smoke validation.",
    )
    args = parser.parse_args()

    if args.deepgram_compare and not os.environ.get("DEEPGRAM_API_KEY"):
        raise SystemExit("--deepgram-compare requires DEEPGRAM_API_KEY")
    if args.deepgram_compare:
        print(
            "Deepgram comparison is an explicit future extension point; local smoke continues without cloud.",
            file=sys.stderr,
        )

    repo_root = Path(__file__).resolve().parents[2]
    desktop_package = repo_root / "desktop" / "Desktop"
    with tempfile.TemporaryDirectory(prefix="omi-local-bg-asr-") as temp:
        work_dir = Path(temp)
        if args.generate_speech:
            if not shutil.which("say") or not shutil.which("afconvert"):
                raise SystemExit("Generated speech requires macOS `say` and `afconvert`.")
            pcm_path = make_generated_audio(args.generate_speech, work_dir)
            fixture_text = args.generate_speech
        else:
            if not args.audio.exists():
                raise SystemExit(f"Input audio does not exist: {args.audio}")
            if args.audio.suffix.lower() != ".pcm" and not shutil.which("afconvert"):
                raise SystemExit("Non-PCM input requires macOS `afconvert`.")
            pcm_path = convert_audio(args.audio.resolve(), work_dir)
            fixture_text = args.reference or "hello local background transcription"

        env = os.environ.copy()
        env.update(
            {
                "OMI_LOCAL_BACKGROUND_ASR_HARNESS": "1",
                "OMI_LOCAL_BACKGROUND_ASR_PCM_PATH": str(pcm_path),
                "OMI_LOCAL_BACKGROUND_ASR_OUTPUT_PATH": str(args.output.resolve()),
                "OMI_LOCAL_BACKGROUND_ASR_MODE": args.mode,
                "OMI_LOCAL_BACKGROUND_ASR_FIXTURE_TEXT": fixture_text,
                "OMI_LOCAL_ASR_ENGINE": args.engine,
                "OMI_LOCAL_ASR_MODEL": args.model,
                "OMI_LOCAL_ASR_QUALITY": args.quality,
                "OMI_LOCAL_ASR_LANGUAGE": args.language,
                "OMI_LOCAL_BACKGROUND_ASR_MAX_CHUNK_SECONDS": args.max_chunk_seconds,
                "OMI_LOCAL_BACKGROUND_ASR_MIN_CHUNK_SECONDS": args.min_chunk_seconds,
                "OMI_LOCAL_BACKGROUND_ASR_OVERLAP_SECONDS": args.overlap_seconds,
            }
        )
        if args.reference:
            env["OMI_LOCAL_BACKGROUND_ASR_REFERENCE"] = args.reference

        run(
            ["swift", "test", "--filter", "LocalBackgroundSmokeHarnessTests/testRunHarness"],
            cwd=desktop_package,
            env=env,
        )

    report = json.loads(args.output.read_text())
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
