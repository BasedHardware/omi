"""Public LibriSpeech qualification; emits numeric receipts, never turns/vectors/text.

Prepare locally with --prepare DIR; then stage corpus.pcm + manifest.json under a
synthetic GCS prefix. Run the matrix against ONE replica using the shipping client.
See docs/diarizer-batch-stagec-load.md for lead-owned probe commands.
"""

import argparse
import asyncio
import hashlib
import io
import itertools
import json
import os
from pathlib import Path
import shutil
import tarfile
import time
from urllib.request import urlopen

import httpx
import soundfile
from google.cloud import storage
from prometheus_client.parser import text_string_to_metric_families
from utils.stt.diarization import HttpDiarizer

SOURCE = 'https://openslr.trmal.net/resources/12/test-clean.tar.gz'
SOURCE_MD5 = '32fa31d27d2e1cad72775fee3f4849a9'
LICENSE = 'https://creativecommons.org/licenses/by/4.0/'
BYTES_PER_SECOND = 32000
MINUTES = (5, 15, 30, 60, 120)


def digest(path, algorithm='sha256'):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, algorithm).hexdigest()


def prepare(directory):
    """Read FLAC only, round-robin four speakers; no transcript extraction."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / 'test-clean.tar.gz'
    if not archive.exists():
        partial = archive.with_suffix('.partial')
        with urlopen(SOURCE, timeout=60) as source, partial.open('wb') as target:
            shutil.copyfileobj(source, target)
        partial.replace(archive)
    if digest(archive, 'md5') != SOURCE_MD5:
        raise ValueError('OpenSLR archive checksum mismatch')
    with tarfile.open(archive) as source:
        members = [m for m in source.getmembers() if m.isfile() and m.name.endswith('.flac')]
        speakers = sorted({m.name.split('/')[-3] for m in members})[:4]
        groups = [[] for _ in speakers]
        for member in sorted(members, key=lambda m: m.offset_data):
            speaker = member.name.split('/')[-3]
            if speaker not in speakers:
                continue
            extracted = source.extractfile(member)
            if extracted is None:
                raise ValueError('missing public FLAC')
            with extracted:
                samples, rate = soundfile.read(io.BytesIO(extracted.read()), dtype='int16')
            if rate != 16000 or samples.ndim != 1 or not len(samples):
                raise ValueError('expected mono 16kHz public source')
            groups[speakers.index(speaker)].append((Path(member.name).stem, samples.astype('<i2').tobytes()))
        groups = [sorted(group) for group in groups]
        if len(groups) != 4 or any(not group for group in groups):
            raise ValueError('four public speakers required')
        cursors = [itertools.cycle(group) for group in groups]
        reference, offset, maximum = [], 0, 120 * 60 * BYTES_PER_SECOND
        with (directory / 'corpus.pcm').open('wb') as target:
            for index in itertools.cycle(range(4)):
                clip, full_pcm = next(cursors[index])
                pcm = full_pcm[: maximum - offset]
                target.write(pcm)
                reference.append(
                    dict(clip=clip, speaker=speakers[index], start=offset / 32000, end=(offset + len(pcm)) / 32000)
                )
                offset += len(pcm)
                if offset == maximum:
                    break
    manifest = dict(
        corpus='LibriSpeech test-clean',
        source=SOURCE,
        source_md5=SOURCE_MD5,
        attribution='Vassil Panayotov, Daniel Povey, Guoguo Chen, Sanjeev Khudanpur; OpenSLR SLR12',
        license=LICENSE,
        modification='four-speaker round-robin concatenation; repeated clips; no overlap',
        sha256=digest(directory / 'corpus.pcm'),
        bytes=maximum,
        sample_rate=16000,
        speakers=speakers,
        reference=reference,
    )
    (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({k: v for k, v in manifest.items() if k != 'reference'}), flush=True)


def load_corpus(directory):
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text())
    path = directory / 'corpus.pcm'
    if (
        manifest.get('source') != SOURCE
        or manifest.get('source_md5') != SOURCE_MD5
        or manifest.get('license') != LICENSE
        or len(set(manifest.get('speakers', []))) != 4
        or manifest.get('bytes') != 7200 * BYTES_PER_SECOND
        or manifest.get('sample_rate') != 16000
        or path.stat().st_size != manifest['bytes']
        or digest(path) != manifest.get('sha256')
    ):
        raise ValueError('public corpus provenance/format/hash mismatch')
    return manifest


def stage_download(prefix, directory):
    """ADC reads only the two explicitly named synthetic objects; never lists buckets."""
    if not prefix.startswith('gs://'):
        raise ValueError('GCS prefix required')
    bucket, separator, key = prefix[5:].partition('/')
    if not separator or not key.startswith('synthetic/diarizer-bench/'):
        raise ValueError('expected synthetic/diarizer-bench/ prefix')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    client = storage.Client()
    for name in ('manifest.json', 'corpus.pcm'):
        client.bucket(bucket).blob(key.rstrip('/') + '/' + name).download_to_filename(
            str(directory / name), timeout=120, retry=None
        )


def metric_values(body, name, node=None):
    return [
        sample.value
        for family in text_string_to_metric_families(body)
        for sample in family.samples
        if sample.name == name and (node is None or sample.labels.get('Hostname') == node) and 0 <= sample.value <= 100
    ]


async def gpu_samples(url, node, stop, samples):
    async with httpx.AsyncClient(timeout=2) as client:
        while not stop.is_set():
            try:
                response = await client.get(url)
                response.raise_for_status()
                values = metric_values(response.text, 'DCGM_FI_DEV_GPU_UTIL', node)
                samples.extend({'monotonic': time.monotonic(), 'util_percent': v} for v in values)
            except (httpx.HTTPError, ValueError):
                pass
            try:
                await asyncio.wait_for(stop.wait(), timeout=1)
            except TimeoutError:
                pass


def request(pcm, timeout):
    started = time.monotonic()
    audio = len(pcm) / BYTES_PER_SECOND
    try:
        result = HttpDiarizer('pyannote').diarize(pcm, deadline=started + timeout)
        wall = time.monotonic() - started
        inference = getattr(result, 'inference_seconds', None)
        return dict(
            outcome='ok',
            audio_seconds=audio,
            wall_seconds=wall,
            wall_rtf=wall / audio,
            server_audio_seconds=getattr(result, 'audio_seconds', None),
            inference_seconds=inference,
            inference_rtf=inference / audio if inference is not None else None,
            client_minus_inference_seconds=wall - inference if inference is not None else None,
            # The served revision has no component timers. Never infer stage durations.
            stage_seconds=dict.fromkeys(('model_load', 'vad', 'embeddings', 'clustering', 'cpu')),
            speakers=len(result.centroids),
            turns=len(result.turns),
            provenance=result.provenance,
        )
    except Exception as error:
        return dict(
            outcome='failed',
            audio_seconds=audio,
            wall_seconds=time.monotonic() - started,
            error=type(error).__name__,
            status=getattr(getattr(error, 'response', None), 'status_code', None),
        )


async def wave(pcm, concurrency, timeout, dcgm_url=None, dcgm_node=None):
    stop, samples = asyncio.Event(), []
    sampler = asyncio.create_task(gpu_samples(dcgm_url, dcgm_node, stop, samples)) if dcgm_url else None
    started = time.monotonic()
    try:
        results = await asyncio.gather(*(asyncio.to_thread(request, pcm, timeout) for _ in range(concurrency)))
        elapsed = time.monotonic() - started
    finally:
        stop.set()
        if sampler:
            await sampler
    return dict(
        concurrency=concurrency,
        wave_seconds=elapsed,
        requests=results,
        completed_audio_hours_per_hour=sum(r['audio_seconds'] for r in results if r['outcome'] == 'ok') / elapsed,
        gpu_samples=samples,
        gpu_util_mean=sum(s['util_percent'] for s in samples) / len(samples) if samples else None,
        gpu_measurement='dcgm_percent_samples' if samples else 'unavailable',
    )


async def run(args):
    manifest = load_corpus(args.corpus)
    os.environ['HOSTED_DIARIZATION_API_URL'] = args.base.rstrip('/')
    print(
        json.dumps(
            dict(
                event='manifest',
                corpus_sha256=manifest['sha256'],
                target=args.base,
                target_image=args.target_image,
                client_image=args.client_image,
                target_node=args.dcgm_node,
                timeout=args.timeout,
                repeats=args.repeats,
            )
        ),
        flush=True,
    )
    for minutes in MINUTES:
        with (Path(args.corpus) / 'corpus.pcm').open('rb') as stream:
            pcm = stream.read(minutes * 60 * BYTES_PER_SECOND)
        for concurrency in (1, 2):
            for repeat in range(args.repeats):
                # Existing live work invalidates an isolated per-replica sample.
                response = httpx.get(args.base.rstrip('/') + '/metrics', timeout=5)
                response.raise_for_status()
                if metric_values(response.text, 'omi_diarization_v2_queue_depth') != [0]:
                    raise RuntimeError('target queue not empty; abort without adding work')
                receipt = await wave(pcm, concurrency, args.timeout, args.dcgm_url, args.dcgm_node)
                print(json.dumps(dict(event='wave', minutes=minutes, repeat=repeat, **receipt)), flush=True)
                if any(r['outcome'] != 'ok' for r in receipt['requests']):
                    # Client cancellation does not cancel GPU jobs. Never retry or add more.
                    raise RuntimeError('matrix aborted; failed/timed-out server jobs may still be running')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', metavar='DIR')
    parser.add_argument('--corpus', default='/data')
    parser.add_argument('--gcs-prefix')
    parser.add_argument('--base', help='single batch replica URL, without /v2/diarization')
    parser.add_argument('--target-image', default='unrecorded')
    parser.add_argument('--client-image', default='unrecorded')
    parser.add_argument('--dcgm-url')
    parser.add_argument('--dcgm-node')
    parser.add_argument('--timeout', type=float, default=600)
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args()
    if args.prepare:
        prepare(args.prepare)
        return
    if not args.base or not 0 < args.timeout <= 7200 or not 1 <= args.repeats <= 10:
        parser.error('--base, timeout in (0,7200], and repeats in [1,10] required')
    if args.dcgm_url and not args.dcgm_node:
        parser.error('--dcgm-node required to prevent sampling a different node')
    if args.gcs_prefix:
        stage_download(args.gcs_prefix, args.corpus)
    asyncio.run(run(args))


if __name__ == '__main__':
    main()
