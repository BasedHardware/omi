# Pipeline lab: agent guide

Rules for agents that change the lab or use it to judge a product change. [README.md](README.md) is the
reference: layout, store, commands and runbook. This file covers what earlier agents got wrong, so the
next one does not repeat it. The backend rules in [`backend/AGENTS.md`](../../AGENTS.md) still apply.

## Privacy

The README's hard rules come first. In practice:

- **Reports hold numbers only.** PRs, issues, chat and memory may carry times, durations, word counts,
  card counts, scores and flags such as `visible` or `home_hidden_reason`. Transcript text, card titles,
  summaries, names, uids and conversation ids never go in them. `ideal.runs` prints only safe fields;
  when you write your own query, print the same fields and nothing more.
- **Private files stay under the 0700 lab root,** never in the repo, a PR or an artifact. That covers
  overlays with the owner's uid, snapshots, audio, ideals, run outputs and the gateway token.
- **Secrets are read by path at the moment of use.** The owner uid, encryption secrets and the gateway
  token come from 0600 files. Never print them, and never put them in argv, a log or a commit.
- **Production stays read-only.** Exports run under a read-only GCP agent tier, and only for the owner who
  consented. A replay writes only to local emulators under the synthetic uid `local-dev-user`.

## Before you open a backend pull request

- Run `affected`, run the scenarios it names (`scenario run NAME ... --keep DIR`) and attach the verdict
  summary (`scenario summary DIR`) to the pull request.
- A production escape in the capture -> Finish -> Home path gets a scenario before its fix merges.
- A change that moves a scenario's operation counts (`ops` in its `result.json`, the `reads`/`writes`/
  `no-op writes` columns of `scenario summary`) past its `budget` fails that scenario. Raise a budget only
  with the reason in the pull request; a new no-op write site is a finding to report, not a cap to raise.

## Judging a change with a replay

- **Replays are repeatable by default.** The v3 replay runs on the simulated clock
  (`model_config.v3.clock: "sim"`), and so does the classic chain (same switch; `"tick"` restores the
  ticking clock for both): every pass is stamped at its scheduled instant, not instant plus real latency, so
  lock and gap decisions no longer depend on host speed. With a warm proxy cache, the same ref and inputs
  give identical semantic artifacts; check with `python -m testing.pipeline_lab.determinism RUN_A RUN_B` (it
  prints paths only). Still not deterministic: real LLM answers on a cache miss (first run, or
  `--llm-mode refresh`), product I/O budgets measured in real time inside one event
  (`utils/conversations/v3/context.py:50`, a 1 s background-sources read), and any run whose
  `v3_driver.json` (or `chain_entry.json`) shows `late_monotonic_reads > 0`. When any of these applies, run
  each head twice, compare runs of the same head first and report a range.
- **Score with the lab tools.** Don't write a one-off scorer.

  ```bash
  python -m testing.pipeline_lab.ideal.runs score DAY base=RUN_ID head=RUN_ID   # against the day's ideal
  python -m testing.pipeline_lab.ideal.runs diff  r1=RUN_ID r2=RUN_ID head=RUN_ID  # per-card boundaries
  ```

  `score` drops dictation (`voice_work`) by default and prints production's row first.
- **Read the diff before the totals.** A card still `in_progress` at the run's end, or a one-line card sharing
  a line with its neighbour, moves a total without being about cut quality (0.83 -> 0.71 on 2026-11-20).
- **Know the day's stalls.** 2026-11-19 parks the builder from 07:12 on an open card over 1 MB (SCA-2791);
  a low card count that day is that stall, not a regression.
- **The ideal is the reference.** Each day's ideal Home lives under the lab root at `ideal/<day>/`. Note
  whether it was reviewed by the owner or judged by a model, and say which in the report.

## Product tests the lab leans on

- **A stubbed loader must match production.** v3 multi-pass unit harnesses, such as
  `backend/tests/unit/test_conversations_v3_live_passes.py`, stub `store.load`. Production reads every row a
  recording's claims name, deleted rows included. A stub that drops tombstones lets deletion and
  ownership tests pass without testing anything.
- **Mutation pass for custody and ownership tests.** Revert each ownership decision one at a time and
  confirm some test fails before you push. On #25829, 14 mutations found 2 that no test caught.

## Running things on the lab host

- **One day replay at a time** on a shared stack (each `recursive_delete`s the lab user first). Scenario runs
  are isolated per run and may share one stack (`--jobs`).
- **The stack belongs to whoever started it.** `make dev-up` supervisors have ppid 1 but are not orphans.
  Never kill by path, name or ppid; stop only PIDs you started (read `ps -o pid,etime,command -p PID`).
- **Bound every run:** a deadline (`perl -e 'alarm 600; exec @ARGV' ...`) through the heavy-command queue,
  one process per test file, and a check for leftovers at the end.
- **Clean up** your stack, LLM tunnel, inspector and `tailscale serve` entries (serve, never funnel) by PID,
  and delete gateway tokens issued for the experiment.
- **Spending.** Every replay that reaches a real gateway runs with `--budget-usd`. The proxy cache makes a
  repeat of the same call free, so only spend that is new counts against the cap.
