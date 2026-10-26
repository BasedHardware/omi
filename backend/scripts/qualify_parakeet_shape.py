"""Public/synthetic shape qualification, run as `python -m scripts.qualify_parakeet_shape`.

No application API, account, persistence or production-content inputs. Output is
aggregate timing, error distances and fixture hashes, never audio/transcripts.
Exact order-statistic p95 confidence intervals are prespecified; uncertainty is
HOLD. No noninferiority margin is allowed. Runtime must include >=60min soak.
"""

import argparse
import asyncio
import hashlib
import io
import json
import math
import os
from pathlib import Path
import random
import time
from urllib.parse import urlsplit
import wave

import httpx


def p95_interval(values, alpha=0.0008333333333333334):
    """Distribution-free binomial/order-statistic interval, no bootstrap tuning.

    Bonferroni: 2 arms x 3 metrics x 5 phases x 2 tails = 60 x (.05/60) = .05.
    An infinite upper bound means sample size cannot establish no regression.
    """
    xs = sorted(values)
    n = len(xs)
    if not n or any(not math.isfinite(x) or x < 0 for x in xs):
        return (0, math.inf)
    cumulative, low, high = 0.0, 0, n + 1
    for k in range(n + 1):
        probability = math.exp(
            math.lgamma(n + 1)
            - math.lgamma(k + 1)
            - math.lgamma(n - k + 1)
            + k * math.log(0.95)
            + (n - k) * math.log(0.05)
        )
        cumulative += probability
        if cumulative <= alpha:
            low = k + 1
        if high == n + 1 and cumulative >= 1 - alpha:
            high = k + 1
    return (xs[low - 1] if low else 0, xs[high - 1] if high <= n else math.inf)


def compare(control, candidate, alpha=0.05 / 60):
    c_low, c_high = p95_interval(control, alpha)
    t_low, t_high = p95_interval(candidate, alpha)
    state = 'PASS' if t_high <= c_low else ('ABORT' if t_low > c_high else 'HOLD')
    finite = lambda x: x if math.isfinite(x) else None
    return {
        'state': state,
        'control_n': len(control),
        'candidate_n': len(candidate),
        'control_p95_ci': [finite(c_low), finite(c_high)],
        'candidate_p95_ci': [finite(t_low), finite(t_high)],
    }


def distance(a, b):
    previous = list(range(len(b) + 1))
    for i, word in enumerate(a):
        row = [i + 1]
        for j, other in enumerate(b):
            row.append(min(row[-1] + 1, previous[j + 1] + 1, previous[j] + (word != other)))
        previous = row
    return previous[-1]


def load_manifest(path):
    manifest_path = Path(path)
    rows = json.loads(manifest_path.read_text())
    if not isinstance(rows, list) or len(rows) < 4:
        raise ValueError('need >=4 public/synthetic multilingual, multispeaker fixtures')
    fixtures = []
    for row in rows:
        if row['source_kind'] not in ('public', 'synthetic') or not row.get('source'):
            raise ValueError('public/synthetic provenance required')
        raw = (manifest_path.parent / row['file']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != row['sha256']:
            raise ValueError('fixture hash mismatch')
        with wave.open(io.BytesIO(raw)) as wav:
            if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (16000, 1, 2):
                raise ValueError('fixtures must be mono PCM16 16kHz')
            pcm = wav.readframes(wav.getnframes())
        seconds = len(pcm) / 32000
        spans = row['speech_spans']
        if (
            not row.get('reference')
            or not row.get('language')
            or not spans
            or not 0 <= row['first_speech_seconds'] < seconds
            or any(not 0 <= s['start'] < s['end'] <= seconds or not isinstance(s['speaker'], int) for s in spans)
        ):
            raise ValueError('gold speech/speaker spans and reference required')
        fixtures.append({**row, 'pcm': pcm, 'wav': raw, 'duration': seconds})
    if (
        len({f['language'] for f in fixtures}) < 2
        or max(len({s['speaker'] for s in f['speech_spans']}) for f in fixtures) < 2
    ):
        raise ValueError('multilingual and multispeaker corpus required')
    if min(f['duration'] for f in fixtures) > 10 or max(f['duration'] for f in fixtures) < 120:
        raise ValueError('short <=10s and long >=120s inputs required')
    if not any(f['first_speech_seconds'] >= 1 for f in fixtures):
        raise ValueError('silence-to-speech fixture required')
    return fixtures


async def window_probe(base, fixture):
    # Lazy imports keep statistical/schema tests free of backend initialization.
    from utils.stt.parakeet_window import WindowedParakeetSocket

    first = None
    emitted = []
    began = time.monotonic()

    def receive(segments):
        nonlocal first
        if first is None and any(s.get('text', '').strip() for s in segments):
            first = time.monotonic()
        emitted.extend(segments)

    post_seconds = []

    class MeasuredSocket(WindowedParakeetSocket):
        async def _post_window(self, *args, **kwargs):
            started = time.monotonic()
            response = await super()._post_window(*args, **kwargs)
            elapsed = time.monotonic() - started
            if response.status_code != 200 or elapsed >= 3:
                raise ValueError('live_post_status_or_latency_failed')
            post_seconds.append(elapsed)
            return response

    socket = MeasuredSocket(receive, base, 16000, lambda: None)
    # The standalone harness sends only fixture audio directly. Disable the
    # live experiment lease/replica recovery so the two URLs remain exact.
    socket._shape_route.initialized = True
    socket.replica_scoped = False
    socket.start()
    try:
        pcm = fixture['pcm']
        for offset in range(0, len(pcm), 3200):
            at = offset / 32000
            if any(s['start'] <= at < s['end'] for s in fixture['speech_spans']):
                socket.mark_speech()
            if not socket.send(pcm[offset : offset + 3200]):
                raise ValueError('window_send_failed')
            await asyncio.sleep(max(0, began + (offset + 3200) / 32000 - time.monotonic()))
        await asyncio.wait_for(socket.drain_and_close(), timeout=30)
        if first is None or socket.is_connection_dead:
            raise ValueError('no_text_or_dead_socket')
        latency = first - began - fixture['first_speech_seconds']
        if not 0 <= latency < 30:
            raise ValueError('first_text_budget_failed')
        if not post_seconds:
            raise ValueError('no_live_posts_measured')
        return latency, emitted, max(post_seconds)
    finally:
        socket.finish()
        if socket._pump_task is not None:
            await asyncio.gather(socket._pump_task, return_exceptions=True)


def quality(fixture, control, candidate):
    def normalized(segments):
        return [{key: s.get(key) for key in ('text', 'start', 'end', 'speaker', 'speaker_id')} for s in segments]

    def text(segments):
        return ' '.join(s.get('text', '') for s in segments).lower().split()

    reference = fixture['reference'].lower().split()
    ct, tt = text(control), text(candidate)
    cw, tw = distance(reference, ct), distance(reference, tt)
    cc, tc = distance(' '.join(reference), ' '.join(ct)), distance(' '.join(reference), ' '.join(tt))
    # Exact recognizer output parity also enforces omission/tail/absolute-time
    # and speaker-label parity; any difference requires HOLD or investigation.
    return {
        'pass': bool(tt) and tw <= cw and tc <= cc and normalized(control) == normalized(candidate),
        'reference_words': len(reference),
        'control_word_errors': cw,
        'candidate_word_errors': tw,
        'control_char_errors': cc,
        'candidate_char_errors': tc,
    }


def require_watcher(path, identity):
    status = json.loads(Path(path).read_text())
    observing = (
        status.get('percent') == 0
        and status.get('state') == 'HOLD'
        and status.get('reason') == 'insufficient_first_text_samples'
    )
    if (
        not 0 <= time.time() - status.get('observed_at', 0) <= 60
        or status.get('identity') != identity
        or status.get('age', 0) < 900
        or not (status.get('state') == 'ARMED' or observing)
    ):
        raise ValueError('watcher_not_ready_or_identity_changed')


async def probe_arm(base, fixture, client):
    first, segments, live_post = await window_probe(base, fixture)
    started = time.monotonic()
    response = await client.post(
        base.rstrip('/') + '/v2/transcribe',
        data={'diarize': 'true'},
        files={'file': ('fixture.wav', fixture['wav'], 'audio/wav')},
    )
    post = time.monotonic() - started
    if response.status_code != 200 or post >= 3:
        raise ValueError('v2_status_or_latency_failed')
    payload = response.json()
    if not payload.get('text') and not payload.get('segments'):
        raise ValueError('empty_v2')
    return {'first': first, 'post': live_post, 'v2_post': post, 'segments': segments, 'v2': payload}


async def run(args):
    fixtures = load_manifest(args.manifest)
    cohorts = ['pooled', *sorted({f['sha256'] for f in fixtures})]
    alpha = 0.05 / (60 * len(cohorts))
    phases = []
    receipt = {
        'schema': 1,
        'state': 'HOLD',
        'fixture_hashes': [f['sha256'] for f in fixtures],
        'test': 'exact-binomial-p95-zero-margin-pooled-and-every-fixture',
        'alpha_per_tail': alpha,
        'phases': phases,
        'identities': json.loads(Path(args.identities).read_text()),
    }
    if not receipt['identities'].get('matched_image_config_driver') or not receipt['identities'].get(
        'watcher_identity'
    ):
        raise ValueError('verified identity and watcher identity receipt required')
    require_watcher(args.watcher_status, receipt['identities']['watcher_identity'])
    if not os.getenv('HOSTED_SPEAKER_EMBEDDING_API_URL') or os.getenv('PARAKEET_WINDOW_DIARIZATION') != 'true':
        raise ValueError('same served speaker embedding path and window diarization required')
    async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
        for concurrency, seconds in [
            (1, args.step_seconds),
            (2, args.step_seconds),
            (4, args.step_seconds),
            (8, args.step_seconds),
            (args.representative_concurrency, args.soak_seconds),
        ]:
            started = time.monotonic()
            samples = {
                cohort: {a: {m: [] for m in ('first', 'post', 'v2_post')} for a in ('control', 'candidate')}
                for cohort in cohorts
            }
            qualities = []
            active_seconds = {'control': 0.0, 'candidate': 0.0}
            wave_index = 0
            # The entire wave shares one randomized arm order. Independent
            # producer randomization would silently halve/mismatch endpoint load.
            while min(active_seconds.values()) < seconds:
                require_watcher(args.watcher_status, receipt['identities']['watcher_identity'])
                wave_fixtures = [fixtures[(wave_index + i) % len(fixtures)] for i in range(concurrency)]
                order = [('control', args.control), ('candidate', args.candidate)]
                random.shuffle(order)
                results = {}
                for arm, base in order:
                    arm_started = time.monotonic()
                    tasks = [asyncio.create_task(probe_arm(base, fixture, client)) for fixture in wave_fixtures]
                    try:
                        results[arm] = await asyncio.gather(*tasks)
                    finally:
                        for task in tasks:
                            if not task.done():
                                task.cancel()
                        await asyncio.gather(*tasks, return_exceptions=True)
                    active_seconds[arm] += time.monotonic() - arm_started
                for index, fixture in enumerate(wave_fixtures):
                    pair = {arm: results[arm][index] for arm in ('control', 'candidate')}
                    parity = quality(fixture, pair['control']['segments'], pair['candidate']['segments'])
                    if not parity['pass'] or pair['control']['v2'] != pair['candidate']['v2']:
                        raise ValueError('accuracy_speaker_language_or_timestamp_parity_failed')
                    qualities.append(parity)
                    for cohort in ('pooled', fixture['sha256']):
                        for arm in samples[cohort]:
                            for metric in samples[cohort][arm]:
                                samples[cohort][arm][metric].append(pair[arm][metric])
                wave_index += concurrency
            phase = {
                'concurrency': concurrency,
                'elapsed_seconds': time.monotonic() - started,
                'active_seconds_by_arm': active_seconds,
                'quality_pairs': len(qualities),
                'quality_pass': all(q['pass'] for q in qualities),
                'comparisons': {
                    cohort: {
                        m: compare(samples[cohort]['control'][m], samples[cohort]['candidate'][m], alpha)
                        for m in ('first', 'post', 'v2_post')
                    }
                    for cohort in cohorts
                },
            }
            phases.append(phase)
            states = [v['state'] for cohort in phase['comparisons'].values() for v in cohort.values()]
            receipt['state'] = (
                'ABORT' if 'ABORT' in states else ('PASS' if all(s == 'PASS' for s in states) else 'HOLD')
            )
            Path(args.output).write_text(json.dumps(receipt, indent=2))
            print(json.dumps(phase), flush=True)
            if receipt['state'] != 'PASS':
                return 1  # Never escalate load on inconclusive evidence.
    from utils.http_client import close_all_clients

    await close_all_clients()
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--control', required=True)
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--identities', required=True)
    parser.add_argument('--watcher-status', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--step-seconds', type=int, default=900)
    parser.add_argument('--soak-seconds', type=int, default=3600)
    parser.add_argument('--representative-concurrency', type=int, choices=(1, 2, 4, 8), required=True)
    args = parser.parse_args()
    for url in (args.control, args.candidate):
        parsed = urlsplit(url)
        if (
            parsed.scheme != 'http'
            or parsed.hostname not in ('127.0.0.1', 'localhost')
            and not (parsed.hostname or '').endswith('.svc.cluster.local')
        ):
            parser.error('only isolated loopback/internal Kubernetes services allowed')
        if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
            parser.error('credentials/query/path are forbidden')
    if args.control == args.candidate or args.step_seconds < 900 or args.soak_seconds < 3600:
        parser.error('distinct services, >=15min stages and >=60min soak required')
    try:
        return asyncio.run(run(args))
    except Exception as error:
        Path(args.output).write_text(json.dumps({'state': 'ABORT', 'reason': type(error).__name__}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
