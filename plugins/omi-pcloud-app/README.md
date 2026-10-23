# Omi pCloud backup service

Completion of the foundation in [#20498](https://github.com/BasedHardware/omi/pull/20498),
tracking [#20213](https://github.com/BasedHardware/omi/issues/20213). This is not a
deployment or evidence that the issue is resolved for customers.

## User flow

Open the integration from your signed-in Omi app, on mobile or desktop. Omi's
authenticated app-details response supplies a short-lived setup capability.
The service consumes it once, sets a Secure/HttpOnly session cookie and removes
the capability from the URL. A bare `?uid=` never grants access.

Connect pCloud, then save your destination folder and independent summary,
transcript and audio preferences. Transcripts/audio default off, including
records without a current consent version. The same server-side connection,
preferences and recent-backup list serve both clients.

New finalized conversations enter encrypted durable jobs. `202 accepted` means
queued, not uploaded. The settings page distinguishes pending, running, failed,
completed, canceled and expired work and offers retry. Completed files are
checkpointed individually; retries overwrite the same destination rather than
creating numbered copies. Conversation identity, not title/minute, owns the
remote folder. An unfinished job follows a destination-folder change and uploads
every file there; a change during an upload fails the job with a retry prompt
rather than splitting it across folders. Completed and canceled jobs keep their
per-file receipts until the row is removed 30 days after expiry; expiry clears
only the payloads of unfinished jobs. The list shows the 30 most recent jobs plus
every older failed or pending job, so retry stays reachable. Summary/transcript files retain the readable conversation title.
`summary.md` carries the conversation's primary summary as every client selects
it (`contracts/parity/conversation-summary.md`): an app result, else the overview
or structured sections, so an empty overview never yields an empty backup.

Audio comes from Omi's canonical saved-audio records by conversation ID, never
from a shared per-user buffer. Original WAV or MP3 parts retain their real
format. If Omi has not saved audio, has removed it, or playback is not ready,
the job reports that limitation; it never calls a truncated or missing file a
successful audio backup. The maximum audio file is 512 MB; downloads are bounded
and uploads use streaming multipart. Summary/transcript successes remain saved
even if the audio portion fails.

Before each provider write, the worker rechecks Omi account/app/conversation
access and the current local consent and connection generation. Uncertain
authorization stops the operation. Discarded, deleted and locked conversations
cannot be recovered through an old backup grant.

## Deployment topology and configuration

This standalone service requires **one replica with a persistent, backed-up
volume**, mounted at `/data`. It owns one transactional SQLite database for
sessions, OAuth state, credentials, consent and jobs. Multiple workers on that
same volume use SQLite leases and per-account OS locks. **Do not deploy it onto
ephemeral Cloud Run disk, use separate per-replica volumes, or silently fall
back to files/another store.** A horizontally scaled deployment needs a separately
reviewed shared-store implementation before rollout.

The JSON/Redis implementation in the unmerged foundation is replaced, not
automatically migrated. Existing files or Redis records are not read, erased or
rewritten. If any existing installation is discovered, inventory and migrate its
state explicitly before changing its deployment. No such migration is performed
by importing or starting this code.

Configure these secrets/settings through your deployment's secret manager:

| Variable | Meaning |
| --- | --- |
| `OMI_PLUGIN_APP_ID` | Registered Omi app ID |
| `OMI_PLUGIN_SIGNING_KEY` | Per-app random signing secret, at least 32 bytes; matches backend registration |
| `PCLOUD_CLIENT_ID`, `PCLOUD_CLIENT_SECRET` | pCloud developer-app credentials |
| `PCLOUD_REDIRECT_URI` | Exact HTTPS URL ending `/auth/pcloud/callback` |
| `PCLOUD_DB_PATH` | Absolute persistent path, e.g. `/data/pcloud.sqlite3` |
| `PCLOUD_ENCRYPTION_KEYS` | JSON array of Fernet keys, newest first; no public/default key |
| `OMI_API_BASE_URL` | Trusted HTTPS Omi API base; defaults to `https://api.omi.me` |

Use a random secret generator and `Fernet.generate_key()` locally; never paste
secret values into issues, PRs or logs. Configure the pCloud application for the
minimum provider-supported permission level. The code does not request the
optional `manageshares` permission; verify the actual app grant in the developer
console before claiming app-folder-only access. pCloud OAuth tokens currently do
not expire and have no refresh-token flow; reconnect/revoke rather than inventing
one. US/EU selection comes from the allowlisted provider callback parameters.

On the Omi backend, provision the server-only `OMI_PLUGIN_TRANSPORT_JSON` mapping
from app ID to `{base_url, key}`. `base_url` is the service's exact HTTPS origin;
`key` matches the plugin signing secret. Never put the key in marketplace metadata,
query strings, or client configuration. The new registration is intentionally
unprovisioned in this source-only PR; its reviewed runtime secret bindings and
rollout are part of the remaining checklist. Unregistered apps retain their old
behavior. See [transport architecture](../../backend/docs/plugin-transport.md).

Install from this directory: `uv pip install -r requirements.txt`. Run
`python -m uvicorn main:app --host 0.0.0.0 --port 8080 --no-access-log`.
The worker starts with the application and resumes persisted work after restart;
the host must keep CPU available while idle. Do not enable request-query access
logs at the app or proxy, because setup links carry short-lived capabilities.

## Retention, disconnect and key rotation

Pending payloads (including scoped access tokens) are encrypted with vetted
Fernet, expire after seven days and are scrubbed by the worker. There are at most
100 unfinished jobs per account. Five failed attempts stop automatic retries;
the owner can retry within retention. After expiry use Omi's manual export: a
fresh delivery replaces an expired (or, after reconnecting, canceled) record,
while active, failed and completed backups still deduplicate.
Completed jobs clear their content and authorization tokens. Job metadata is
removed 30 days after expiry. Credentials and preferences are retained while
connected (ten-year maximum); sessions last one hour and OAuth state 15 minutes.
Nonce consumption and expiry are transactional, including local development.

Disconnect first stops exports and cancels/scrubs queued payloads. Only a
confirmed `result=0, auth_deleted=true` response erases the local provider token.
Failed revocation retains an inactive encrypted token solely for retry and tells
the user how to revoke access directly in pCloud. Omi does not delete remote
files or promise retention beyond pCloud's own policies.

Disconnect also rotates a durable per-account authorization epoch, even when no
connection exists. Every OAuth attempt is stamped with the epoch at Connect, and
the callback checks it under the account lock before and after the token
exchange. An attempt started before Disconnect therefore never exchanges its
code, and one already exchanging revokes the token it was just issued instead of
storing it. A newer connection is never overwritten; canceled jobs stay canceled.

To rotate encryption keys: back up the volume, configure `[new_key, old_key, ...]`,
run `configured_store().rotate_keys()` in an administrative shell on that volume,
verify reads with the new key, then remove retired keys. The transaction rewraps
both credentials and job payloads. Test the procedure against a copy first.
Signing-key rotation invalidates outstanding launch/access grants; pause admission
and settle/cancel pending jobs before coordinating that separate change.

The provider protocol remains local to this first implementation. The shared
Omi SDK deliberately owns webhook models only; Dropbox/S3/WebDAV are not claimed
as implementations of this protocol.

## Verification and release checklist

Run `bash scripts/run-plugin-pcloud-tests.sh` from the repository root. It installs
the actual pinned FastAPI/service dependencies and runs the HTTP, storage,
provider-client and backend-signing conformance tests. The deterministic manifest
runs it in both local and CI lanes. Backend transport/route tests live in
`backend/tests/unit/test_plugin_transport*.py`.

- [x] Local HTTP/browser smoke and focused backend verification recorded in PR (synthetic provider only).
- [x] Fresh grants for repeated home and setup-step clicks, signed-query preservation,
  failed-refresh refusal and account/page fences covered by client regressions.
- [x] Mobile vendor completion probes omit Omi bearer credentials and never log
  capability-bearing URLs; legacy apps with no endpoint keep optional setup.
- [ ] Verify setup/retry on the installed mobile and desktop clients with the
  operator-provisioned provider app; helper/unit/browser fixtures do not replace it.
- [ ] GitHub checks pass on the final reviewed SHA.
- [ ] Operator provisions pCloud developer app, minimal grants, callbacks and test account.
- [ ] Runtime secret bindings reviewed and provisioned on all conversation-finalization hosts.
- [ ] Persistent-volume backup, restore and encryption-key rotation exercised by operator.
- [ ] Synthetic US/EU connect, settings parity, three-part backup, retry and revocation verified live.
- [ ] Separately authorized rollout completed and customer acceptance checked before closing #20213.

No deployment, production data change, credential provisioning or issue closure
is part of this code-only work.
