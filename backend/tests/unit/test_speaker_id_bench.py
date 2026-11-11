"""Hermetic checks of the offline cohort selector using synthetic bucket listings."""

import json
from pathlib import Path
import runpy


def test_person_cohort_includes_owner_even_outside_other_cohorts(tmp_path, monkeypatch):
    # Five seconds is outside the 30..180s impostor pool and there are no
    # legacy/additional profiles. The owner must still accompany their person.
    paths = [
        'owner/speech_profile.wav',
        'owner/people_profiles/person/a.wav',
        'owner/people_profiles/person/b.wav',
        'no-owner/people_profiles/person/a.wav',
        'no-owner/people_profiles/person/b.wav',
    ]
    (tmp_path / 'manifest.txt').write_text(
        ''.join(f'160000 2026-09-07T00:00:00Z gs://speech-profiles/{path}\n' for path in paths)
    )
    monkeypatch.chdir(tmp_path)
    script = Path(__file__).resolve().parents[2] / 'scripts/speaker_id_bench/select_cohorts.py'
    runpy.run_path(str(script), run_name='__main__')
    selection = json.loads((tmp_path / 'selection.json').read_text())
    assert selection['cohortA'] == selection['cohortB'] == selection['impostors'] == {}
    assert selection['cohortC']['owner/person']['main'] == 'owner/speech_profile.wav'
    assert 'main' not in selection['cohortC']['no-owner/person']
    assert set((tmp_path / 'download_list.txt').read_text().splitlines()) == set(paths)
