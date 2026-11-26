"""``scenario compare`` metric ``stt_routing``: where each arm sent the audio, and how much speech Parakeet
received that it cannot transcribe.

Reads only the routed recordings' summaries in each scenario's ``result.json`` (``audio.recordings[].route``,
numbers and labels). Speech language comes from a reference that no arm computes, so an arm cannot grade
itself: ``$OMI_PIPELINE_LAB_STT_REFERENCE`` names a private JSON file ``{"<audio sha256 prefix>": {"speech_s",
"unsupported_s", "unsupported_spans": [[start, end], ...]}}`` (e.g. built from several engines' agreement on the
same audio; spans are seconds from the recording's start, no text). A mixed legacy upload counts only the
unsupported speech inside its files that went to Parakeet. Without a reference only route counts are reported.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from testing.pipeline_lab.scenario.metrics import register_metric, scenario_results

REFERENCE_ENV = 'OMI_PIPELINE_LAB_STT_REFERENCE'


def _reference() -> dict[str, dict[str, float]]:
    path = os.environ.get(REFERENCE_ENV)
    if not path:
        return {}
    raw = json.loads(Path(path).expanduser().read_text(encoding='utf-8'))
    return {str(k): v for k, v in raw.items() if isinstance(v, dict)}


@register_metric('stt_routing', description='engine per routed recording; unsupported speech sent to Parakeet')
def stt_routing_metrics(run_dir: Path) -> dict[str, Any]:
    reference = _reference()
    out: dict[str, Any] = {}
    totals = {
        'recordings': 0,
        'parakeet_recordings': 0,
        'mixed_recordings': 0,
        'lid_probes': 0,
        'self_lid_windows': 0,
        'parakeet_audio_s': 0.0,
        'multi_audio_s': 0.0,
    }
    speech = {'speech_s': 0.0, 'unsupported_s': 0.0, 'unsupported_on_parakeet_s': 0.0, 'unreferenced': 0}
    for _name, result in scenario_results(run_dir):
        for row in (result.get('audio') or {}).get('recordings') or []:
            route = row.get('route')
            if not isinstance(route, dict):
                continue
            totals['recordings'] += 1
            seconds = float(row.get('audio_seconds') or 0.0)
            on_parakeet = _parakeet_spans(route, seconds)
            parakeet_s = sum(b - a for a, b in on_parakeet)
            totals['parakeet_recordings'] += int(route.get('route') == 'parakeet')
            totals['mixed_recordings'] += int(route.get('route') == 'mixed')
            totals['lid_probes'] += int('lid_language' in route) + len(route.get('pieces') or [])
            totals['self_lid_windows'] += int(route.get('self_lid_windows') or 0)
            totals['parakeet_audio_s'] += parakeet_s
            totals['multi_audio_s'] += max(0.0, seconds - parakeet_s)
            ref = _match(reference, str(route.get('audio_sha256') or ''))
            if ref is None:
                speech['unreferenced'] += 1
                continue
            speech['speech_s'] += float(ref.get('speech_s') or 0.0)
            speech['unsupported_s'] += float(ref.get('unsupported_s') or 0.0)
            speech['unsupported_on_parakeet_s'] += _overlap(ref, on_parakeet, seconds)
    out.update({k: round(v, 1) if isinstance(v, float) else v for k, v in totals.items()})
    if reference:
        out.update({k: round(v, 1) if isinstance(v, float) else v for k, v in speech.items()})
        if speech['unsupported_s']:
            out['unsupported_on_parakeet_share'] = round(
                speech['unsupported_on_parakeet_s'] / speech['unsupported_s'], 3
            )
    return out


def _parakeet_spans(route: dict[str, Any], seconds: float) -> list[tuple[float, float]]:
    if route.get('route') == 'parakeet':
        return [(0.0, seconds)]
    return [(float(a), float(b)) for a, b, r in route.get('pieces') or [] if r == 'parakeet']


def _overlap(ref: dict[str, Any], spans: list[tuple[float, float]], seconds: float) -> float:
    if not spans:
        return 0.0
    if spans == [(0.0, seconds)]:
        return float(ref.get('unsupported_s') or 0.0)
    total = 0.0
    for a, b in ref.get('unsupported_spans') or []:
        for x, y in spans:
            total += max(0.0, min(b, y) - max(a, x))
    return total


def _match(reference: dict[str, dict[str, float]], digest: str) -> dict[str, float] | None:
    if not digest:
        return None
    for key, value in reference.items():
        if digest.startswith(key) or key.startswith(digest):
            return value
    return None
