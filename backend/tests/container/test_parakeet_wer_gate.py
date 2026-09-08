"""
WER regression gate -- end-to-end test against running parakeet server.

Downloads LibriSpeech test-clean samples, transcribes via /v2/transcribe,
and gates on Word Error Rate threshold.

Follows the same pattern as test_parakeet_der_benchmark.py.

Requires:
  - Parakeet server running on localhost:8080 (or PARAKEET_URL env var)
  - GPU (for ASR inference)
  - Network access (to download LibriSpeech audio on first run)

Usage (inside container with server running):
    python -m pytest tests/container/test_parakeet_wer_gate.py -v -s

Or standalone:
    python tests/container/test_parakeet_wer_gate.py
"""

import http.client
import io
import json
import os
import struct
import sys
import tarfile
import time
import urllib.request
import wave
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
import pytest

PARAKEET_URL = os.getenv("PARAKEET_URL", "http://127.0.0.1:8080")
LIBRISPEECH_URL = "https://www.openslr.org/resources/12/test-clean.tar.gz"
CACHE_DIR = Path(os.getenv("LIBRISPEECH_CACHE", "/tmp/librispeech-cache"))
MANIFEST_PATH = Path(__file__).parent / "librispeech" / "manifest.json"

MAX_SAMPLES = int(os.getenv("WER_MAX_SAMPLES", "10"))
WER_THRESHOLD = float(os.getenv("WER_THRESHOLD", "15.0"))
PER_SAMPLE_WER_MAX = float(os.getenv("PER_SAMPLE_WER_MAX", "30.0"))
REPORT_ONLY = os.getenv("WER_REPORT_ONLY", "false").lower() == "true"


def _compute_wer(ref_text, hyp_text):
    ref_words = ref_text.strip().lower().split()
    hyp_words = hyp_text.strip().lower().split()

    if not ref_words:
        return 0.0 if not hyp_words else 100.0

    n = len(ref_words)
    m = len(hyp_words)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref_words[i - 1] == hyp_words[j - 1]:
                d[i][j] = d[i - 1][j - 1]
            else:
                d[i][j] = 1 + min(d[i - 1][j], d[i][j - 1], d[i - 1][j - 1])

    return d[n][m] / n * 100


def load_manifest():
    with open(MANIFEST_PATH) as f:
        return json.load(f)


def _flac_to_wav(flac_path, wav_path):
    import soundfile as sf

    data, samplerate = sf.read(str(flac_path))
    if data.ndim > 1:
        data = data.mean(axis=1)
    data_int16 = (data * 32767).astype(np.int16)
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(samplerate)
        wf.writeframes(data_int16.tobytes())


def download_and_extract(samples):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    needed = []
    for s in samples:
        wav_path = CACHE_DIR / f"{s['id']}.wav"
        ref_path = CACHE_DIR / f"{s['id']}.ref.txt"
        if not wav_path.exists() or not ref_path.exists():
            needed.append(s)

    if not needed:
        return

    gcs_url = os.getenv("LIBRISPEECH_GCS_URL")
    if gcs_url:
        for s in needed:
            for ext in ["wav", "ref.txt"]:
                url = f"{gcs_url}/{s['id']}.{ext}"
                dest = CACHE_DIR / f"{s['id']}.{ext}"
                print(f"  Downloading {s['id']}.{ext} from GCS mirror...")
                try:
                    urllib.request.urlretrieve(url, dest)
                except Exception as e:
                    print(f"  WARNING: GCS download failed for {s['id']}.{ext}: {e}")
        remaining = [s for s in needed if not (CACHE_DIR / f"{s['id']}.wav").exists()]
        if not remaining:
            return
        needed = remaining

    tar_path = CACHE_DIR / "test-clean.tar.gz"
    if not tar_path.exists():
        print(f"  Downloading LibriSpeech test-clean ({LIBRISPEECH_URL})...")
        urllib.request.urlretrieve(LIBRISPEECH_URL, tar_path)
        size_mb = tar_path.stat().st_size / 1e6
        print(f"  Downloaded: {size_mb:.0f} MB")

    needed_flacs = {}
    needed_trans = {}
    for s in needed:
        speaker, chapter = s["speaker"], s["chapter"]
        flac_member = f"LibriSpeech/test-clean/{speaker}/{chapter}/{s['id']}.flac"
        trans_member = f"LibriSpeech/test-clean/{speaker}/{chapter}/{speaker}-{chapter}.trans.txt"
        needed_flacs[flac_member] = s["id"]
        needed_trans[trans_member] = (speaker, chapter)

    all_needed = set(needed_flacs.keys()) | set(needed_trans.keys())

    print(f"  Extracting {len(needed)} samples from tar.gz...")
    with tarfile.open(tar_path, "r:gz") as tf:
        for member in tf:
            if member.name in all_needed:
                tf.extract(member, CACHE_DIR)

    transcripts = {}
    for trans_path, (speaker, chapter) in needed_trans.items():
        full_path = CACHE_DIR / trans_path
        if full_path.exists():
            with open(full_path) as f:
                for line in f:
                    parts = line.strip().split(" ", 1)
                    if len(parts) == 2:
                        transcripts[parts[0]] = parts[1]

    for flac_member, sample_id in needed_flacs.items():
        flac_path = CACHE_DIR / flac_member
        wav_path = CACHE_DIR / f"{sample_id}.wav"
        ref_path = CACHE_DIR / f"{sample_id}.ref.txt"

        if flac_path.exists() and not wav_path.exists():
            print(f"  Converting {sample_id}.flac -> .wav...")
            _flac_to_wav(flac_path, wav_path)

        if sample_id in transcripts and not ref_path.exists():
            ref_path.write_text(transcripts[sample_id])


def transcribe_clip(wav_path):
    parsed = urlparse(PARAKEET_URL)
    boundary = "----WERBenchmark"

    with open(wav_path, "rb") as f:
        file_data = f.read()

    body_parts = [
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{wav_path.name}"\r\n'.encode(),
        b"Content-Type: audio/wav\r\n\r\n",
        file_data,
        f"\r\n--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="diarize"\r\n\r\n',
        b"false",
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    body = b"".join(body_parts)

    conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=120)
    conn.request(
        "POST",
        "/v2/transcribe",
        body=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    resp = conn.getresponse()
    data = resp.read()
    conn.close()

    if resp.status != 200:
        raise RuntimeError(f"API returned {resp.status}: {data[:500]}")

    return json.loads(data)


def run_wer_benchmark():
    manifest = load_manifest()
    samples = manifest["samples"][:MAX_SAMPLES]

    print(f"\n{'=' * 60}")
    print(f"LibriSpeech WER Regression Gate")
    print(f"Samples: {len(samples)}")
    print(f"Threshold: {WER_THRESHOLD}% (aggregate), {PER_SAMPLE_WER_MAX}% (per-sample)")
    print(f"Mode: {'REPORT ONLY' if REPORT_ONLY else 'GATED'}")
    print(f"{'=' * 60}\n")

    download_and_extract(samples)

    results = []

    for sample in samples:
        sid = sample["id"]
        wav_path = CACHE_DIR / f"{sid}.wav"
        ref_path = CACHE_DIR / f"{sid}.ref.txt"

        if not wav_path.exists():
            print(f"  SKIP {sid}: audio not available")
            results.append({"id": sid, "status": "skipped", "reason": "audio_missing"})
            continue

        if not ref_path.exists():
            print(f"  SKIP {sid}: reference text not available")
            results.append({"id": sid, "status": "skipped", "reason": "ref_missing"})
            continue

        ref_text = ref_path.read_text().strip()

        print(f"  [{sid}] ... ", end="", flush=True)

        try:
            t0 = time.time()
            api_result = transcribe_clip(wav_path)
            elapsed = time.time() - t0

            hyp_text = api_result.get("text", "").strip()
            wer = _compute_wer(ref_text, hyp_text)

            results.append(
                {
                    "id": sid,
                    "status": "ok",
                    "wer": wer,
                    "ref_words": len(ref_text.split()),
                    "hyp_words": len(hyp_text.split()),
                    "elapsed_s": elapsed,
                    "ref_text": ref_text[:80],
                    "hyp_text": hyp_text[:80],
                }
            )

            status = "PASS" if wer <= PER_SAMPLE_WER_MAX else "FAIL"
            print(f"WER={wer:.1f}% ({status}) [{elapsed:.1f}s, {len(hyp_text.split())} words]")

        except Exception as e:
            print(f"ERROR: {e}")
            results.append({"id": sid, "status": "error", "error": str(e)})

    ok_results = [r for r in results if r["status"] == "ok"]

    if ok_results:
        total_ref_words = sum(r["ref_words"] for r in ok_results)
        total_errors = sum(r["wer"] * r["ref_words"] / 100 for r in ok_results)
        agg_wer = total_errors / total_ref_words * 100 if total_ref_words > 0 else 100.0
    else:
        agg_wer = 100.0

    high_wer = [r for r in ok_results if r["wer"] > PER_SAMPLE_WER_MAX]
    skipped = [r for r in results if r["status"] == "skipped"]
    errors = [r for r in results if r["status"] == "error"]

    print(f"\n{'=' * 60}")
    print(f"AGGREGATE WER: {agg_wer:.1f}%  (threshold: {WER_THRESHOLD}%)")
    print(f"Samples: {len(ok_results)} scored, {len(skipped)} skipped, {len(errors)} errors")
    if high_wer:
        print(f"High-WER samples (>{PER_SAMPLE_WER_MAX}%): {[r['id'] for r in high_wer]}")
    print(f"{'=' * 60}\n")

    return {
        "aggregate_wer": agg_wer,
        "per_sample": results,
        "threshold": WER_THRESHOLD,
        "per_sample_max": PER_SAMPLE_WER_MAX,
        "report_only": REPORT_ONLY,
        "samples_scored": len(ok_results),
        "samples_total": len(samples),
    }


class TestWERRegressionGate:
    """WER must stay below threshold on LibriSpeech test-clean."""

    @pytest.fixture(scope="class")
    def benchmark_results(self):
        return run_wer_benchmark()

    def test_aggregate_wer_below_threshold(self, benchmark_results):
        if benchmark_results["report_only"]:
            pytest.skip(f"Report-only mode: WER={benchmark_results['aggregate_wer']:.1f}%")

        if benchmark_results["samples_scored"] == 0:
            pytest.skip("No samples scored (audio download may have failed)")

        assert benchmark_results["aggregate_wer"] <= benchmark_results["threshold"], (
            f"Aggregate WER {benchmark_results['aggregate_wer']:.1f}% "
            f"exceeds threshold {benchmark_results['threshold']}%"
        )

    def test_no_catastrophic_per_sample_failures(self, benchmark_results):
        if benchmark_results["report_only"]:
            pytest.skip("Report-only mode")

        ok_results = [r for r in benchmark_results["per_sample"] if r["status"] == "ok"]
        catastrophic = [r for r in ok_results if r["wer"] > benchmark_results["per_sample_max"]]

        if catastrophic:
            details = ", ".join(f"{r['id']}={r['wer']:.0f}%" for r in catastrophic)
            assert False, (
                f"{len(catastrophic)} samples exceed per-sample max "
                f"{benchmark_results['per_sample_max']}%: {details}"
            )

    def test_minimum_samples_scored(self, benchmark_results):
        if benchmark_results["report_only"]:
            pytest.skip("Report-only mode")

        min_required = min(5, benchmark_results["samples_total"])
        assert (
            benchmark_results["samples_scored"] >= min_required
        ), f"Only {benchmark_results['samples_scored']} samples scored, need at least {min_required}"

    def test_all_transcriptions_nonempty(self, benchmark_results):
        if benchmark_results["report_only"]:
            pytest.skip("Report-only mode")

        ok_results = [r for r in benchmark_results["per_sample"] if r["status"] == "ok"]
        empty = [r for r in ok_results if r["hyp_words"] == 0]

        assert len(empty) == 0, f"{len(empty)} transcriptions were empty: {[r['id'] for r in empty]}"


if __name__ == "__main__":
    results = run_wer_benchmark()
    json_path = Path("/tmp/wer_benchmark_results.json")
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Results saved to {json_path}")

    if not results["report_only"] and results["aggregate_wer"] > results["threshold"]:
        sys.exit(1)
