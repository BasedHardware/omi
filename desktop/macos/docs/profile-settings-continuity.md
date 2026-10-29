# Profile edits and assistant-settings continuity

The Memories page remains an input/output surface for canonical memory. It does
not create a second profile or knowledge writer. A successful canonical edit may
return a replacement record with a different ID; the response, rather than the
submitted text, is authoritative when present. A legacy successful response
without a replacement retains the existing content-update behavior. Unsynced
local rows remain local and never send a `local_<rowid>` ID to the server.

## Ownership and persistence

Settings pulls, full pushes and queued partial pushes capture the existing
`RuntimeOwnerAuthorizationSnapshot`. The API client receives that same snapshot
so admission, credential refresh and retries cannot silently move the request
to a replacement account. Publication checks the snapshot again. A same-UID
sign-out/sign-in revokes earlier work just as a different-account switch does.
The existing voice store continues to fence its own refresh independently.
Writes serialize within their authenticated session. A pull that predates a
new local write cannot overwrite that newer intent, and a new session does not
wait for an old account's pending request.

Memory saves carry that authority through HTTP and cache reconciliation. The
existing effective-owner mutation lease covers pool acquisition and the physical
SQLite commit. Replacement upsert and retirement of the superseded local
projection occur in one transaction; a failure rolls both back. This changes no
server deletion policy and preserves unsynced local recordings and memories.

The editor retains its draft and error after failure. While a submitted save is
pending, repeat Save, text changes and Cancel are disabled. A late result must
not dismiss another memory's editor or republish into another owner. Owner reset
also resets transient save/error state.

## Electron client

The renderer advances one `authSessionScope` generation on Firebase auth-state
changes. API calls, token refresh/retry, memory paging and cache publication keep
the originating generation; a revoked request cannot retry as the replacement
account or force that account to sign out. A failed optimistic edit restores
only its own untouched row, preserving other edits that completed meanwhile.
The inline editor retains its failed draft and blocks dismissal while saving.

Main-process assistant settings bind only through the existing signature-verified
PiMono session relay. The exact admitted session object fences delayed verifier
results, including A→B→A. Clear the previous owner before awaiting verification.
Raw auth-persistence payloads and audio-start tokens are not owner authority.
Owner-tagged IPC writes must match the current owner; existing untagged local
preference calls retain their local-device semantics. This does not introduce
account-wide Electron settings sync or key portability.

## Verification checklist

- From `desktop/macos`, run:

  ```bash
  ./scripts/dev-feedback.py --once swift 'SettingsSyncOwnerBoundaryTests|APIClientSettingsOwnerRequestTests|APIClientAssistantSettingsTests|MemoryDetailPanelTests|LocalMutationAuthorizationTests'
  ```

- Exercise current settings pull/push, a queued write after sign-out, different
  owners and same-owner reauthentication. Revoked requests must never reach the
  intercepted HTTP transport or change the new session's local settings.
- Exercise canonical replacement and immediate cache readback. Inject SQLite
  retirement failure and verify that the original remains and no replacement
  survives a rolled-back transaction. Failed HTTP edits retain the draft.
- From `desktop/windows`, use pinned Node 22 and pnpm 10, then run
  `pnpm typecheck`, `pnpm lint`, and `pnpm test --maxWorkers=2`. Build with
  `VITE_OMI_API_BASE=http://127.0.0.1:49601 pnpm build`, then run
  `node --test e2e/memory-edit-continuity.spec.mjs`. That built-app check uses
  synthetic auth and a real loopback HTTP fixture serving unchanged built assets
  under the same origin, with CSP and web security enabled. It verifies failed-save/retry/canonical
  replacement and offline restart, not a live Firebase provider login.
- Build an isolated named app against the offline local harness and synthetic
  users. Verify the actual memory Save/error/retry controls and settings sync;
  record the app's source identity and screenshots. Create a fresh memory through
  New Memory for write checks; the canned read-scenario rows are not a substitute
  for a current canonical apply-control generation. The local harness must use
  `MEMORY_ENABLED=on`; the retired `MEMORY_MODE` no longer permits writes. Do not seed production auth
  into the emulator profile or mutate production/customer memories.
- Review the final diff, run component checks and normal preflight/pre-push, and
  inspect required CI for the updated commit. Keep the PR draft until those
  checks and the separately requested account-isolation review are satisfied.

These workflows do not implement atomic task recurrence, reminder delivery,
automatic task execution, additional account-sync fields or secret-key
portability. Those remain separate stages of issue #20956.
