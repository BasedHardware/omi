"""``scenario compare`` metric ``speakers``: each speaker scenario's scorecard and final-pass outcome per arm.

Reads ``<run dir>/<scenario>/result.json``: the scorecard ``scenario/ops.py`` put on the conversation holding the
truth's recording (``speakers/scenario.SpeakerScoring``; the one with the most scored words when several hold it)
and ``speakers.final_pass``. Numbers and short labels only; a rate with nothing to measure is left out (its delta
reads ``null``).
"""

from __future__ import annotations

from pathlib import Path

from testing.pipeline_lab.scenario.metrics import register_metric, scenario_results

RATES = ('attribution', 'owner_precision', 'owner_recall', 'named_accuracy', 'named_coverage', 'wrong_name_rate')
COUNTS = ('voices', 'owner_words', 'words')


@register_metric('speakers', description='speaker scorecard and final-pass outcome per speaker scenario')
def speaker_metrics(run_dir: Path) -> dict[str, int | float | str]:
    out: dict[str, int | float | str] = {}
    for name, result in scenario_results(run_dir):
        block = result.get('speakers')
        if not isinstance(block, dict):
            continue
        cards = [row['speakers'] for row in result.get('conversations') or [] if isinstance(row.get('speakers'), dict)]
        if cards:
            card = max(cards, key=lambda c: c.get('words') or 0)
            for key in (*RATES, *COUNTS):
                value = card.get(key)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    out[f'{name}.{key}'] = value
        out[f'{name}.final_pass'] = (','.join(block.get('final_pass') or []) or 'not_run')[:80]
    return out
