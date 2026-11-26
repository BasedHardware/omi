# Recording-reliability rollouts, switched per account

Nine behaviour changes to ending a conversation, to what the phone shows while it records and to how fast
an upload's result reaches the conversation land together, each behind its own flag and each off for
every account until a rule admits it. With no rule in the flag store the backend and the app behave as
before.

## How a flag is switched

Each name is one rule in the Omi flag store (`kind: posthog` rows in `config/feature-flags.yaml`). The
backend asks `config.reliability_experiments.enabled(name, uid)` at the place the behaviour changes; the
mobile app reads the same rule from `GET /v1/flags`
(`app/lib/services/experiments/reliability_flags.dart`). One rule therefore switches both sides for an
account:

```
python scripts/omi_flags.py --project <project> set fast_end_feedback --active --allow <uid> --reason "..."
```

No rule, an inactive rule, an unreadable store or no account id all read as off. The store read is bound
at process start (`utils/reliability_flags.py`, from `configure_rollout_runtime`). A thread reads the
store's in-memory snapshot directly. An event loop never reads the store inline: it answers from what it
last learned for the account and refreshes on a worker thread, and the async paths that must not miss a
first read (`reconcile`, the two wait routes, `/v4/live-words`, the commit-wake route) await
`reliability_experiments.warm(uid)` first.

`OMI_RELIABILITY_EXPERIMENTS` (a comma list of names, or `all`) turns names on for every account. It is a
development override for a local stack, which has no flag store; no deployed environment sets it, and a
test pins that.

## The flags

| Flag | Sides | On, for an admitted account |
|---|---|---|
| `end_open_conversation` | app, backend | Every way of ending seals the phone file being written and sends the End time (`X-Omi-Ended-At`). The backend stores an owner-level cut there, the live builder starts a new v3 conversation at it at once, and speech recorded before the cut that lands later joins the ended conversation. An End with a stored cut is not held by the Finish wait of `CONVERSATIONS_V3_CAPTURE_CONTINUITY`; every other End keeps that wait. |
| `fast_end_feedback` | app, backend | The conversation shows as done as soon as its summary is stored, before the derived effects of the same pass. `GET /v1/conversations/{id}/summary/wait` holds a request until the conversation is committed with its outline (`until=outline`) or its summary is stored. |
| `end_button_by_device` | app, backend | The open v3 conversation carries the app install behind its latest speech (`v3_capture_device_id`), so the app offers End on a conversation this phone feeds. |
| `instant_live_text` | app, backend | A speech write whose grouping wake is refused because the minute's task name is taken enqueues one follow-up task in its 15 s slot. A batch-only phone session streams to the live provider while the app reports its transcript on screen; those lines are shown, never stored. |
| `vendor_recognizer_on_opened_app` | app, backend | WebSocket `/v4/live-words`: while the app is in front and capturing, a copy of the audio goes to the live provider and words come back for display only. Nothing is stored and batch stays the transcript. Supersedes the page-only provider stream of `instant_live_text` for that account. |
| `receipt_long_poll` | app, backend | `POST /v2/sync-local-files/receipts/wait` holds a request up to 20 s and answers with the upload jobs that finished; a finished job publishes a wake. |
| `early_title_icon` | app | Home lists an ended conversation with its title and emoji as soon as the server has fixed them. |
| `commit_wake` | backend | A batch worker that commits a result tells the serving backend which owner it was (`POST /v2/batch-pipeline/commit-wake`), and the backend projects that owner without waiting for the serving sweep. |
| `batch_frame_outcomes` | backend | A completed batch upload reports `frame_outcomes_v1` in its status result. |

## Not behind a flag

- The collision record and the commit meter (`2026-11-25-v3-pass-collision-record.md`): bookkeeping that
  cannot change a commit or a response.
- The four new routes exist for every account. For an account its flag is off for, the two wait routes
  answer 404 after authentication, `/v4/live-words` closes with 1008 and the commit-wake route accepts no
  owner.
- New optional response fields (`v3_capture_device_id`, `frame_outcomes_v1`) are absent unless their flag
  wrote them.

## Cost

Off, a guarded path costs one in-memory rule lookup. On the event loop of a grouping pass that is one
short task on the rollout executor per pass, replacing nothing else. Flags that add provider or database
work for an admitted account say so in their registry row: `vendor_recognizer_on_opened_app` and
`instant_live_text` add live provider seconds while the app is open, `end_open_conversation` can add a
second summary call when late speech joins an ended conversation, and `receipt_long_poll` as built reads
more documents per upload job than status polling does.

## Rollout and rollback

All nine start with no rule, so nothing changes at deploy. A rule's allow list admits single accounts; its
percentage ramps it. Rollback is deactivating the rule, which takes effect within the store's refresh
(15 s per process, plus the same again for an answer held on an event loop). The mobile app reads its
flags once per launch and identity change. `commit_wake` is decided on the batch worker, which has no
flag store configured today, so it cannot be admitted for any owner until that is added.

## Evidence

`tests/unit/test_reliability_experiments_switch.py` (per-account decision, the override, the loop-safe
read), one `tests/unit/test_reliability_experiment_<name>.py` per backend flag, and the app tests under
`app/test` named for each flag. Contract references: route policy entries for the four routes, the
Firestore query drivers for `conversation_v3_manual_cuts`, the lifecycle writer inventory entries for
`end_answer.py` and `frame_outcomes.py`.
