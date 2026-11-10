# Token lease: pre-push deferral-marker timeout investigation

Verified 2026-11-10. Source head: `48e320b62064875cdef73099b9dfc28f2332b43b`, branch `lane/tokenlease`. This follow-up changes only this report. No code, fixture, assertion, timeout, test selection policy, skip or xfail changes. No push, amend, rebase or PR mutation.

## Finding

The reported `assert 2 == 1` is a deadline-sensitive test flake shared with pinned main, not a duplicate call introduced by `b217c5c740d3`. All five unchanged-head full-file repetitions passed (208 each; **1,040 passed**). The original failure did not recur naturally in these runs. A controlled marker-response delay reproduces the exact assertion and `uncertain=0` log on head, parent and main, with **zero enqueue calls** and exactly one marker write followed by one marker clear. Per the lead's explicit timing-flake instruction, leave the assertion and seam intact and report the evidence instead of changing the fixture or production behavior.

`backend/tests/unit/test_sync_cloud_tasks.py:5996-5997` assigns real 50ms handler and shared marker/enqueue deadlines. The enqueue mock at `:6003` raises `TimeoutError` immediately, so the intended test requires reaching enqueue before that wall expires. In `backend/routers/sync.py:2641`, the marker is a shielded future: delivering its result requires the event loop to resume the handler. If the 50ms wall expires first, `enqueue_started` has not been set at `:2655`. The outer timeout is therefore classified as `marker_timeout` (`:2681`), and `_clear_deferral_marker_after_failed_replacement` clears the marker (`:2378`) after draining the write. The two updates are `{deferred_until: <schedule>}` then `{deferred_until: null}`. This is the required cleanup when no replacement could exist. In contrast, a timeout after enqueue starts is `enqueue_uncertain`, which retains the marker.

The supplied `.agent-brief/prepush-fail-48e320.txt` records `uncertain=0`, matching the pre-enqueue branch, not the mocked enqueue timeout the test intended. A load-induced scheduling pause across the tiny wall explains the failure; the original process was not instrumented, so the precise pause cannot be measured retrospectively. Passing under some high-load samples does not establish a safe load threshold.

`b217c5c740d3` moved the same async passthrough before import and exported it on `mock_executors` (`backend/tests/unit/test_sync_cloud_tasks.py:1345-1356`). Its body calls `fn(*args, **kwargs)` once; the router's later `module.run_blocking` binding is unchanged. Imported archive helpers must await this API (`backend/utils/sync/record_token_lease.py:153`). Removing that export restores the parent's non-awaitable `MagicMock` failures; it does not fix this deadline race.

AST comparisons (excluding source locations) confirm that `run_sync_job`, `_is_uncertain_enqueue_error`, `_clear_deferral_marker_after_failed_replacement`, `_defer_sync_job_after_handler_budget_expiry` and the failing test are identical across all three revisions. The deferral function AST SHA-256 is `0f30a6feaab5036845af7a30030376f43cb6a28fa68833cd4d8a41de644f21fc`; the test AST SHA-256 is `f6c97e46ce0dd032918944f7b99c269536d162555075753763314c50800cbb60`.

## Canonical full-file comparisons

Every unit invocation used `bash test.sh` from the checkout's `backend/`, admitted through `/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 7200 --no-priority -- ...`. No bare pytest invocation. `BACKEND_UNIT_FILE_BUDGET_SECONDS=900`, `BACKEND_PYTEST_WORKERS=1`, file isolation on, parallel-session batching off; the canonical 1-second per-test CPU guard is unchanged. `BACKEND_UNIT_TEST_FILE_LIST` contains `tests/unit/test_sync_cloud_tasks.py`. Each checkout has its own `.venv`, Python 3.11.15 and exactly the same 273 installed package/version entries (verified via `uv pip freeze`, after syncing baseline environments through the heavy gate).

Test children have `GOOGLE_APPLICATION_CREDENTIALS`, all `CLOUDSDK_*`, service-account/auth-file and project bindings removed, private HOME/XDG_CONFIG_HOME/TMPDIR, one-thread native math pools, no personal `.env`, and both `OMI_ENV_STAGE` and `PROVIDER_MODE` unset to match CI. GCP tier: **none**; no production access.

| Checkout | Whole-file result | Pytest seconds | Launcher wall seconds | Reported timeout case |
|---|---|---:|---:|---|
| Parent `661fae06f9c6e12092483e0bffc88f96aecde525` | 171 passed, 37 failed | 404.55 | 419.11 | Passed |
| Pinned main `eec13aa0cd29a20ab298bdaa75f71e767620fd42` | 208 passed, 0 failed | 318.60 | 343.25 | Passed |

The 37 parent failures are the existing archive seam defect fixed by `b217c5c740d3`, not this timeout case: 33 show `TypeError: object MagicMock can't be used in 'await' expression`; four expose its cleanup/HTTP consequences (one erroneous claim release, three HTTP 500 instead of 202) and log `event=sync_ingest outcome=failed exception_type=TypeError`. The timeout case passes on the parent. The current head's full file passes every case, so this comparison supports keeping the async seam.

Five separate canonical runner invocations at unchanged head `48e320b62064` (each launches a new pytest process):

| Run | Start UTC | Passed | Pytest seconds | Launcher wall seconds | 1-minute load start → end |
|---|---|---:|---:|---:|---:|
| 1 | 2026-11-10T07:20:12.399764+00:00 | 208 | 162.54 | 184.64 | 52.56 → 49.14 |
| 2 | 2026-11-10T07:23:17.302419+00:00 | 208 | 288.56 | 298.74 | 49.14 → 87.01 |
| 3 | 2026-11-10T07:28:16.290101+00:00 | 208 | 72.88 | 77.46 | 87.01 → 57.35 |
| 4 | 2026-11-10T07:29:33.907848+00:00 | 208 | 23.03 | 24.96 | 57.35 → 42.01 |
| 5 | 2026-11-10T07:29:58.914963+00:00 | 208 | 19.49 | 20.76 | 42.01 → 32.55 |

No failures, skips, xfails or deselections in these full-file repetitions. Load samples are measured at the runner boundaries, not at the individual test, and belong to these dated runs only.

## Controlled diagnostic, separate from the five normal runs

A temporary pytest plugin wraps only the failing test's loader. It delegates to the exact original `module.run_blocking` once, then delays returning a successfully written non-null marker by `await asyncio.sleep(0.06)`. The assertion is left unchanged. This models delayed delivery of an applied marker across the test's 50ms deadline; it does not manufacture duplicate calls or alter the production handler. Teardown prints the real mock arguments, enqueue count and fallback reasons. No plugin is used for normal or final runs, and none is committed into the test suite.

Each diagnostic still uses `test.sh` with the entire file in `BACKEND_UNIT_TEST_FILE_LIST`; the explicit diagnostic-only selection is `PYTEST_ADDOPTS='-s -k test_sync_task_budget_deferral_timeout_during_enqueue_keeps_deferred_marker'`, `PYTEST_PLUGINS=marker_delay_probe`, `PYTHONPATH=<private probe directory>`. Each returns exit 1 with **1 intentionally reproduced failure, 207 deselected**, `assert 2 == 1`, and `uncertain=0`. These deliberate failures are not presented as green suite results.

| Checkout | Pytest seconds | Launcher wall seconds | Applied marker / clear calls | Enqueue calls | Fallback |
|---|---:|---:|---|---:|---|
| `48e320b62064` | 7.37 | 10.75 | 1 / 1 | 0 | `marker_timeout` |
| `661fae06f9c6` | 12.46 | 16.91 | 1 / 1 | 0 | `marker_timeout` |
| `eec13aa0cd29` | 23.07 | 30.56 | 1 / 1 | 0 | `marker_timeout` |

All three traces have this shape (the actual scheduled timestamp is irrelevant):

```json
{"writes": [{"deferred_until": "scheduled timestamp"}, {"deferred_until": null}], "enqueue_calls": 0, "fallback_reasons": ["marker_timeout"]}
```

The diagnostic's only behavioral wrapper, with `passthrough` bound to the unmodified fixture function:

```python
async def delayed_marker(executor, fn, *args, **kwargs):
    result = await passthrough(executor, fn, *args, **kwargs)
    if fn is module.update_sync_job and args[1].get('deferred_until') is not None:
        await asyncio.sleep(0.06)
    return result
```

## Final requested rerun

A fresh canonical `test.sh` invocation at unchanged source head, with the same hermetic profile above, uses this explicit file list:

```text
tests/unit/test_sync_cloud_tasks.py
tests/unit/test_legacy_dark_router.py
tests/unit/test_verify_pusher_config_references.py
```

| File | Passed | Pytest seconds |
|---|---:|---:|
| `test_sync_cloud_tasks.py` | 208 | 26.72 |
| `test_legacy_dark_router.py` | 15 | 11.69 |
| `test_verify_pusher_config_references.py` | 31 | 25.25 |

**254 passed, 0 failed**, no skips/xfails/deselections, exit 0; 73.16s launcher wall. No probe plugin or diagnostic filter. Finished 2026-11-10T07:31:44.000730+00:00.

## Evidence hashes and remaining risk

SHA-256 of complete local runner logs, including per-invocation timestamps/results, before removing temporary checkouts:

| Log label | SHA-256 |
|---|---|
| `head-original` | `cb1adde84be2b6257dd59349f31779905748ca93c5014178bead728bdcd2d1ea` |
| `parent-original` | `b9bd19cab1d4cdb581ec4956a9933a9e1d6b3b022bf5df4f9294bf2dada880a3` |
| `main-original` | `6709824aaf576261ec7916818c2e7ea7cbd065e19834ab9689d158fbaebeb4e9` |
| `head-marker-probe` | `53862ce71d70b6648693c1d215c1e18dfad62959be2003a9fd5abd5567208444` |
| `parent-marker-probe` | `666b9b186278ac50771a733248f1de1d532409a848bd8e4e1af62821f6d9d6f1` |
| `main-marker-probe` | `cb6333018fd0995599aed80d0d6ab050a373a56912679a3cc46205e78b7ab89f` |
| `final-three` | `54d39326be5ea9d1337c4ab082c4a26d2d70790f02cb6c5a505a1b4fa3047fe7` |

The 50ms scheduling race remains in the existing test and can recur on a busy runner; five green repetitions do not eliminate it. The controlled reproduction establishes the exact two-write mechanism and that main has the same vulnerability. The requested conditional disposition is evidence-only, with no assertion weakening, timeout increase or production workaround. Final source validation is on `48e320b62064`; the follow-up commit contains only this report. The prior full-shard and expanded preflight results remain documented in [the CI shard report](2026-11-10-token-lease-ci-shard7.md); they were not rerun for this documentation-only follow-up.
