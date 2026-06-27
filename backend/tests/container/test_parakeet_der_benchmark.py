"""
Real-speech DER benchmark using VoxConverse test subset.

Downloads ~15 real multi-speaker audio clips, sends them through the
parakeet /v2/transcribe endpoint, and scores diarization error rate
against ground-truth RTTM annotations using pyannote.metrics.

Requires:
  - Parakeet server running on localhost:8080 (or PARAKEET_URL env var)
  - GPU (for ASR + diarization inference)
  - Network access (to download VoxConverse audio on first run)
  - pyannote.metrics installed

Usage (inside container with server running):
    python -m pytest tests/container/test_parakeet_der_benchmark.py -v -s

Or standalone:
    python tests/container/test_parakeet_der_benchmark.py
"""

import io
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

PARAKEET_URL = os.getenv("PARAKEET_URL", "http://127.0.0.1:8080")
VOXCONVERSE_AUDIO_URL = "https://www.robots.ox.ac.uk/~vgg/data/voxconverse/data/voxconverse_test_wav.zip"
CACHE_DIR = Path(os.getenv("VOXCONVERSE_CACHE", "/tmp/voxconverse-cache"))
MANIFEST_PATH = Path(__file__).parent / "voxconverse" / "manifest.json"
RTTM_DIR = Path(__file__).parent / "voxconverse"

MAX_CLIPS = int(os.getenv("VOXCONVERSE_MAX_CLIPS", "15"))
DER_THRESHOLD = float(os.getenv("DER_THRESHOLD", "0.40"))
PER_CLIP_DER_MAX = float(os.getenv("PER_CLIP_DER_MAX", "0.85"))
REPORT_ONLY = os.getenv("DER_REPORT_ONLY", "false").lower() == "true"
DER_RESULTS_PATH = os.getenv("DER_RESULTS_PATH")
DER_REPORT_SCHEMA_VERSION = 1


def _aggregate_components(ok_results):
    total_scored = sum(r["total"] for r in ok_results)
    total_missed = sum(r["missed"] for r in ok_results)
    total_fa = sum(r["false_alarm"] for r in ok_results)
    total_confusion = sum(r["confusion"] for r in ok_results)
    agg_der = (total_missed + total_fa + total_confusion) / total_scored if total_scored > 0 else 1.0
    return {
        "der": agg_der,
        "total": total_scored,
        "missed": total_missed,
        "false_alarm": total_fa,
        "confusion": total_confusion,
    }


def write_der_results_artifact(results, output_path=None):
    """Persist structured DER diagnostics for CI artifact upload."""
    target = output_path or DER_RESULTS_PATH
    if not target:
        return None

    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    with open(tmp_path, "w") as f:
        json.dump(results, f, indent=2, sort_keys=True)
        f.write("\n")
    tmp_path.replace(path)
    print(f"DER diagnostics written to {path}")
    return path


def load_manifest():
    with open(MANIFEST_PATH) as f:
        return json.load(f)


def download_audio_subset(clip_ids):
    """Download VoxConverse audio clips, extracting only needed files from zip."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    missing = [cid for cid in clip_ids if not (CACHE_DIR / f"{cid}.wav").exists()]
    if not missing:
        return

    gcs_url = os.getenv("VOXCONVERSE_GCS_URL")
    if gcs_url:
        for cid in missing:
            url = f"{gcs_url}/{cid}.wav"
            print(f"  Downloading {cid}.wav from GCS mirror...")
            urllib.request.urlretrieve(url, CACHE_DIR / f"{cid}.wav")
        return

    print(f"  Downloading VoxConverse test audio zip ({len(missing)} clips needed)...")
    zip_path = CACHE_DIR / "voxconverse_test_wav.zip"
    if not zip_path.exists():
        urllib.request.urlretrieve(VOXCONVERSE_AUDIO_URL, zip_path)
        print(f"  Downloaded: {zip_path.stat().st_size / 1e6:.0f} MB")

    needed = {f"audio/{cid}.wav" for cid in missing}
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        alt_needed = set()
        for cid in missing:
            for pattern in [f"audio/{cid}.wav", f"voxconverse_test_wav/{cid}.wav", f"{cid}.wav"]:
                if pattern in names:
                    alt_needed.add((pattern, cid))
                    break

        for zip_name, cid in alt_needed:
            print(f"  Extracting {cid}.wav...")
            data = zf.read(zip_name)
            (CACHE_DIR / f"{cid}.wav").write_bytes(data)

    extracted = [cid for cid in missing if (CACHE_DIR / f"{cid}.wav").exists()]
    if len(extracted) < len(missing):
        still_missing = [cid for cid in missing if cid not in extracted]
        print(f"  WARNING: Could not find audio for: {still_missing}")


def parse_rttm(rttm_path):
    """Parse RTTM file into pyannote Annotation."""
    from pyannote.core import Annotation, Segment

    ann = Annotation()
    with open(rttm_path) as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) < 8 or parts[0] != "SPEAKER":
                continue
            start = float(parts[3])
            duration = float(parts[4])
            speaker = parts[7]
            ann[Segment(start, start + duration)] = speaker
    return ann


def api_result_to_annotation(result):
    """Convert parakeet API response to pyannote Annotation."""
    from pyannote.core import Annotation, Segment

    ann = Annotation()
    for seg in result.get("segments", []):
        speaker = seg.get("speaker", "SPEAKER_0")
        ann[Segment(seg["start"], seg["end"])] = speaker
    return ann


def transcribe_clip(wav_path):
    """Send audio clip to parakeet /v2/transcribe endpoint."""
    import http.client
    import mimetypes
    from urllib.parse import urlparse

    parsed = urlparse(PARAKEET_URL)
    boundary = "----VoxConverseBenchmark"

    with open(wav_path, "rb") as f:
        file_data = f.read()

    body_parts = []
    body_parts.append(f"--{boundary}\r\n".encode())
    body_parts.append(f'Content-Disposition: form-data; name="file"; filename="{wav_path.name}"\r\n'.encode())
    body_parts.append(b"Content-Type: audio/wav\r\n\r\n")
    body_parts.append(file_data)
    body_parts.append(f"\r\n--{boundary}\r\n".encode())
    body_parts.append(b'Content-Disposition: form-data; name="diarize"\r\n\r\n')
    body_parts.append(b"true")
    body_parts.append(f"\r\n--{boundary}--\r\n".encode())

    body = b"".join(body_parts)

    conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=300)
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


def run_benchmark():
    """Run full DER benchmark and return results."""
    from pyannote.metrics.diarization import DiarizationErrorRate

    manifest = load_manifest()
    clips = manifest["clips"][:MAX_CLIPS]
    clip_ids = [c["id"] for c in clips]

    print(f"\n{'=' * 60}")
    print(f"VoxConverse DER Benchmark")
    print(f"Clips: {len(clips)}, Total audio: {sum(c['duration_s'] for c in clips):.0f}s")
    print(f"Threshold: {DER_THRESHOLD:.0%} (aggregate), {PER_CLIP_DER_MAX:.0%} (per-clip)")
    print(f"Mode: {'REPORT ONLY' if REPORT_ONLY else 'GATED'}")
    print(f"{'=' * 60}\n")

    download_audio_subset(clip_ids)

    metric = DiarizationErrorRate(collar=0.25, skip_overlap=True)
    results = []

    for clip in clips:
        cid = clip["id"]
        wav_path = CACHE_DIR / f"{cid}.wav"
        rttm_path = RTTM_DIR / f"{cid}.rttm"

        if not wav_path.exists():
            print(f"  SKIP {cid}: audio not available")
            results.append({"id": cid, "status": "skipped", "reason": "audio_missing"})
            continue

        if not rttm_path.exists():
            print(f"  SKIP {cid}: RTTM not found")
            results.append({"id": cid, "status": "skipped", "reason": "rttm_missing"})
            continue

        print(f"  [{cid}] {clip['duration_s']:.0f}s, {clip['speakers']} speakers ... ", end="", flush=True)

        try:
            t0 = time.time()
            api_result = transcribe_clip(wav_path)
            elapsed = time.time() - t0

            ref = parse_rttm(rttm_path)
            hyp = api_result_to_annotation(api_result)

            detail = metric(ref, hyp, detailed=True)
            der = detail["diarization error rate"]

            n_hyp_speakers = len(set(s.get("speaker", "") for s in api_result.get("segments", [])))

            results.append(
                {
                    "id": cid,
                    "status": "ok",
                    "der": der,
                    "missed": detail.get("missed detection", 0),
                    "false_alarm": detail.get("false alarm", 0),
                    "confusion": detail.get("confusion", 0),
                    "total": detail.get("total", 0),
                    "ref_speakers": clip["speakers"],
                    "hyp_speakers": n_hyp_speakers,
                    "elapsed_s": elapsed,
                    "rtfx": clip["duration_s"] / elapsed if elapsed > 0 else 0,
                }
            )

            status = "PASS" if der <= PER_CLIP_DER_MAX else "WARN"
            print(f"DER={der:.1%} ({status}) [{elapsed:.1f}s, {n_hyp_speakers} spk detected]")

        except Exception as e:
            print(f"ERROR: {e}")
            results.append({"id": cid, "status": "error", "error": str(e)})

    ok_results = [r for r in results if r["status"] == "ok"]

    aggregate = (
        _aggregate_components(ok_results)
        if ok_results
        else {
            "der": 1.0,
            "total": 0,
            "missed": 0,
            "false_alarm": 0,
            "confusion": 0,
        }
    )
    agg_der = aggregate["der"]

    high_der_clips = [r for r in ok_results if r["der"] > PER_CLIP_DER_MAX]
    skipped = [r for r in results if r["status"] == "skipped"]
    errors = [r for r in results if r["status"] == "error"]

    print(f"\n{'=' * 60}")
    print(f"AGGREGATE DER: {agg_der:.1%}  (threshold: {DER_THRESHOLD:.0%})")
    print(f"Clips: {len(ok_results)} scored, {len(skipped)} skipped, {len(errors)} errors")
    if high_der_clips:
        print(f"High-DER clips (>{PER_CLIP_DER_MAX:.0%}): {[r['id'] for r in high_der_clips]}")
    print(f"{'=' * 60}\n")

    result = {
        "schema_version": DER_REPORT_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "config": {
            "parakeet_url": PARAKEET_URL,
            "max_clips": MAX_CLIPS,
            "der_threshold": DER_THRESHOLD,
            "per_clip_der_max": PER_CLIP_DER_MAX,
            "report_only": REPORT_ONLY,
            "collar_s": 0.25,
            "skip_overlap": True,
        },
        "aggregate_der": agg_der,
        "aggregate": aggregate,
        "per_clip": results,
        "threshold": DER_THRESHOLD,
        "per_clip_max": PER_CLIP_DER_MAX,
        "report_only": REPORT_ONLY,
        "clips_scored": len(ok_results),
        "clips_total": len(clips),
        "clips_skipped": len(skipped),
        "clips_errored": len(errors),
    }
    write_der_results_artifact(result)
    return result


class TestDERDiagnosticsArtifact:
    def test_aggregate_components_from_synthetic_records(self):
        aggregate = _aggregate_components(
            [
                {"total": 10.0, "missed": 1.0, "false_alarm": 0.5, "confusion": 0.5},
                {"total": 30.0, "missed": 3.0, "false_alarm": 1.0, "confusion": 0.0},
            ]
        )

        assert aggregate == {
            "der": 0.15,
            "total": 40.0,
            "missed": 4.0,
            "false_alarm": 1.5,
            "confusion": 0.5,
        }

    def test_write_der_results_artifact(self, tmp_path):
        artifact_path = tmp_path / "der" / "results.json"
        results = {
            "schema_version": DER_REPORT_SCHEMA_VERSION,
            "aggregate_der": 0.341,
            "aggregate": {"der": 0.341, "total": 100.0, "missed": 10.0, "false_alarm": 4.0, "confusion": 20.1},
            "per_clip": [
                {
                    "id": "dohag",
                    "status": "ok",
                    "der": 0.052,
                    "missed": 1.0,
                    "false_alarm": 0.0,
                    "confusion": 0.1,
                    "total": 21.0,
                    "ref_speakers": 1,
                    "hyp_speakers": 1,
                }
            ],
        }

        written = write_der_results_artifact(results, artifact_path)

        assert written == artifact_path
        loaded = json.loads(artifact_path.read_text())
        assert loaded["schema_version"] == DER_REPORT_SCHEMA_VERSION
        assert loaded["aggregate"]["confusion"] == 20.1
        assert loaded["per_clip"][0]["ref_speakers"] == 1
        assert loaded["per_clip"][0]["hyp_speakers"] == 1


class TestVoxConverseDERBenchmark:
    """Real-speech DER benchmark using VoxConverse test subset."""

    @pytest.fixture(scope="class")
    def benchmark_results(self):
        return run_benchmark()

    def test_aggregate_der_below_threshold(self, benchmark_results):
        if benchmark_results["report_only"]:
            pytest.skip(f"Report-only mode: DER={benchmark_results['aggregate_der']:.1%}")

        if benchmark_results["clips_scored"] == 0:
            pytest.skip("No clips scored (audio download may have failed)")

        assert benchmark_results["aggregate_der"] <= benchmark_results["threshold"], (
            f"Aggregate DER {benchmark_results['aggregate_der']:.1%} "
            f"exceeds threshold {benchmark_results['threshold']:.0%}"
        )

    def test_no_catastrophic_per_clip_failures(self, benchmark_results):
        if benchmark_results["report_only"]:
            pytest.skip("Report-only mode")

        ok_results = [r for r in benchmark_results["per_clip"] if r["status"] == "ok"]
        catastrophic = [r for r in ok_results if r["der"] > benchmark_results["per_clip_max"]]

        if catastrophic:
            details = ", ".join(f"{r['id']}={r['der']:.0%}" for r in catastrophic)
            assert False, (
                f"{len(catastrophic)} clips exceed per-clip max " f"{benchmark_results['per_clip_max']:.0%}: {details}"
            )

    def test_minimum_clips_scored(self, benchmark_results):
        """At least 10 clips must be successfully scored."""
        if benchmark_results["report_only"]:
            pytest.skip("Report-only mode")

        assert (
            benchmark_results["clips_scored"] >= 10
        ), f"Only {benchmark_results['clips_scored']} clips scored, need at least 10"


if __name__ == "__main__":
    results = run_benchmark()
    json_path = Path("/tmp/der_benchmark_results.json")
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Results saved to {json_path}")

    if not results["report_only"] and results["aggregate_der"] > results["threshold"]:
        sys.exit(1)
