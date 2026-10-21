"""Refresh ``profile.json`` from prod aggregate metrics (ro-prod; plan F §3.4, F7).

Reads Prometheus counters/histograms only: no uid, no document, no content.
Every categorical bucket below ``K_FLOOR`` events is folded into ``other`` so a
bucket can never describe a handful of owners.

    source ~/.local/bin/gcp-agent-env.sh ro-prod
    KUBECONFIG=<copied kubeconfig> python -m testing.loadgen.refresh_profile --write
    rm -f ~/.kube/gke_gcloud_auth_plugin_cache

Fields that no prod metric measures stay in ``assumed`` with their basis, so
a reader can tell a measured shape from a modelled one.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

PROFILE_PATH = Path(__file__).with_name('profile.json')
K_FLOOR = 20
SCHEMA_VERSION = 1
DEFAULT_CONTEXT = 'gke_based-hardware_us-central1_prod-omi-gke'
PROM_PROXY = '/api/v1/namespaces/prod-omi-monitoring/services/prod-omi-kube-prometheus-s-prometheus:9090/proxy'

# Unmeasured by any prod metric; values and their basis are explicit.
ASSUMED: dict[str, Any] = {
    'reverse_upload_share': {
        'value': 0.10,
        'basis': 'unmeasured; 10-19 02:45Z ordered-head incident showed reverse-uploaded heads exist (plan F §9)',
    },
    'burst_owners': {
        'count_range': [4, 6],
        'audio_age_days': [8, 10],
        'basis': 'plan F §3.4: 4-6 heavy owners with 8-10-day-old audio',
    },
    'near_silence_empty_asr_rate': {'value': 0.29, 'basis': 'plan F §3.4 (~29% empty-ASR on near-silence)'},
    'files_per_upload': {
        'weights': {'1': 0.55, '2': 0.2, '3': 0.1, '4': 0.08, '6': 0.05, '10': 0.02},
        'basis': 'unmeasured; replace with the mirror inventory files-per-job aggregate when available',
    },
    'file_seconds': {'range': [30, 600], 'basis': 'unmeasured; device WAL flush windows'},
}


Fetch = Callable[[str, dict[str, str]], dict[str, Any]]


def kube_proxy_fetch(context: str) -> Fetch:
    """Prometheus HTTP API through the GKE service proxy (works on ro-prod)."""

    def fetch(path: str, params: dict[str, str]) -> dict[str, Any]:
        url = f'{PROM_PROXY}{path}?{urllib.parse.urlencode(params)}'
        out = subprocess.run(
            ['kubectl', '--context', context, 'get', '--raw', url], check=True, capture_output=True, timeout=120
        )
        body = json.loads(out.stdout)
        if body.get('status') != 'success':
            raise RuntimeError(f'prometheus query failed: {body.get("error", "unknown")}')
        return body['data']

    return fetch


def _vector(fetch: Fetch, query: str) -> list[tuple[dict[str, str], float]]:
    data = fetch('/api/v1/query', {'query': query})
    return [(r['metric'], float(r['value'][1])) for r in data.get('result', [])]


def _floor_shares(counts: dict[str, float], k: int = K_FLOOR) -> dict[str, float]:
    """Shares with every bucket below k events folded into 'other'."""
    kept: dict[str, float] = {}
    other = 0.0
    for key, value in counts.items():
        if value >= k:
            kept[key] = value
        else:
            other += value
    if other >= k:
        kept['other'] = kept.get('other', 0.0) + other
    total = sum(kept.values())
    if total <= 0:
        return {}
    return {key: round(value / total, 6) for key, value in sorted(kept.items())}


def _hourly_rate(fetch: Fetch, days: int, now: float) -> tuple[list[float], float, int]:
    """Accepted uploads/min per UTC hour, the overall mean, and the hours observed.

    Computed from hourly increases over hours that have samples, so a metric
    younger than the window does not dilute the rate (omi_sync_upload_total
    first appeared 10-16 14Z; a 7d increase/7d understated it ~2.3x).
    """
    data = fetch(
        '/api/v1/query_range',
        {
            'query': 'sum(increase(omi_sync_upload_total{outcome="accepted"}[1h]))',
            'start': str(int(now - days * 86400)),
            'end': str(int(now)),
            'step': '3600',
        },
    )
    sums = [0.0] * 24
    counts = [0] * 24
    for series in data.get('result', []):
        for ts, value in series.get('values', []):
            v = float(value)
            if math.isnan(v):
                continue
            hour = datetime.fromtimestamp(float(ts), timezone.utc).hour
            sums[hour] += v
            counts[hour] += 1
    by_hour = [round(sums[h] / counts[h] / 60.0, 3) if counts[h] else 0.0 for h in range(24)]
    observed = sum(counts)
    mean = round(sum(sums) / observed / 60.0, 3) if observed else 0.0
    return by_hour, mean, observed


def _age_cdf(fetch: Fetch, days: int) -> dict[str, dict[str, list[float]]]:
    rows = _vector(fetch, f'sum by (lane, le)(increase(omi_sync_recording_age_seconds_bucket[{days}d]))')
    by_lane: dict[str, dict[float, float]] = {}
    for metric, value in rows:
        le = metric.get('le', '')
        bound = math.inf if le == '+Inf' else float(le)
        by_lane.setdefault(metric.get('lane', 'unknown'), {})[bound] = value
    out: dict[str, dict[str, list[float]]] = {}
    for lane, buckets in sorted(by_lane.items()):
        total = buckets.get(math.inf, 0.0)
        if total < K_FLOOR:
            continue
        les = sorted(b for b in buckets if b != math.inf)
        # Cumulative buckets: fold any bucket adding < k events into the next one.
        kept: list[float] = []
        last = 0.0
        for le in les:
            if buckets[le] - last >= K_FLOOR:
                kept.append(le)
                last = buckets[le]
        out[lane] = {'le': kept, 'cdf': [round(buckets[le] / total, 6) for le in kept]}
    return out


def build_profile(fetch: Fetch, *, days: int = 7, now: float | None = None) -> dict[str, Any]:
    now = now if now is not None else datetime.now(timezone.utc).timestamp()
    window = f'{days}d'
    uploads = {
        (m.get('platform', 'unknown'), m.get('outcome', 'unknown')): v
        for m, v in _vector(fetch, f'sum by (platform, outcome)(increase(omi_sync_upload_total[{window}]))')
    }
    accepted = {p: v for (p, o), v in uploads.items() if o == 'accepted'}
    started = sum(v for (_, o), v in uploads.items() if o == 'started')
    failed = sum(v for (_, o), v in uploads.items() if o == 'failed')
    lanes = {
        f"{m.get('lane')}/{m.get('trust')}/{m.get('reason')}": v
        for m, v in _vector(fetch, f'sum by (lane, trust, reason)(increase(omi_sync_lane_admissions_total[{window}]))')
    }
    vad = {
        m.get('outcome', ''): v
        for m, v in _vector(
            fetch, f'sum by (outcome)(increase(omi_vad_gate_audio_seconds_total{{mode="active"}}[{window}]))'
        )
    }
    vad_total = vad.get('sent', 0.0) + vad.get('skipped', 0.0)
    shape, _, observed_hours = _hourly_rate(fetch, days, now)
    # Level from one 24h increase (the metric is present for the whole day, and a
    # long window carries little per-series extrapolation); shape from hourly
    # increases. Summed 1h increases over short-lived Cloud Run series overcount.
    day = sum(v for _, v in _vector(fetch, 'sum(increase(omi_sync_upload_total{outcome="accepted"}[1d]))'))
    mean_per_min = round(day / 1440.0, 3) if day >= K_FLOOR else 0.0
    shape_mean = sum(shape) / len([v for v in shape if v]) if any(shape) else 0.0
    by_hour = [round(v * mean_per_min / shape_mean, 3) if shape_mean else 0.0 for v in shape]
    return {
        'schema_version': SCHEMA_VERSION,
        'generated_at': datetime.fromtimestamp(now, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'window_days': days,
        'source': 'ro-prod Prometheus aggregates (omi_sync_upload_total, omi_sync_lane_admissions_total, '
        'omi_sync_recording_age_seconds, omi_vad_gate_audio_seconds_total); no uids',
        'k_floor': K_FLOOR,
        'uploads': {
            'accepted_per_min_mean': mean_per_min,
            'accepted_per_min_by_utc_hour': by_hour,
            'observed_hours': observed_hours,
            'rate_basis': 'level: 24h increase / 1440; hourly shape: 1h increases, rescaled to that level',
            'failed_share': round(failed / started, 6) if started >= K_FLOOR else 0.0,
        },
        'platform_mix': _floor_shares(accepted),
        'lane_decisions': _floor_shares(lanes),
        'recording_age_seconds': _age_cdf(fetch, days),
        'speech_share': round(vad.get('sent', 0.0) / vad_total, 6) if vad_total >= K_FLOOR else None,
        'assumed': ASSUMED,
    }


def load_profile(path: Path = PROFILE_PATH) -> dict[str, Any]:
    profile = json.loads(path.read_text())
    if profile.get('schema_version') != SCHEMA_VERSION:
        raise ValueError('unsupported loadgen profile schema')
    return profile


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--context', default=DEFAULT_CONTEXT)
    parser.add_argument('--days', type=int, default=7)
    parser.add_argument('--write', action='store_true', help=f'write {PROFILE_PATH.name} (default: print)')
    args = parser.parse_args(argv)
    profile = build_profile(kube_proxy_fetch(args.context), days=args.days)
    text = json.dumps(profile, indent=2, sort_keys=True) + '\n'
    if args.write:
        PROFILE_PATH.write_text(text)
    else:
        print(text, end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
