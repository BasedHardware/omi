# Offline audio capture (write-ahead log)

LIFECYCLE: permanent

Keeps audio the transcription socket could not take, and uploads it afterwards so
it still becomes a conversation. Ports the Flutter write-ahead log
(`app/lib/services/wals/*`, the protocol authority) into the desktop shape macOS uses
(`desktop/macos/Desktop/Sources/WAL/*`).

## The gap this closes

`main/ipc/omiListen.ts` had three ways of not taking a fed chunk, and each ended at a
silent `return`:

| Situation | Before | Now |
|---|---|---|
| No session owns the audio | dropped | reported as missed |
| Socket connecting, pre-connect buffer full (5 s cap) | oldest chunks dropped | evicted chunks reported as missed |
| Socket closing or closed | dropped | reported as missed |
| Session superseded or killed | pending buffer discarded | discarded chunks reported as missed |

`capture/liveRescue.ts` only ever rescued segments the backend had already returned, so
audio that was never transcribed had nowhere to go. A two minute network drop mid
conversation lost two minutes of audio permanently.

## Flow

```
capture window ──pcm──▶ main omiListen ──▶ socket (sent)
                              │
                              └──disposition──▶ WalCapture ──▶ ledger ──▶ file + audio_wal row
                                                                              │
                                            WalSyncEngine ◀───────────────────┘
                                              │ POST /v2/sync-local-files (202 + job id)
                                              │ GET  /v2/sync-local-files/{job} (reconcile)
                                              ▼
                                          conversation
```

## Modules

| File | Responsibility |
|---|---|
| `shared/wal.ts` | The model: statuses, display states, identity, upload filename. Shared with the renderer. |
| `frameLedger.ts` | Tracks what reached the socket and turns what did not into windows. |
| `walCapture.ts` | Per capture source: ledger, file writing, index rows. |
| `walStore.ts` | The `audio_wal` table and its queries. Driver agnostic, tested under `node:sqlite`. |
| `syncPolicy.ts` | Every sync decision, pure: upload outcomes, job outcomes, backoff, attempt gating. |
| `syncEngine.ts` | One upload pass, one poll per job per pass. No blocking loops. |
| `walHttp.ts` | Multipart upload, capture manifest, job polling. |
| `walRetention.ts` | What may be released when the log outgrows its budget. |
| `walService.ts` | Folder, timers, IPC, settings, lifecycle. |

## Rules that are not obvious from the code

- **`uploaded` is not deletable.** The server has the bytes and a job is running, but the
  job can still fail. The local file is kept until the job is confirmed `synced`. This is
  the single most important rule here: getting it wrong deletes the only copy of audio.
- **Nothing unconfirmed is ever deleted to reclaim space.** A full log reports being full;
  it does not make room by dropping audio that has not been backed up.
- **A response that cannot be read as success keeps the recording.** Every backend refusal
  says "local audio was not consumed". A 202 with no job id is not treated as accepted
  (nothing could resolve it), and an unrecognized job status is not read as success
  (the server may still be working).
- **A permanent refusal keeps the file.** HTTP 422 `backfill_lookback_exceeded` is terminal
  for sync, not for the audio; the row explains rather than retrying forever.
- **A requested pause does not spend a retry.** The server refused to look at the audio, so
  charging an attempt would spend the recording's budget on backend capacity.
- **`X-Device-Id-Hash` comes from the renderer.** The install id lives in renderer storage;
  minting a second one in main would look to the backend like a different machine and
  unbind every capture time. An upload is deferred rather than sent without it.
- **The upload filename is a contract.** The backend reads the capture time from the text
  after the last underscore, so the device segment is sanitized to alphanumerics: a device
  name containing an underscore would move the timestamp out of the last field and make
  every recovery untrusted backfill.

## Divergence from the Flutter source

Flutter applies its loss threshold to whatever happens to be judgeable when its 75 second
timer fires, so the same outage is stored or discarded depending on polling cadence. Here a
window is judged only once a full chunk of audio is available (or on drain), which makes the
outcome identical whether the caller polls every second or every minute. The thresholds
themselves are unchanged: a 15 second judging delay, and 10 seconds of missed audio in a
60 second window.

## Testing

Everything except the service wiring is tested without Electron: the ledger runs on a
hand-advanced clock, the store on `node:sqlite`, the policy on response fixtures taken from
the backend's own refusal shapes, and the engine on an in-memory store plus a fake HTTP
client. `omiListen.wal.test.ts` drives the real IPC handlers through a fake socket to pin all
three drop paths, which is the regression that matters most: if audio stops being reported,
this feature silently does nothing.
