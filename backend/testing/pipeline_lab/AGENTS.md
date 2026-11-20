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

## Judging a change with a replay

- **Default timing is bistable.** At 300 s gap / 300 s lock, the same ref and inputs can settle into one of
  two outcomes. The driver stamps each pass at arrival plus the real pass latency, so a one-second jitter
  early in the day moves lock decisions and outline prompts. On 2026-11-20, two runs of one ref differed
  by the same 15 cards every time. The 900 / 3600 runs did reproduce.
  - Run each head at least twice.
  - Compare runs of the same head first. A difference that also shows up between two runs of one head
    is noise, not your code.
  - Report a range, such as "Home 16–18", not one number.
  - The lasting fix, stamping passes on the simulated clock only, is still an open lab follow-up.
- **Score with the lab tools.** Don't write a one-off scorer.

  ```bash
  python -m testing.pipeline_lab.ideal.runs score DAY base=RUN_ID head=RUN_ID   # against the day's ideal
  python -m testing.pipeline_lab.ideal.runs diff  r1=RUN_ID r2=RUN_ID head=RUN_ID  # per-card boundaries
  ```

  `score` drops dictation (`voice_work`) by default and prints production's row first.
- **Read the diff before the totals.** Two kinds of card move a total without being about cut quality:
  - an `in_progress` card still open when the run ended;
  - a one-line card that shares a line with its neighbour.

  On 2026-11-20 one such open, one-word card at the end of a run moved Home precision from 0.83 to 0.71.
- **Know the day's pre-existing stalls.** At default timing, 2026-11-19 parks the builder from 07:12 on an
  open card over 1 MB (SCA-2791), and nothing later is built. A low card count on that day is that stall,
  not a regression.
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

- **One replay at a time.** Replays share the emulator, Redis and Typesense, so run them sequentially.
  Each replay `recursive_delete`s the lab user first.
- **The stack belongs to whoever started it.** `OMI_HARNESS_PORT_OFFSET=<n> PROVIDER_MODE=offline make dev-up`
  starts long-lived `dev_harness.supervisor` processes from the worktree's `.venv`. They have ppid 1 and
  look like orphaned test workers, but they are not.
  - Never pick processes to kill by path, name or ppid.
  - Stop only PIDs you started, after reading `ps -o pid,etime,command -p PID`.
  - Use `make dev-down` for a stack you started.
- **Bound every run.**
  - Run lab tests with a deadline, such as `perl -e 'alarm 600; exec @ARGV' ...`, through the host's heavy-command queue where it has one.
  - Run each test file in its own process, as CI does.
  - Check for leftovers when the run ends.
- **Clean up when the experiment ends.** Stop your stack, your LLM tunnel and any inspector you started,
  by PID. Remove `tailscale serve` entries you added; use serve, never funnel. Delete gateway tokens
  issued for the experiment.
- **Spending.** Every replay that reaches a real gateway runs with `--budget-usd`. The proxy cache makes a
  repeat of the same call free, so only spend that is new counts against the cap.
