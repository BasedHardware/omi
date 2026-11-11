# Server batch abstention evidence

Fictional fixtures only; no account reads, API requests or provider calls.
All six PNGs render actual Python server output text. They are not screenshots
of Omi clients. `flutter-render-evidence` is unavailable on this host; the
requested server API/excerpt fallback is used. `web` in the evidence manifest
identifies the local HTML text renderer, not acceptance of the web client.

The test-owned case JSON under
`backend/tests/unit/fixtures/speaker_abstention_snapshots/` contains exact before/after API `speaker_name` payloads (normal
and developer modes), server review excerpt, MCP search and bounded transcript,
plain and compact LLM input and bindings, episode input, analytics, and a raw
inventory. Before means the new kill switch is false, restoring the previous
behavior; after means true, the default. The snapshot tests compare these files
value-for-value against the real functions and assert unchanged inventory.

| Case | Snapshot | Before/after render |
| --- | --- | --- |
| One voice + two gaps | [one-voice.json](../../../backend/tests/unit/fixtures/speaker_abstention_snapshots/one-voice.json) | [001](001-web-one-voice-before-after.png) |
| Two voices + two gaps | [two-voices.json](../../../backend/tests/unit/fixtures/speaker_abstention_snapshots/two-voices.json) | [002](002-web-two-voices-before-after.png) |
| Manual wearer receipt | [wearer.json](../../../backend/tests/unit/fixtures/speaker_abstention_snapshots/wearer.json) | [003](003-web-wearer-before-after.png) |
| Mixed capture epochs | [mixed-epochs.json](../../../backend/tests/unit/fixtures/speaker_abstention_snapshots/mixed-epochs.json) | [004](004-web-mixed-epochs-before-after.png) |
| Zero-duration point keys | [point-keys.json](../../../backend/tests/unit/fixtures/speaker_abstention_snapshots/point-keys.json) | [005](005-web-point-keys-before-after.png) |
| Historical fallback keys sharing old ID -1 | [historical-fallback.json](../../../backend/tests/unit/fixtures/speaker_abstention_snapshots/historical-fallback.json) | [006](006-web-historical-fallback-before-after.png) |

Positive manual assignments on gap keys remain authoritative; stale carried
flags remain suppressed. MCP participant rosters exclude unassigned rows while
transcript rows retain their text.

UI/API/review/analytics labels use `Unknown speaker`; real voices keep dense
letters and the manual wearer remains `You`. MCP and plain LLM text instead use
`[unassigned speech]` per segment, since shared display text must not imply one
speaker. Compact LLM text retains separate citation keys and null identity
bindings, with `[unassigned speech]` on each segment. No deduplication by label.
Raw scoped IDs, separate abstention keys, participant IDs, word totals and
speech seconds are unchanged; the presentation label/participant delta is zero
in every after fixture. `You` counts as an attributed label in that metric.

Mobile numbering, macOS `SpeakerLabelFormatter`, and web `TranscriptView`/chip
formatters are **not fixed by stage 1**. Those clients' own naming rules and the
wire flag are stage 2. Existing mobile review `excerptLabel` already localizes
server `Unknown speaker`; no client strings or client code change here.
Renders pending David; no merge or deployment is authorized.

Reproduce from repository root (the key below is the repository's public test
fixture, identical to `backend/test.sh`):

```sh
PYTHONPATH=backend OPENAI_API_KEY=test-openai-key-not-real \
ENCRYPTION_SECRET=omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv \
backend/.venv/bin/python .agent-artifacts/ui-evidence/speaker-abstention/render_outputs.py

# Point PLAYWRIGHT_MODULE at an installed playwright package and optionally
# PLAYWRIGHT_BROWSERS_PATH at its installed Chromium headless shell cache.
node .agent-artifacts/ui-evidence/speaker-abstention/render.mjs
```


Pre-review fix batch: before payloads were independently verified against
`origin/main` at `9980aaf18681eee6eb8989d30c9fce3710416bad`. The generator
refuses to overwrite a before payload that differs from that verified oracle.
The six PNGs and manifest are unchanged: the six existing cases render identical
API, review, MCP and LLM output after the fix batch. Wording remains with David.
