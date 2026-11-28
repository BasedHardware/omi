# Prod-parity local stack

Test a change end to end before it merges: your checkout's backend, your build
of the app, a real phone and a real pendant, with the backend configured the
way production is.

Plain `make dev-up` is built for fast local work. It runs one backend process
with a short hand-written environment, so every setting production declares and
the harness does not falls back to its code default. That is a different
application from production's: live speech-to-text where production records for
the batch pipeline, inline uploads where production queues them, no scheduled
sweeps. A recording that works there says little about what it will do after a
deploy.

`OMI_HARNESS_PROFILE=prod-parity make dev-up` starts the same harness with
production's shape instead. Every process still runs on your machine against
emulators. Nothing connects to production, and no production credential is used.

## What runs

| Production | Here |
|---|---|
| Load balancer | `backend` process: an edge router on the public port (`dev_harness/edge_router.py`) |
| Cloud Run `backend`, `backend-sync`, `backend-sync-backfill`, `backend-integration`; GKE `backend-listen` | One process each (`svc-backend`, `svc-sync`, `svc-sync-backfill`, `svc-integration`, `svc-listen`) running this checkout's `backend/main.py` with that service's production settings |
| GKE `pusher` | `pusher` process, production settings |
| Batch speech workers (GPU) | `batch-worker` processes: production's `diarizer.batch_pipeline_runtime` with the same pinned models on CPU (`dev_harness/batch_worker.py`) |
| Record seal worker | `record-seal-worker`, when a production snapshot describes it |
| Cloud Tasks | `task-queue`: a persistent local queue with production's queue names, attempts, backoff and rate (`dev_harness/local_task_queue.py`) |
| Cloud Scheduler | `scheduler`: production's recording-path jobs on their cron schedule (`dev_harness/local_scheduler.py`) |
| LLM gateway | `llm-gateway`, as in the default stack |
| Firestore, Auth, Redis, Typesense, object storage | The default stack's emulators, local Redis and Typesense, and a storage folder |

Each service's environment is composed by `dev_harness/prod_parity.py`. Settings
that say *where something lives or who it is* (projects, addresses, buckets,
queues, accounts, telemetry targets) are replaced by local ones or dropped.
Every other setting takes production's value, and a harness test fails on any
that does not. Addresses the stack has no stand-in for are pointed at a closed
port, so a local process can never dial a production or staging host.

Production's settings come from one of two sources:

- **This checkout's deploy files** (default): `backend/deploy/runtime_env.yaml`,
  `backend/deploy/ops/prod.yaml`, the listen, pusher and batch-worker chart
  values, and the staging composition for deploy-time inputs. Needs no access
  to anything. It describes your checkout, which can be behind what runs, and
  it has neither the load balancer's path rules nor the live rollout document:
  the router then sends the upload routes, status polls included, to the sync
  service, where production sends the polls to `backend`.
- **A production snapshot** (optional, for people with read access to the
  production project): the running services' own settings, the load balancer's
  path rules, the live queues, scheduler jobs and rollout percentages. See
  [Production snapshot](#production-snapshot).

## Before you start

- The default stack works: `make setup`, then `make dev-up` and `make dev-down`
  (see [`local-emulator-manual-qa.md`](../../backend/docs/runbooks/local-emulator-manual-qa.md)).
- Provider keys in `backend/.env.local-dev`. The profile requires
  `OPENAI_API_KEY`, `MODULATE_API_KEY` and `SONIOX_API_KEY`, because
  production's serving chain does not start without them. The other keys in
  the template are optional. These are your own vendor accounts and they are
  billed for what you record.
- The batch worker's model runtime, in its own environment (it does not fit
  the backend's):

  ```bash
  uv venv backend/.venv-eval --python 3.11
  uv pip install --python backend/.venv-eval/bin/python -r backend/scripts/diarization_eval/requirements-eval.txt
  ```

- `HUGGINGFACE_TOKEN` in `backend/.env.local-dev`, from an account that has
  accepted the terms of `pyannote/speaker-diarization-community-1`. The models
  are downloaded on the worker's first start.
- On macOS, `brew install opus ffmpeg`. The pendant sends Opus.

Without the model runtime or the token the stack still starts, and says so, but
no batch worker runs: phone and pendant recordings stay "Transcribing", because
production transcribes them in the batch pipeline, not in a live stream.

### Speakers

The batch worker separates voices inside one recorded unit, which on a phone is
a file of a few seconds. Joining a voice across the units of a conversation,
and matching it to a person the account has named, is a later step in the
backend. It compares voice vectors that production gets from the diarizer
service's `/v2/embedding` route.

With the model runtime and the token in place the stack runs that route as the
`voice-embedding` process: production's handler and pinned model
(`backend/diarizer/embedding.py`), on CPU, on loopback only. The model is
downloaded on its first start; until it is loaded, callers get the same
"unavailable" answer as without it. Without the runtime the route is
unreachable and every unit keeps its own speaker numbers, so a conversation
shows a new speaker every few seconds. `make dev-parity` says which of the two
you have.

The whole-conversation second pass (`HOSTED_DIARIZATION_API_URL`) is not served
locally.

## Start the stack

```bash
export OMI_HARNESS_PROFILE=prod-parity
export OMI_DEV_HOST="$(ipconfig getifaddr en0)"   # this Mac's LAN or Tailscale address; needed for a real phone
make dev-up
make dev-status
make dev-parity
```

`make dev-parity` prints what still differs from production and exits 0 only
when nothing but the standing substitutions does. Keep the two variables
exported for every `make dev-*` command in that shell.

The services do not reload. After a code or settings change run
`make dev-restart`: it restarts the application services only, in about ten
seconds, while the emulators and Redis keep running, so local data stays.
`make dev-down` stops everything; the emulator's data is exported on the way
down and imported by the next `make dev-up` (see
[Troubleshooting](#troubleshooting) for when that export does not happen).
`make dev-reset` clears the local data.

Logs are one file per process under `.local/dev-harness/<instance>/logs/`:

| File | Read it for |
|---|---|
| `backend.log` | Every request the phone made: `harness_edge ... path= upstream= status= ms= client=` |
| `svc-*.log`, `pusher.log` | What each service did with it |
| `task-queue.log` | Every task: `harness_task_queue event=created|delivered|retry_in_Ns|attempts_exhausted` |
| `scheduler.log` | Each scheduled sweep and its status |
| `batch-worker*.log` | Transcription of recorded audio |

## Phone app and pendant

The app side is the existing local-development build; nothing here changes it.
In the same shell (so the app is compiled against the address the stack listens
on), with the iPhone connected and unlocked:

```bash
cd app
OMI_MOBILE_BUILD_MODE=profile bash setup.sh ios
```

Profile mode gives a build that opens from the Home Screen without a debugger
attached, which a pendant session needs: the phone will be locked and in a
pocket. Details and Android are in [`app/README.md`](../../app/README.md) and
[`AppSetup.mdx`](../../docs/doc/developer/AppSetup.mdx).

On the phone, sign in with the local-development button. Pair the pendant in
the app the usual way; the Bluetooth path is the app's own and does not involve
the stack. Then record. What you should see is production's behaviour:

1. The phone opens `/v4/listen`. The edge router sends it to `svc-listen`,
   which admits the session as batch-only when production's rollout says so.
   No live transcript appears.
2. `pusher` archives the audio. Recordings the phone stored offline arrive as
   uploads on `/v2/sync-local-files` and go to `svc-sync`.
3. The batch worker transcribes the audio; the conversation leaves
   "Transcribing".
4. Title and summary arrive through the task queue a little later.

Without a pendant, the phone's own microphone exercises the same server path.
[`omi/firmware/scripts/devkit/OmiSimulator`](../../omi/firmware/scripts/devkit/OmiSimulator/README.md)
is a macOS Bluetooth stand-in for a pendant.

## Production snapshot

A snapshot replaces the checkout's deploy files as the source of settings. Take
one with your own read-only `gcloud` access:

```bash
make dev-parity ARGS="snapshot --out ~/omi-prod-snapshots/$(date -u +%Y%m%dT%H%M%SZ)"
export OMI_HARNESS_PROD_SNAPSHOT=~/omi-prod-snapshots/<the directory it printed>
make dev-restart
```

Add `--configuration NAME` to read with a gcloud configuration other than the
active one. The command needs view access to Cloud Run, the load balancer's URL
map, the backend namespace of the GKE cluster, Cloud Tasks, Cloud Scheduler and
the one rollout document. Whatever it cannot read is listed in the snapshot and
in `make dev-parity`, and the rest is still used.

What a snapshot holds, and what it never does:

- It is written outside the repository, owner-only. The command refuses a
  directory inside a git checkout. Do not commit one or attach one to a PR.
- Secret values are never read. A setting bound from a secret is recorded by
  name only; the stack supplies its own local value or your own key.
- Allow-lists of user ids are recorded as a placeholder, so no account
  identifier reaches the file. The local account is therefore treated as an
  ordinary account, not an allow-listed one.
- Nothing is written to production.

Production deploys several times a day. To see what moved since your snapshot,
take a new one and compare (names only, never values; exit status 1 when
something changed):

```bash
make dev-parity ARGS="drift ~/omi-prod-snapshots/OLD ~/omi-prod-snapshots/NEW"
```

With a snapshot, `make dev-parity` also says which commit each production
service runs and how many recording-path files your checkout differs in. The
stack always runs your checkout's code. To test a change against what is
deployed today, base your branch on the commit the report names.

## Settings

| Variable | Effect |
|---|---|
| `OMI_HARNESS_PROFILE=prod-parity` | Selects this profile. Unset, `make dev-up` is the default stack, unchanged. |
| `OMI_DEV_HOST` | Address the public port binds and the app is built against (existing harness setting). |
| `OMI_HARNESS_PROD_SNAPSHOT` | Directory of the production snapshot to compose from. |
| `OMI_HARNESS_BATCH_WORKERS` | Batch worker processes (default 3). One CPU process falls behind a phone that uploads continuously. |
| `OMI_HARNESS_TASK_QUEUE_CONCURRENCY` | Cap on deliveries in flight per queue (default 4; production's own limit when lower). |
| `OMI_HARNESS_SCHEDULER_JOBS=all` | Run every backend-service scheduler job, not only the recording-path ones. That includes agent sweeps that call LLMs. |
| `OMI_HARNESS_LOG_TIMESTAMPS=1` | Prefix the service, gateway, edge router, task queue and scheduler log lines with UTC time to the millisecond, to time a step. The backend's own log format has no time. |
| `OMI_HARNESS_PUSHER_PORT` | Pusher port (default 8090). Service ports are the backend port plus 10 to 14, batch workers from plus 15. The record seal worker's metrics port is 8080, fixed in backend code. |

The rollout document (`rollout_cohorts/_ramp` in the Firestore emulator) is
written on first start from the snapshot, or from what the tracked files say
production runs. To study another rollout state, edit it in the emulator; the
harness leaves a document it did not write alone.

## What cannot match production

`make dev-parity` prints this list with everything else that differs.

- Speech and speaker models run on your CPU in FP32. Production uses GPUs.
  Text can differ slightly; speed and latency differ a lot.
- Firestore, Auth and Redis are emulators. Contention, indexes and latency differ.
- Cloud Tasks and Cloud Scheduler are the local stand-ins above. Not
  reproduced: IAM, Google-signed tokens, throttling after bursts of errors,
  duplicate delivery.
- Hosted GPU services (diarization, VAD, language gate) are unreachable by
  design; callers take the fallback they take in production when those are
  down. Speaker embedding is the exception: see "Speakers" below.
- Vendor accounts are your own keys, with their own limits.
- Telemetry, payments and messaging channels are off.
- The local account's plan and language are whatever the emulator holds. On
  the free plan, recordings are held once the allowance is used, as in production.
- The app is a development build: it talks plain HTTP to a LAN address, reads
  feature-flag defaults, and signs in against the Auth emulator.

## Related tools

- [Pipeline lab](../../backend/testing/pipeline_lab/README.md) replays one
  recorded day through pinned code and compares the result with what production
  produced. Use it to judge output quality on real data. Use this stack to
  exercise the live path with a real client.
- The hermetic stacks under `backend/testing/` (`listen_pusher_stack`,
  `sync_cloud_tasks_stack`) are one-shot CI gauntlets with fake models. They
  prove invariants; they are not something a phone can connect to.
- [Physical devices](PHYSICAL_DEVICES.md) covers the leased qualification lane
  and the native probes. This stack makes no qualification claim.

## Troubleshooting

- **The phone stopped reaching the backend overnight.** The Mac's address
  changed. Compare `ipconfig getifaddr en0` with `OMI_DEV_HOST`; restart the
  stack and rebuild the app on the new address. Recordings made meanwhile stay
  on the phone and upload afterwards.
- **Recordings stay "Transcribing".** `make dev-status` shows whether a
  `batch-worker` runs; `make dev-up` prints why when it does not.
- **Every Opus session ends at "Codec decoder initialization failed".**
  libopus is not installed where the services look (`brew install opus`).
- **`make dev-up` refuses to start.** It lists what is missing. Docker must be
  running for Typesense.
- **`ERROR ... Stripe price validation failed` at start-up.** Expected: the
  services run production's start-up checks and payments are off here.
- **`warning: record-seal-worker: exited after start`.** The seal worker
  serves its metrics on port 8080, fixed in backend code. If something else
  holds that port it exits and the stack runs without it; in production its
  repair switch is off, so it idles there too.
- **Emulator data is gone after `make dev-down`.** The emulator exports its
  data when it stops, and it finds itself through a file named after the
  Firebase project in the system temp folder. If that file is missing when the
  stack stops (the temp folder was cleaned under a long-running stack, or
  another harness instance on the same project stopped first), the log says
  `Did not find any running emulators` and nothing is exported. Prefer
  `make dev-restart`, which never stops the emulator.
- **Typesense is not healthy after quick `make dev-down` / `make dev-up`
  cycles.** Seen when the new container found its data folder still in use by
  the previous one. `make dev-restart` avoids the cycle.
- **A second harness instance next to a running one.** Give it its own
  instance name, ports and temp folder, and export them for every `make dev-*`
  command of that instance:
  `OMI_LOCAL_INSTANCE=second OMI_HARNESS_PORT_OFFSET=2000 TMPDIR=/some/private/dir/`.
  The temp folder keeps the two emulators' project files apart (previous
  point). Without the instance name, starting the second one replaces the
  first one's Typesense container.

## Tests

`bash scripts/dev-harness/run-tests.sh` covers the composition
(`tests/test_prod_parity.py`: no behaviour setting differs, no address leaves
the machine, no process gets cloud credentials), the snapshot and routing
(`tests/test_prod_snapshot.py`) and the task queue (`tests/test_local_task_queue.py`).
They start nothing and contact nothing.
