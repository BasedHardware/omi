# Speaker identification offline bench

Measures the enrolled-voiceprint verification policy (`utils/stt/speaker_match.py`)
against real enrollments in `gs://speech-profiles`, using the same
`pyannote/wespeaker-voxceleb-resnet34-LM` model the diarizer's `/v2/embedding` serves.
It replaces production measurement periods: any change to the threshold, margin, clip
policy or embedding model should be run through here first (about 15 minutes on an
Apple-silicon laptop).

Cohorts

- **A** the user's current `speech_profile.wav` vs their legacy `samples/*.wav`
  (older enrollment, median 101 days apart) — cross-session, cross-era positives.
- **B** `speech_profile.wav` vs the user's `additional_profile_recordings/`.
- **C** taught persons with two or more samples, leave-one-out.
- **Impostors** 400 random other users' profiles.

Outputs, per cohort and clip length (whole / 2 s / 5 s / 10 s): false-reject and
false-accept rate at the production threshold, equal-error rate and its threshold,
and a threshold sweep. `score.py` also reports the live decision policies
(first clip, 2-of-3, centroid-of-3) and within-household confusions.

Run (bucket read access as a Google account with `storage.objects.get/list`):

```bash
uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python \
  torch torchaudio "pyannote.audio>=3.1" numpy scipy soundfile google-cloud-storage
gcloud auth login
gcloud storage ls -l -r 'gs://speech-profiles/**' > manifest.txt
.venv/bin/python select_cohorts.py      # writes selection.json + download_list.txt
.venv/bin/python download.py            # audio/ (never commit; delete afterwards)
.venv/bin/python embed_all.py           # emb.npz + index.json
.venv/bin/python score.py && .venv/bin/python sweep.py
rm -rf audio emb.npz index.json manifest.txt selection.json download_list.txt
```

User audio and derived embeddings stay on the machine running the bench and are
deleted once the aggregate numbers are recorded. The 2026-09-07 run that set the
current constants is summarised in `speaker_match.py`.
