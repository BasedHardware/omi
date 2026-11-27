# Speaker lab

Develop and validate speaker labeling (diarization, voice matching, owner and people naming) on a laptop, against
truth, before a production ramp. Run from `backend/`. The pipeline lab's [privacy rules](../README.md#privacy-hard-rules)
apply: private corpora, cassettes and reports live under the owner-only lab root (`$OMI_PIPELINE_LAB_ROOT`), never in
Git, and reports carry numbers only.

```bash
python -m testing.pipeline_lab.speakers bench --corpus public-libri          # replay, no models, about 10 s
python -m testing.pipeline_lab.speakers bench --corpus NAME --arm base \
    --arm 'loose:CONVERSATION_SPEAKER_VOICE_MATCH_THRESHOLD=0.55' --arm 'head@/path/to/other/backend'
```

## Pieces

| Piece | What it does |
|---|---|
| `peer.py` | Loopback stand-in for the hosted diarizer (`POST /v2/diarization`, `POST /v2/embedding`). Point `HOSTED_DIARIZATION_API_URL` and `HOSTED_SPEAKER_EMBEDDING_API_URL` at it and every product speaker path runs unchanged. `replay` answers from **speaker cassettes** (keyed on route, parameters, the diarizer's pinned model revisions and the exact audio bytes; a miss is HTTP 409). `record-local` runs production's diarizer code (`diarizer/final_pass.py`, `diarizer/embedding.py`) on this CPU for a miss and files it as `source: local`, `device: cpu-fp32`. |
| `local_worker.py` | The model process behind `record-local`, in the optional local-models venv. Also runs the independent reference diarizer used for silver truth. |
| `corpus.py` | Corpus layout: one directory per conversation with `audio.wav`, `words.json`, `truth.json`, and for owner corpora `conversation.json` (production's stored labels). |
| `fixtures/public-libri/` | Committed public corpus: five LibriSpeech dev-clean (CC BY 4.0) conversations with exact truth, enrollment audio for the owner and two people, words and cassettes. `fixtures/make_public_corpus.py` rebuilds it. |
| `owner_export.py` | Read-only export of the consenting owner's own conversations into a private corpus (guard module injected by path, every write refused). `--v3-recent` picks the newest conversations-v3 rows. |
| `bench.py` | Runs **arms** over a corpus and scores them. An arm is an engine (`final_pass`: the product's whole-conversation pass) plus an environment overlay and optionally another backend tree, each in a fresh process. Stored-label arms come for free on owner corpora: `production` (what production stored) and `resolver_L` / `final_L` from each `diagnose --label L`. |
| `score.py` | Scorecards from production's own scorer (`utils/stt/diarization_eval.py`): attribution (Hungarian 1:1 per word), owner precision and recall, named accuracy, wrong-name rate, named coverage, speaker-count error. Pooled by summing counts over the conversations every arm labeled. |
| `silver.py` | Silver truth for corpora nobody has labeled: words where pyannote community-1 and NVIDIA Streaming Sortformer v2 agree; identity only from a strict voiceprint match (owner also near-field) or the owner's own manual corrections. |
| `prod_diagnose.py` | Runs today's resolver and staged-unit final pass read-only on the owner's own conversations (production flags from `deploy/runtime_env.yaml`, writes refused, models on the peer) and records why each one abstains plus the labels it would produce. |

## Metrics and what they can claim

- **Exact truth** (`public-libri`): every metric is accuracy. Clean read speech: a regression floor, not product
  quality.
- **Silver truth** (owner corpora): attribution favours community-1 (one of the two voters) and identity shares the
  gallery and embedding model with the arms. Silver ranks changes downstream of the diarizer and measures
  production's stored labels. It cannot qualify the diarizer itself, or a naming threshold between 0.45 and 0.70.
- **Gold truth** (a person listening, `truth.json` with `kind: gold`) settles both. `silver` never overwrites gold.
- Stored clocks are not on the audio clock (owner corpus, 2026-11-26: 17 % of segments within 1.5 s), so stored
  labels are placed by **text alignment** to the corpus words, and every arm is scored only on the words the
  conversation's own segments cover.
- Local cassettes are CPU FP32, not production's CUDA BF16: evidence for everything after the model, an
  approximation of the model's own output.

## Owner corpus runbook (consenting owner only, on the lab host)

```bash
export OMI_PIPELINE_LAB_ROOT=<owner-only lab root>                      # outside Git
export OMI_PIPELINE_LAB_LOCAL_SPEAKERS_PYTHON=<venv>/bin/python HF_HOME=<dir>/hf   # requirements-local-speakers.txt
export OMI_PIPELINE_LAB_LOCAL_STT_PYTHON=$OMI_PIPELINE_LAB_LOCAL_SPEAKERS_PYTHON
G="--guard <guard.py> --uid-file <0600> --secret-file <0600>"           # files, never argv values
source ~/.local/bin/gcp-agent-env.sh ro-prod                            # prod-operator to read staged artifacts
python -m testing.pipeline_lab.speakers export-owner $G --name owner-fresh --v3-recent --days 2 --limit 24
python -m testing.pipeline_lab.speakers words --corpus owner-fresh --jobs 4
python -m testing.pipeline_lab.speakers silver --corpus owner-fresh --speakers record-local
python -m testing.pipeline_lab.speakers diagnose $G --corpus owner-fresh --final-pass --label head   # a fix
python -m testing.pipeline_lab.speakers diagnose $G --corpus owner-fresh --final-pass --label main \
    --without-source-recordings                                          # main's v3 receipt behaviour
python -m testing.pipeline_lab.speakers bench --corpus owner-fresh --speakers record-local
```

Staged batch artifacts are cleaned 24 hours after projection, so `diagnose --final-pass` measures the batch path
only on conversations younger than that. Run system binaries such as `nice` around these commands with care: macOS
strips `DYLD_*` from them, and opus decoding then fails.

Delete an experiment's private corpus when the experiment ends and say so in the report.

Imports are at module scope except at two deliberate boundaries: `local_worker.py` loads the diarizer's model
modules inside the optional local-models venv, and the owner tools (`owner_export.py`, `prod_diagnose.py`, the
gallery writers in `scenario.py`) import `database`/`utils` modules that require `ENCRYPTION_SECRET` only after the
owner guard (or the lab stack) has put it in the process.
