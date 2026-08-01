# Security audit — 2026-08-01

Multi-agent audit of the whole repo at `upstream/main` (`6c4d752b2f`), plus the fixes
applied on this branch. Nothing here originates from a feature PR; all of it is on `main`
today.

**Read the "Not fixed" section before deploying anything.** Several of the worst findings
need an infra or product decision, not a code change, and two of the applied fixes require
env vars to be set *before* they roll out or they will take features down.

---

## 1. Fixed on this branch

### Backend — authorization

| | Finding | File |
|---|---|---|
| CRITICAL | `update_app` / `update_persona` authorized on the path id but wrote the id from the request body. Any app owner could rewrite any other developer's app document — reassign ownership, repoint the webhook that receives installing users' transcripts, repoint the Stripe payment link. | `backend/routers/apps.py` |
| HIGH | Multipart `filename` used unsanitized in `_temp/...` paths at five upload endpoints → arbitrary file write, and the container root filesystem is writable → RCE on next process start. | `backend/routers/speech_profile.py`, `backend/routers/apps.py` |
| HIGH | `POST /v1/stripe/refresh/{account_id}` bound `uid` and never used it. Any authenticated user could mint an onboarding link into another developer's Connect account (which permits editing payout bank details). | `backend/routers/payment.py` |
| MEDIUM | Sentry webhook signature check was fail-open when the secret was unset; `/v1/webhooks/sentry/poll` had no auth at all. | `backend/routers/desktop_core.py` |
| MEDIUM | Conversation-summary ratings keyed without uid → cross-user read and overwrite. | `backend/database/users.py` |

### Backend — data exposure

| | Finding | File |
|---|---|---|
| CRITICAL | Chat image thumbnails were `make_public()`'d and served at `https://storage.googleapis.com/<bucket>/<uid>/<snake_cased_original_filename>`. Deterministic path + a uid (which appears in PostHog `distinct_id` and Sentry) = anyone can pull a user's chat images. Now stores the blob path and signs at read time; existing absolute-URL records pass through. | `backend/utils/other/storage.py`, `backend/database/chat.py`, `backend/routers/chat.py` |
| CRITICAL | Account deletion never purged speech profiles (raw voiceprints), private-cloud-sync audio, chat files, or the `ns_x` vector namespace. Firestore was wiped and the API reported success while the audio of every conversation the user ever recorded stayed in GCS — with the index to find it gone. GDPR Art. 17 failure. | `backend/services/users/account_deletion.py`, `backend/database/vector_db.py` |
| HIGH | `get_chat_tracer_callbacks` checked only for an API key, never `LANGCHAIN_TRACING_V2`. Prod sets the flag to `false` *and* injects the key, so every agentic chat — prompts, retrieved memories, retrieved transcripts — was being exported to LangSmith. | `backend/utils/observability/langsmith.py` |
| MEDIUM | Eight sites logged raw user search queries to Cloud Logging at INFO, correlated with uid. `sanitize_pii` already existed and was used on the MCP path only. | `backend/utils/retrieval/**` |

### Agent VM — prompt injection to root shell

The per-user VM ran Claude with `permission_mode="bypassPermissions"` and
`Bash`/`Write`/`Edit`/`WebFetch`, as root, over a database of the user's screen OCR.
Indirect prompt injection was therefore a code-execution primitive: any text that landed
in a screenshot, a window title, a fetched page, or an email body could issue shell
commands. From that shell: the org-wide `ANTHROPIC_API_KEY`, the user's live Firebase
token, the whole database, and the GCE metadata service.

Fixed: tool surface reduced to the MCP tools, permission bypass removed, container runs as
uid 10001 with `--cap-drop=ALL --security-opt no-new-privileges`, data volume moved off
`/root`. Also fixed alongside it: VM names truncated a 28-char case-sensitive uid to 12
lowercase chars (collision → user B is handed user A's external IP), `_agent_disabled()`
failed open, no shielded-VM config, no SSH lockdown, `agent-proxy` ran as root.

### Desktop (macOS) — local code execution

This app holds Full Disk Access, Screen Recording, Accessibility, and Apple Events.

| | Finding |
|---|---|
| CRITICAL | `TaskAgentManager` built a `zsh -c` string containing `$(cat promptFile)`, which tmux then re-parsed with a *second* shell — so LLM-extracted task text was executed. Rewritten to pass argv with no shell. |
| CRITICAL | Server-supplied task ids were interpolated into `osascript` and four `zsh -c` strings, and were replayed from SQLite on every launch with no revalidation — one poisoned row = persistent execution. Sanitized at mint and at restore. |
| HIGH | `RewindStorage.loadScreenshot` had no path confinement and `imagePath` is a DB column, so model-authored SQL could point it at `~/.ssh/id_ed25519` and read the file back through `get_screenshot`. |
| HIGH | `InsightAssistant` analyses screenshots — attacker-renderable content — and forwarded `execute_sql` write-enabled (`read_only` defaults to false). |
| HIGH | Insight and Goals logged full prompts (screen OCR, transcripts, memories) to a plaintext log in `/tmp`. |
| HIGH | Test `DistributedNotificationCenter` observers shipped in production. That bus has no sender identity — any local process could forge an Omi notification (clean phishing primitive) or force a run over the user's screen history. |
| MEDIUM | OAuth authorization code written to the macOS unified log (captured by sysdiagnose, which users attach to support tickets); the deeplink `state` could name an arbitrary bundle id to launch. |
| MEDIUM | Notion OAuth listener bound all interfaces instead of loopback and resolved before validating `state`. |
| HIGH | `omi.db` — all screen OCR and transcripts, unencrypted — was created 0644 in a 0755 directory. Now 0600/0700. |

### Mobile and hygiene

| | Finding |
|---|---|
| HIGH | `_isRequiredAuthCheck` attached the Firebase ID token to any URL *containing* `api.omi.me`. A marketplace publisher setting `setupCompletedUrl` to `https://api.omi.me.attacker.tld/x` harvested it — full account takeover, triggerable by opening an app detail page. |
| HIGH | Android permitted backup (the auth token is in plaintext SharedPreferences, so it was going to Google cloud backup and device-to-device transfer) and permitted cleartext app-wide. |
| MEDIUM | Markdown viewer appended the user's uid to any link in publisher-supplied markdown and launched it with no scheme check; publisher webview had unrestricted JS and no navigation allowlist. |
| MEDIUM | A bearer-equivalent share token was sent to PostHog as an event property. |
| CRITICAL | `plugins/oauth/conversation_created.py` printed a live, non-expiring Notion access token to stdout on every integration setup. **Rotate every Notion token that has passed through this.** |
| HIGH | `plugins/omi-hive-app` printed the raw Hive API key on every REST call. **Rotate.** |
| MEDIUM | `.gitignore` had no generic `*.pem` / `*.p8` / `*.p12` / `credentials.json` rules. |

---

## 2. NOT fixed — needs a decision

### 2.1 CRITICAL — the wearable is an unauthenticated open microphone

`omi/firmware/omi/src/lib/core/transport.c:144`

The BLE audio characteristic is `BT_GATT_PERM_READ` with no encryption requirement.
`CONFIG_BT_SMP=y` is set but `bt_conn_set_security()` is never called anywhere in the
firmware, `CONFIG_BT_SETTINGS` is absent (so bonds would not persist even if made), and
the audio service UUID is in the advertising payload.

**Anyone within BLE range can connect with no pairing, write `0x0001` to the audio CCCD,
and receive the live microphone stream.** No prompt, no indication on the device. There is
no `CONFIG_BT_PRIVACY`, so the identity address is static and the wearer is also trackable
across locations. The storage service (`storage.c:79`) is equally open — an attacker can
list, download, and wipe previously recorded audio off the SD card.

`omiGlass` is worse: unauthenticated BLE writes set the device's WiFi credentials and the
OTA firmware URL (`omiGlass/firmware/src/ota.cpp:99`), i.e. persistent takeover of a
head-worn camera and microphone.

Not fixed here because requiring encryption breaks every currently-paired device and needs
a firmware rollout plan. This is the single most serious finding in the audit.

Also unresolved: `CONFIG_MCUMGR_TRANSPORT_BT_AUTHEN` appears nowhere in the tree. If it
defaults off in your pinned NCS version, unauthenticated firmware flashing over BLE is a
second critical. **Check this.**

### 2.2 CRITICAL — firmware signing key is committed

`omi/firmware/bootloader/mcuboot/root-rsa-2048.pem` is the private key CI actually signs
releases with (`omi/firmware/scripts/ci/README.md` says so outright). The public half is
burned into every shipped bootloader, so anyone with the repo can produce a validly signed
DFU image.

Rotation requires a staged rollout: a bootloader update signed with the *old* key that
installs the new trust anchor. `enc-rsa2048-priv.pem` is also committed and appears unused.

### 2.3 CRITICAL — agent VM traffic is cleartext HTTP

`AgentVMService.swift`, `AgentSyncService.swift`, `backend/agent-proxy/main.py`

```
http://<public-GCE-IP>:8080/upload?token=<token>   gzipped copy of the whole omi.db
http://<public-GCE-IP>:8080/auth?token=<token>     body carries the Firebase ID token
ws://<public-GCE-IP>:8080/ws?token=<token>         the whole agent conversation
```

The user's screen history, transcripts, and memories cross the open internet unencrypted,
authenticated by a token that is *also* in the clear and in the query string (so it lands
in every access log along the way). `NSAllowsArbitraryLoads: true` in `Info.plist` is what
permits this, and it disables ATS for every connection the app makes.

Two compounding details:

- `/health` takes no credential and its response is *trusted*. Forging
  `{"databaseReady": false}` makes the client re-upload the entire database — an
  attacker-triggerable exfiltration amplifier.
- No firewall rule for network tag `omi-agent-vm` exists in any IaC in this repo. Because
  the desktop client dials the VM directly from arbitrary residential IPs, whatever rule
  opens 8080 cannot be source-scoped. **Verify in GCP whether 8080 is `0.0.0.0/0`.** The
  VMs are also on the auto-created `default` network, which ships `default-allow-ssh` from
  `0.0.0.0/0`.

Not fixed in code because there is no client-only fix: the VM listener must terminate TLS,
or the external IP must be removed and traffic routed through the existing `agent.omi.me`
ingress. Once that is done, delete the `NSAppTransportSecurity` dict — every other base URL
in the app is already HTTPS.

### 2.4 CRITICAL — a single org-wide Anthropic key is on every user's internet-facing VM

`backend/agent_vm/startup.sh:6` pulls `DESKTOP_ANTHROPIC_API_KEY` and `GEMINI_API_KEY` onto
every VM. The blast radius of compromising *one* user's VM is the company's production
model billing credentials, and revocation is all-or-nothing across the fleet. Route through
the LLM gateway, or mint per-VM keys with a spend cap.

### 2.5 CRITICAL — ACP permission requests are auto-approved

`desktop/macos/agent/src/runtime/desktop-tool-policy.ts:304`

`resolveAcpPermission` selects `allow_always` unconditionally. There is no confirmation
gate anywhere — every `session/request_permission` from the production adapter is
blanket-approved, granting the child agent `Read`/`Write`/`Edit`/`Bash` on any absolute
path in an unsandboxed process with Full Disk Access.

This is documented as intentional at `omi-tool-manifest.ts:1064`, so it is a product
decision rather than an oversight. Flagging it because the consequence is that prompt
injection from a web page, email, or screen OCR reaches a shell.

### 2.6 HIGH — unauthenticated internal WebSocket

`backend/routers/pusher.py:747` — `WEBSOCKET /v1/trigger/listen` takes `uid` as a query
parameter with no auth of any kind, then streams transcripts and audio for that uid.
Mitigated by the pusher service being an internal LB (`gce-internal`, `ClusterIP`), so this
is a VPC-internal trust gap rather than an internet-facing one. Still worth a shared secret.

### 2.7 HIGH — OAuth `state` is unsigned and the MCP callback is unauthenticated

`backend/routers/apps.py:1927` + `backend/utils/mcp_client.py:756`. `generate_state_token`
produces `app_id:uid:nonce` and the nonce is never persisted or checked. An unauthenticated
`GET /v1/apps/mcp/callback?code=...&state=<attacker_app>:<victim_uid>:x` force-installs the
attacker's MCP app into the victim's account. Fix is to persist state in Redis and consume
it atomically — I left it because it touches the OAuth flow and wants a test.

### 2.8 HIGH — no zero-retention configuration on any model or transcription provider

No `store=False` on OpenAI calls, no zero-retention header on Anthropic, no `enable_logging=false`
on ElevenLabs, no opt-out on Modulate (which receives raw live audio by default) or Hume.
Retention posture for the most sensitive data in the product depends entirely on out-of-band
vendor account settings that are invisible to code review and revert silently if an account
is recreated. Note a user who selects `data_protection_level == "e2ee"` still has their raw
audio streamed to Modulate.

### 2.9 HIGH — screen OCR is the only user data stored unencrypted in Firestore

`backend/database/screen_activity.py:44` writes `ocrText` and `windowTitle` in plaintext
while transcripts, memories, chat, and phone numbers all go through `encryption.encrypt`.
Anyone with Firestore read access sees the user's screen contents in the clear. Not fixed
because it needs a backfill migration.

Related: `backend/utils/encryption.py:78` returns the *input* on decryption failure, so a
key rotation or misconfiguration silently feeds ciphertext into prompts and re-embeds it —
failing open in the direction of permanent data corruption.

### 2.10 HIGH — mobile has no secure storage and no certificate pinning

`flutter_secure_storage` is not a dependency at all; `authToken` and `uid` live in plain
SharedPreferences. No pinning anywhere, so any device-trusted CA (MDM, malware, a user
tricked into a profile) intercepts everything.

### 2.11 HIGH — server-only secrets are compiled into the mobile binary

`app/lib/env/prod_env.dart` declares `OPENAI_API_KEY` and `GOOGLE_CLIENT_SECRET`, and
`codemagic.yaml` writes them into `.env` before `build_runner` in eight places. The repo's
own `app/config/client_env_policy.yaml` lists both under `server_secret_env.denied_exact`.
`envied`'s `obfuscate: true` is XOR with an embedded key — recoverable from the IPA/APK in
minutes. **Rotate both if any published build carried them.**

### 2.12 MEDIUM — desktop BYOK keys in plaintext UserDefaults

`SettingsPage.swift:453` — `dev_openai_api_key` and three siblings via `@AppStorage`, i.e.
cleartext in `~/Library/Preferences/<bundleid>.plist`, never cleared on sign-out. Windows
encrypts the same values with DPAPI, so this is a macOS-only gap. `DesktopKeychainStore`
already exists.

### 2.13 MEDIUM — CI

- `.github/workflows/entellegence_issues.yml:36` binds untrusted issue text to env vars and
  then re-interpolates them with `${{ }}` into the `run:` body, which restores the exact
  injection the env vars prevent. Latent — the `issues:` trigger is commented out. It
  becomes a live repo-secret compromise the moment someone uncomments two lines.
- `.github/workflows/entelligence-pr-reviewer.yml:22` passes `OPENAI_API_KEY` and a
  write-scoped `GITHUB_TOKEN` to a third-party action pinned to `@latest`.
- All 12 GCP-touching workflows use a long-lived exportable `GCP_CREDENTIALS` JSON key. The
  Workload Identity Federation config in `infrastructure/opentofu/pilots/` is excellent and
  completely unadopted.

### 2.14 Audited and clean

Recording these so nobody re-audits them: CORS is default-deny and refuses `"*"` at startup.
Firebase token validation is correct everywhere; no `verify=False` outside vendored venvs.
Stripe, Twilio, and Cloud Tasks handlers all verify properly and fail closed. TLS validation
is never disabled anywhere in any client. `firestore.rules` is total-deny with no reachable
client path. Every local HTTP server in the desktop apps binds loopback and authenticates
with a constant-time compare. Sparkle auto-update is sound — HTTPS feed, EdDSA key present,
CI signs. `LocalAgentAPIServer` and `DesktopAutomationBridge` are both well built. No
`pull_request_target` + PR-head checkout. `execute_sql` has no SQL escape (the exposure was
the write path, not an escape). No AWS/GitHub/Slack/Stripe live keys in the tree or history.

---

## 3. Deploy ordering — these will break things if rolled out carelessly

1. **`AGENT_VM_ENABLED=true` must be set in the prod backend env before this deploys**, or
   agent VM provisioning goes dark for everyone (`/v2/agent/provision` → 503). This is the
   intended fail-closed direction, but it is a hard behaviour change on deploy.
2. **The VM name change orphans currently-provisioned VMs.** Existing Firestore records keep
   working, but any user whose record is dropped (including automatically, via the
   `NOT_FOUND` branch and the reaper) re-provisions under a new name and the old instance
   becomes an unreferenced, billable orphan. No migration was written — decide between
   drain-and-rename, accept-plus-sweep, or ship behind a flag.
3. **`shieldedInstanceConfig` requires a UEFI-enabled source image.** If the `omi-agent`
   image family is not UEFI-compatible, `instances.insert` will now fail outright. Verify
   first.
4. **`enable-oslogin` + `block-project-ssh-keys` will lock out anyone using project-wide SSH
   keys** to reach these VMs. They need `roles/compute.osLogin`.
5. **The agent VM image must be rebuilt before `startup.sh` rolls out** — the new script
   mounts the data dir at `/home/omi/omi-agent`; an old root-expecting image paired with the
   new script comes up with an empty database.
6. **`AGENT_VM_SERVICE_ACCOUNT` is unset**, so the `serviceAccounts` block is inert and the
   guest still has no explicitly declared identity. Infra needs to create a dedicated SA with
   `secretmanager.secretAccessor` on the two named secrets and `compute.instances.stop`
   scoped to these instances.
7. **Android LAN cleartext.** The new `network_security_config.xml` covers `localhost`,
   `127.0.0.1`, and `10.0.2.2` only. Android has no CIDR support, so a user pointing the
   self-hosted STT feature at `192.168.x.x` over plain HTTP will now break. Options: require
   https for remote STT endpoints, widen the config, or accept the regression. Product call.
8. **The agent loses `Bash`/`Read`/`Write`/`Edit`/`Glob`/`Grep`/`WebFetch`.** Any behaviour
   that quietly depended on the agent shelling out stops working. That is the point of the
   change, but it is user-visible, and `permission_mode="default"` was not exercised against
   a live VM — worth one manual session to confirm the MCP tools are still auto-approved.

---

## 4. Cost — per-user GCE VMs vs object storage

### What the VM actually is

One dedicated `e2-small` per user in `us-central1-a` with a **50 GB `pd-balanced`** boot
disk and a public IP (`backend/routers/desktop_agent_vm.py:162-179`). The macOS app calls
`provision` automatically on every launch for signed-in users.

It holds the user's entire `omi.db`: screenshots metadata with OCR text and 3072-dim
embeddings, transcription sessions and segments, memories, action items, focus sessions,
observations, live notes. Screenshot *pixels* stay local — the VM copy is metadata, OCR
text, and embeddings.

It self-stops after 30 minutes idle, so vCPU and IP are usage-proportional. **The disk is
not.** `autoDelete: true` only fires on instance *delete*, and nothing in the product ever
deletes an instance — there is no deprovision route. The only backstop is a reaper CronJob
whose checked-in default is `DRY_RUN=true`.

### At 300,000 users

| | | Monthly |
|---|---|---|
| 50 GB pd-balanced × 300k, billed forever | $5.00/user unconditional | **$1,500,000** |
| e2-small compute (assume 30% DAU, ~3h/day) | ~66 h/mo × $0.01675 | ~$100,000 |
| External IP while attached | ~66 h/mo × $0.005 | ~$30,000 |
| | | **~$1.63M/month** |

**92% of that is idle disk**, held for users who may have opened the app once.

### R2 replacement

| | | Monthly |
|---|---|---|
| Storage, ~1 GB/user avg @ $0.015/GB | 300 TB | $4,500 |
| Class A writes, **batched to ~1 object/min while active** | ~3.2B ops @ $4.50/M | ~$14,500 |
| Class B reads | negligible | <$500 |
| Egress | R2 charges none | $0 |
| | | **~$20,000/month** |

**Saving ≈ $1.6M/month, ~99%.**

### Three things that number depends on

1. **Do not lift the sync cadence as-is.** `AgentSyncService.swift:116` syncs every
   **3 seconds** — roughly 10k–30k writes per active user per day. Naively mapped to R2
   Class A operations at 300k users that is ~180 billion ops/month, **~$810M**. The write
   path must be batched before any object-storage migration. This is the single thing that
   turns the migration from a 99% saving into a catastrophe.
2. **R2 replaces storage, not compute.** The VM also runs the Claude agent, a headless
   Playwright browser, and SQL. You cannot delete that with a bucket — compute has to
   consolidate into shared multi-tenant workers, which is the real architectural work and
   where the remaining $130k lives.
3. **SQLite-on-object-storage is a poor fit for the read path.** `semantic_search`
   (`backend/agent_vm/main.py:359`) full-scans the embedding column and computes cosine
   similarity in Python. On R2 that is a whole-object read per query. The realistic target
   is a shared vector store plus Postgres, not literally a SQLite file in a bucket.

### Two changes that need no architecture work at all

- **Turn the reaper live.** It ships `DRY_RUN=true` and has no CD path. This alone reclaims
  most of the disk spend.
- **Change one integer.** `"diskSizeGb": "50"` is hardcoded for a database estimated at
  1–4 GB. Dropping to 10 GB cuts the largest line item by 80% — $1.5M → $300k — with a
  one-character-ish diff.

Numbers are list-price `us-central1` and assume 30% DAU at ~3h/day; the per-user DB size
(1 GB average) is the weakest input and is worth measuring on a real install before anyone
commits to a plan. No pruning exists for `transcription_segments` or `observations`, and
there is no `VACUUM` anywhere, so the DB file only ever ratchets up to its high-water mark.
