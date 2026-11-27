"""The speaker bench end to end on the committed public corpus, from committed cassettes (no models, no network).

A regression floor for speaker labeling: the product's whole-conversation pass (``run_final_pass`` through the
production ``HttpDiarizer`` to the lab's speaker peer) must keep labeling five real-voice LibriSpeech
conversations (exact truth) as well as it did when the cassettes were recorded (2026-11-26: attribution 0.990,
owner precision 0.989, owner recall 1.000, wrong-name rate 0.005).
"""

import json

from testing.pipeline_lab.speakers import bench, corpus


def test_public_corpus_bench_replays_and_holds_its_floor(tmp_path, monkeypatch):
    root = tmp_path / 'lab'
    root.mkdir(mode=0o700)
    monkeypatch.setenv('OMI_PIPELINE_LAB_ROOT', str(root))
    for name in ('HOSTED_DIARIZATION_API_URL', 'HOSTED_SPEAKER_EMBEDDING_API_URL'):
        monkeypatch.delenv(name, raising=False)
    out = root / 'bench'
    out.mkdir(mode=0o700)
    report = bench.bench(corpus.load('public-libri'), [bench.Arm.parse('base')], mode='replay', out=out)
    arm = report['arms']['base']
    assert arm['errors'] == 0, arm
    assert report['peer'].get('/v2/diarization', {}).get('miss') is None, report['peer']
    pooled = arm['pooled']
    assert pooled['conversations'] == 5
    assert (
        bench.check_gates(
            report,
            [
                'base.attribution>=0.97',
                'base.owner_precision>=0.97',
                'base.owner_recall>=0.97',
                'base.wrong_name_rate<=0.02',
            ],
        )
        == []
    ), json.dumps(pooled)
    assert (out / 'summary.md').read_text().startswith('Speaker bench')
