# Owner-lab replay bench

Paired A/B replay of a serving feature (first adapter: the conversation notes
agent) against a frozen snapshot of one consenting owner's account. Arms pin
code refs and env overlays; every run executes in its own subprocess against
its own tree; a file-backed USD ledger stops spend hard, with in-flight
requests charged as reservations; an offline report mode reproduces the paired
statistics without any model call.

## Layout

- `replay_bench.py` — feature-agnostic runner: arms, interleaved repeats,
  resume, spend ledger, transport retry, zero-LLM first-request parity.
- `notes_adapter.py` — the notes agent as a bench feature: production serving
  (`utils/llm/notes_agent_serving` and everything it pulls in) over snapshot
  seams, packet-v2 pinned to the serving default (`shadow` / serve percent 0,
  asserted equal to the unset parser in `qualify`).
- `report.py` — offline report: per-arm table, paired bootstrap 95% CIs vs a
  named baseline, repeat-vs-repeat noise floor, cost split into volume vs
  cache share, acceptance gates (nonzero exit on failure).
- `invariants.py` — label-free invariants and contract-aware identity checks;
  optional labelled cases from an external JSONL.
- `store.py` — read-only in-memory view of a snapshot directory.

## Privacy (hard rules)

The snapshot, bench configs, selections, labelled cases and every run output
hold private data and live **outside Git**, under owner-only file modes (the
bench writes results and ledgers with `0600`). Never commit any of it. No
owner UID, UID digest, email, person name, conversation id, snapshot id or
path, transcript text or case content may appear in code, tests, fixtures,
commit messages or PR bodies — pins and paths arrive through args, env or
files outside the repository (`OWNER_LAB_UID`, `OWNER_LAB_SNAPSHOT`,
`OWNER_LAB_CASES`, the bench config JSON). Grep every diff for 64-hex digests,
emails, UUIDs and snapshot ids before pushing. Never print secrets, UIDs or
emails.

## Setup

1. Snapshot an owner account (the prod exporter lives outside this repo) to a
   directory such as `<scratch>/owner-lab/snapshots/<name>`; pass it with
   `OWNER_LAB_SNAPSHOT`.
2. Check out one worktree per pinned arm and note the commit each sits at.
3. Write a bench config JSON outside Git, next to where results should land:

   ```json
   {
     "repeats": 2,
     "soft_stop_usd": 2.80,
     "hard_stop_usd": 3.00,
     "arms": [
       {"name": "baseline", "adapter": "testing.owner_lab.notes_adapter:build_adapter",
        "tree": "/Volumes/Ephemeral/scratch/worktrees/omi/<baseline>", "ref": "<full sha>"},
       {"name": "on", "adapter": "testing.owner_lab.notes_adapter:build_adapter",
        "tree": "/Volumes/Ephemeral/scratch/worktrees/omi/<candidate>", "ref": "<full sha>",
        "env": {"CONVERSATION_NOTES_AGENT_LOOKUP_EFFICIENCY_ENABLED": "true"}},
       {"name": "off", "adapter": "testing.owner_lab.notes_adapter:build_adapter",
        "tree": "/Volumes/Ephemeral/scratch/worktrees/omi/<candidate>", "ref": "<full sha>",
        "env": {"CONVERSATION_NOTES_AGENT_LOOKUP_EFFICIENCY_ENABLED": "false"}}
     ]
   }
   ```

   The arm tree provides the product code under test (`utils/`, `models/`,
   `database/`). Each worker vendors only `testing/owner_lab` into a private
   directory ahead of the arm tree on `sys.path`, so product imports resolve
   from exactly one place — the arm's pinned checkout — and the harness can
   never shadow it. If the notes lane echoes the requested route instead of a
   billed model, add
   `"billed_model_markers": ["gpt-6-luna", "omi:auto:conv-structure"]`.

4. Gateway: reach the dev LLM gateway through your approved tunnel (a local
   `127.0.0.1` forward), export `OWNER_LAB_GATEWAY_URL` and point
   `OWNER_LAB_GATEWAY_TOKEN_FILE` at the service token file, mode `0600` — the
   token itself never enters the environment or any log. The transport
   reserves each request's worst case in the ledger before sending, refuses
   redirects and proxies, validates the billed model and usage, and the worker
   denies every outbound socket connect except the gateway peer.

## Running

All commands run from `backend/` with the bench module's tree checked out;
`OWNER_LAB_UID` and `OWNER_LAB_SNAPSHOT` must be set (they are never
defaulted).

```bash
.venv/bin/python -m testing.owner_lab.replay_bench --config /path/bench.json --mode select    # zero-LLM selection
.venv/bin/python -m testing.owner_lab.replay_bench --config /path/bench.json --mode qualify   # zero-LLM qualification
.venv/bin/python -m testing.owner_lab.replay_bench --config /path/bench.json --mode parity    # zero-LLM parity
OWNER_LAB_GATEWAY_URL=... OWNER_LAB_GATEWAY_TOKEN_FILE=... \
  .venv/bin/python -m testing.owner_lab.replay_bench --config /path/bench.json               # the paid bench
.venv/bin/python -m testing.owner_lab.report /path/runs.jsonl --baseline baseline \
  --max-cost-per-run 0.006 --no-worse rejections,cost --out /path/report.md                   # offline report
```

`report.py --prices input,cached,output` (USD per million tokens) reprices
every stored run from its token counts when the bench ran on a non-default
card, so the per-arm table, paired ratios, gates and the cost split all use
the same card.

- **select** picks bench cases by tier (7 short / 7 medium / 6 long, filled to
  20) among conversations the eligibility gate would run, and lists labelled
  cases separately.
- **qualify** proves, with zero model requests, that the transport is reached,
  identity and packet wiring match the pinned serving default (including a
  serve-mode probe asserting packet v2), the toolbox redacts screen rows
  outside the conversation window, and the identity contract behaves.
- **parity** fingerprints the first model request per case in every arm and
  compares hashes; arms that share a prompt route must match byte for byte.
- **run** interleaves arms per case and repeat (`arm` order rotates), resumes
  from the results JSONL by skipping already-recorded (arm, case, repeat)
  keys, retries transport stops (exit 3) up to three consecutive failures, and
  stops terminally on the spend stop (exit 4) or any worker error (exit 2).
- **report** reads the results JSONL in place — outside the repo — and exits
  nonzero when a gate fails. `--no-worse` fails only when a metric's 95% CI
  sits entirely above 1, i.e. the arm is significantly worse than baseline.

## Checks on every run

Each run's row carries `invariant_failures` from `invariants.py`: label-free
invariants (sections with nested bullets for long transcripts, no action-item
section, cost under the cap) and the inverted identity check — on the final,
post-repair submission, every human participant and any title name must carry
identity support (voice binding or affirmative user correction). The row also
reports the production repair counters (`repairs_by_kind`:
`accepted_with_problems`, `participant_dropped`,
`unsupported_speaker_identity`). Optional labelled cases
(`OWNER_LAB_CASES=/path/cases.jsonl`, outside Git) carry a
`contract_version`; a case from another contract version reports STALE, never
FAIL, and an expected name is only scored when the snapshot supports it —
without support the identity contract forbids naming that person, so the
expectation is skipped instead of failed.
