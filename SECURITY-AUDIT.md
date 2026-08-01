# Security audit — 2026-08-01

Multi-agent audit of the whole repo at `upstream/main` (`6c4d752b2f`), plus the fixes
applied on this branch. Nothing here originates from a feature PR; all of it is on `main`
today.

Two rounds so far. **Round 1** (sections 1–3) covered authz, transport, secrets, storage
ACLs, local RCE, and mobile. **Round 2** (section 5) applied lenses round 1 never used —
dependencies, concurrency, billing abuse, resource exhaustion, crypto, the web tier, the
Windows app, and fail-open patterns — and found more than round 1 did, including the single
most expensive bug in the repo. Rounds continue until one produces no new HIGH or CRITICAL.

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

---

## 5. Round 2 — fixed on this branch

Different lenses from round 1. Everything below is now fixed unless marked otherwise.

### 5.1 Money

| | Finding |
|---|---|
| CRITICAL | **`backend/routers/desktop_proxy.py` — a one-line binding error made the daily cap unreachable.** `check_rate_limit` returns `(allowed, remaining, retry_after)`; the code bound `_, current, _` and then tested `current > _DAILY_HARD_LIMIT`. `current` was actually `remaining`, which starts at 1499 and counts *down*, so `> 1500` was never true. The 1,500/day Gemini cap was dead code and the real ceiling was the 30/60s burst limit — **43,200 requests/day per free account on Omi's key**. The same inversion ran the pro→flash cost downgrade backwards. |
| CRITICAL | `/v1/omni/relay` — a realtime LLM websocket relay on the platform OpenAI key with no quota, no rate policy, no connection cap, no session timer, and no usage recording. ~$4–6/hour per socket, unbounded sockets. Capped; **per-token metering is still missing** (it needs protocol-aware parsing of the upstream stream). |
| CRITICAL | `/v2/realtime/session` minted OpenAI realtime client secrets with no expiry — usable directly against OpenAI, bypassing Omi entirely, so the spend is invisible until the invoice. Now bounded and quota-gated. `/v2/realtime/usage` accounting remains **client-self-reported** and trivially skipped; that needs provider-side reconciliation. |
| HIGH | Client picked its own Stripe `price_id` with no membership check, and `LEGACY_PRICE_MAP` accepted retired prices — subscribe at the old $19.99 tier, receive current entitlements. |
| HIGH | Paid-app entitlement was a 30-day Redis key with no revocation on refund, chargeback, or cancellation. Subscribe → enable → dispute → keep access. It also failed the other way: annual subscribers lost access on day 31. |
| HIGH | `/v2/sync-local-files` took an unbounded `files[]` behind a single boolean pre-flight check — ~900 hours of audio and ~$230 of STT from one request. |
| MEDIUM | Install counts and ratings were both inflatable (enable is not idempotent, reviews require no install), and both drive marketplace ranking. |

### 5.2 Availability

| | Finding |
|---|---|
| CRITICAL | **Quadratic regexes in `web_tools.py` blocked the event loop.** Three unanchored lazy `DOTALL` patterns run sequentially and synchronously inside `async def`, against a 512 KB fetch cap. Measured 7.4s at 140 KB, ~100s+ at the cap. Trigger: one chat message containing an attacker's URL — the agent prompt *instructs* the model to fetch any URL the user shares. A handful of messages is a full backend outage. Now 0.18s. |
| CRITICAL | Limitless ZIP import read members with no decompressed-size cap — 100 MB → ~103 GB, in-process in the API container. The correct bounded-ZIP pattern already existed in this repo and had not been applied. |
| CRITICAL | Agent-VM upload's decompressed cap equalled its compressed cap, so a ~10 MB request drove 10 GB (~1000:1). |
| CRITICAL | MCP batch endpoint charged one rate-limit token for an unbounded array — a ~100,000× bypass. |
| HIGH | `/v1/tools/conversations` allowed `limit=5000` into a photo N+1 → 5,001 Firestore round trips, unrate-limited. The photo-free query already existed. |
| HIGH | `multipart.py` raised the per-part cap for file parts but left non-file fields on the raised cap with `max_fields` defaulted to 1000 — a 200 GB ceiling. The helper that exists to *protect* uploads was what unlocked the amplification. |
| HIGH | Unbounded user-supplied ID lists drove one Firestore query per element; the shared-chat read leg is **unauthenticated**, making it a durable anonymous amplifier. |
| MEDIUM | Quadratic inline-code regex on every push-notification body: 21s at 100 KB, in a sync handler holding a threadpool slot. Now 0.000s. |

### 5.3 Fail-open

| | Finding |
|---|---|
| CRITICAL | **agent-proxy stored "enhanced protection" chat in plaintext.** It read `ENCRYPTION_SECRET` with a default of `''` and, when unset, wrote plaintext *and relabelled the record `'standard'`* so nothing downstream could tell. The prod Helm chart never injected that secret — this was the shipped production configuration, not a hypothetical. It is a fork of `utils/encryption.py` with that file's fail-closed guard converted to a fail-open one. |
| HIGH | `decrypt()` returned its own input on any exception, **including a GCM authentication-tag failure** — so tampering was indistinguishable from success, and a wrong key silently turned every read into a base64 blob that could then be re-persisted as content. |
| HIGH | `data_protection_level` accepted and persisted `'e2ee'`, but no write path encrypts for it — the strongest-sounding setting stored fully plaintext. |
| HIGH | ~20 admin endpoints used `secret_key != os.getenv('ADMIN_KEY')`. Unset is safe; **set-to-empty authenticated any empty header**, and the prod ExternalSecret materialises empty when the remote secret is absent. `POST /v2/desktop/releases` writes the auto-update manifest. |
| MEDIUM | `_enforce_rate_limit(..., fail_closed=False)` — the insecure value was the default, and the third-party surfaces (MCP, marketplace integrations) took the default. A Redis blip made them unmetered. |
| MEDIUM | The voice-duration Lua script registered once at import; Redis down at import meant that pod served **unmetered transcription for its entire lifetime**, long after Redis recovered. |
| MEDIUM | The transcription budget was skipped entirely when a file's duration could not be parsed — strip the duration metadata and every upload was free. |

### 5.4 Web

| | Finding |
|---|---|
| CRITICAL | **`personas /api/store-facts` was unauthenticated** and took `uid` from the request body, then wrote memories into that account using the server's privileged integration key. Anyone could inject memories into any Omi user's memory bank — which then feed that user's assistant. Persistent prompt injection, at scale, with no credential. `/api/enable-plugins` had the same shape plus Redis key injection. |
| HIGH | `uploadThumbnails` is a public Next server action that fetched a client-supplied URL with no validation and never checked the token first — SSRF to `169.254.169.254` from the frontend service. |
| HIGH | JSON-LD used `JSON.stringify` inside `dangerouslySetInnerHTML`, which does not escape `<`/`>`; developer-submitted app metadata could break out of the script tag on the public marketplace pages. With the Firebase token in localStorage and no `script-src` CSP anywhere, that is account takeover. |
| HIGH | `markdown-to-jsx` passes raw `<script>` through; it rendered LLM and third-party-app content on the public shared-conversation page. |
| MEDIUM | The admin Firebase ID token was persisted to localStorage inside SWR cache keys and never cleared on sign-out; admin payout responses were marked publicly cacheable. |

### 5.5 Client

| | Finding |
|---|---|
| CRITICAL | **`Logger.swift` — a local write primitive.** The production log was `/tmp/omi.log`. The permission-normalisation helper correctly returned `false` when it could not remove an attacker-owned file in sticky `/tmp`, **but the caller never checked the result**, then used `fileExists` + `FileHandle` — both of which follow symlinks. Another local account could read the entire app log, or make Omi append to and create any path the victim can write (`~/.zshenv`, a LaunchAgent plist) as the victim. Moved to `~/Library/Logs/Omi` (0700/0600, `O_NOFOLLOW`, fstat owner check), failing closed, with rotation. |
| HIGH | **Windows: persistent renderer→RCE.** `agentCommands` came from the renderer over IPC *and was read from localStorage*, then reached `spawn(command, { shell: true })`. One write to that origin's storage was persistent code execution, re-run on every agent turn. Moved to main-process settings. |
| HIGH | **`TaskAgentSettings` read its skip-permissions flag as `?? true`** — deliberately permissive when unset, unlike every other flag in the same initializer. A fresh install ran Claude with `--dangerously-skip-permissions` in a process holding Full Disk Access, driven by prompts built from screen OCR. This is the same defect round 1 fixed inside the agent VM, still live on the desktop. |
| HIGH | **A 429 made `AgentSyncService` retry *faster* than a 500 would.** Only 5xx triggered backoff; 4xx left the interval pinned at the 3-second base, re-POSTing the same rejected batch forever — 3 req/s per client, 259k/day. A server-side rate limiter physically could not shed the load. |
| HIGH | `TranscriptionService` did not re-check `shouldReconnect` after awaiting the auth token, so an authenticated socket carrying the user's BYOK Deepgram key could open **after** the user hit stop, with no handle to close it. No jitter and no close-code inspection either — the Windows client of the same product already had both, with a comment naming macOS as the un-jittered reference. |
| HIGH | `stopCapture()` snapshotted a stale IOProc, so a device change racing stop could leave the microphone live with the OS indicator lit and `isCapturing == false` — meaning every later stop was gated off. |
| HIGH | **Retention was largely fictional.** Three retention functions existed with zero call sites; `observations` used `onDelete: .setNull` so they survived the screenshot sweep forever; synced transcription sessions were never aged out; WAL audio was only swept for `.synced` entries and only from inside `syncToCloud`, so a signed-out or offline user accumulated ~30 MB/h indefinitely; retention only ran from the frame-ingest path, so it stopped exactly when capture stopped — including when the disk filled; and with no `VACUUM` or `auto_vacuum`, lowering the retention setting reclaimed zero bytes. Nothing checked free space before any write, and corrupt-DB recovery needed 3× the DB size with a fatal copy, so a full disk could crash-loop the app on a database it could neither open nor recycle. |
| — | **Data loss, not security:** the Trash cleanup deleted every entry whose lowercased name merely *contained* `"omi"` — `domino.pdf`, `comic.png`, `economics.xlsx` — unrecoverably. |

### 5.6 Dependencies

Patched: `cryptography` 46.0.7 → 48.0.1 in agent-proxy (GHSA-537c-gmf6-5ccf, vulnerable
OpenSSL statically linked into the wheel — and this is the TLS-terminating proxy);
`tornado` → 6.5.7, `soupsieve` → 2.8.4, `python-multipart` → 0.0.31, `ujson` → 5.13.0 in
`plugins/` and `mcp/examples/`. Four mutable git refs in `app/pubspec.yaml` pinned to SHAs —
three shipped mobile codec components tracked branches on a **personal, non-org** GitHub
account and one had no `ref` at all, so it followed that fork's default HEAD into our builds.

**The real finding is drift.** In four separate cases the same package was already patched in
one of the repo's ~60 hand-copied `requirements.txt` files and stale in another. Fixing the
mechanism (a `uv` workspace — the tooling is already vendored) is worth more than fixing the
four instances.

**Still outstanding, each needs its own PR:**

- **`websockets` 12.0 → 15.x.** This *blocks* the `langsmith` 0.8.5 → 0.8.18 fix
  (GHSA-f4xh-w4cj-qxq8, arbitrary server-side file read): from 0.8.6 onward langsmith
  requires `websockets>=15.0`, and the backend pins 12.0. Note `backend/openapi-requirements.txt`
  already pins *both* `langsmith==0.8.18` and `websockets==12.0` — an unsatisfiable
  combination that only survives because that file has no solver-verified lock.
- **Electron 39.8.10** — EOL since 2026-05-05, four majors behind, so every Chromium CVE
  disclosed since then is permanently unpatched in a shipped desktop app. Top outstanding
  dependency risk. Native-ABI migration (`better-sqlite3`, `koffi`).
- **Starlette 0.49.3 → 1.3.1** — five advisories, two HIGH. CVE-2026-54283 (form limits
  silently ignored for urlencoded bodies) is genuinely reachable: `POST /token` in
  `backend/routers/auth.py:545` is the unauthenticated OAuth token endpoint and is exactly
  the vulnerable shape. Needs a coordinated FastAPI major bump.

### 5.7 Round 2 — found but NOT fixed

- **`resolveAcpPermission` auto-approves with `allow_always`** (`desktop-tool-policy.ts:304`)
  — still the widest single exposure, and documented as intentional, so it is a product call.
- **`RewindSettings` is still unsynchronized.** The password-manager screenshot-exclusion gate
  is a `@Published Set<String>` on a `nonisolated(unsafe)` singleton read from actors. The two
  `TaskAssistant` call sites now hop to the MainActor, but making the type `@MainActor` cascades
  into ~15 files across four other subsystems (`VideoChunkEncoder` and `RewindIndexer` read it
  from *synchronous* members inside actors, so it is a signature change, not an `await`).
- **Screen OCR is still unencrypted in Firestore** while transcripts, memories, and chat are
  encrypted — needs a backfill migration.
- **Mobile still has no secure storage and no certificate pinning**; `flutter_secure_storage`
  is not a dependency at all.
- **`OPENAI_API_KEY` and `GOOGLE_CLIENT_SECRET` are still compiled into the mobile binary**
  by CI, contradicting the repo's own `client_env_policy.yaml`. Rotate if any published build
  carried them.
- **Firestore/Redis counters fail open individually**, which is defensible per-counter but
  means one Redis degradation removes nearly all cost controls at once.
- **No zero-retention configuration on any model or transcription provider.**
- **Idempotency gaps** remain on the integration-webhook conversation-create path and the
  Limitless import (a redelivery duplicates conversations, action items, and real
  third-party tasks).

### 5.8 Additional deploy-ordering notes from round 2

- **`ENCRYPTION_SECRET` must exist in `prod-omi-backend-secrets` before the agent-proxy chart
  is applied.** agent-proxy now raises at import, so a missing or short value is a
  CrashLoopBackOff instead of a silent plaintext write. The pusher chart already reads the
  same key from the same secret.
- **`ADMIN_KEY` must be non-empty in every environment**, or all admin routes — including
  desktop release publishing — now 403 instead of accepting an empty header.
- **Phone-call quota and the MCP/integration/relay rate limits now fail closed**, so a Redis
  outage blocks those paths rather than going unmetered. Worth an alert.
- **Desktop retention now actually deletes**, so users will see historical derived data
  disappear on first run after upgrade, and existing databases get a one-time full `VACUUM`
  the first time a sweep leaves >20% of the file free.
- **Capture stops below 2 GB free** instead of filling the disk.
