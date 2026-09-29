# Omi repository audit — 2026-09-11

Read-only recon of `/Users/undivisible/projects/omi`. No pushes, merges, deploys, deletes, or live attacks.

**Checkout:** `main` @ `1c196bbfae` (2026-09-06). Local `main` was **227 commits behind `origin/main`** at audit start. Findings are for this tree unless noted.

**Confidence:** 8/10 for in-tree code. Live GCP IAM, deployed Firestore rules, and whether independent plugin services are internet-reachable were **not** probed.

---

## 1. Overview

Omi is a memory-first capture product: wearable + phone + desktop + web → one FastAPI backend → Firestore as canonical state. The product loop is **Capture → Understand → Remember → Retrieve → Act** (`PRODUCT.md`).

| Surface | Path | Stack |
|---|---|---|
| API / listen / memory | `backend/` | Python 3.11, FastAPI, Firestore, Redis, GCS |
| Desktop-backend | `backend/desktop_backend.py` | Separate Cloud Run image |
| LLM gateway | `backend/llm_gateway/` | Internal service-auth FastAPI |
| Mobile | `app/` | Flutter iOS/Android, Pigeon + MethodChannels |
| macOS | `desktop/macos/` | SwiftUI, unsandboxed, bundled TS agent |
| Windows/Linux | `desktop/windows/` | Electron + React, pnpm |
| Web client | `web/app/` | React 19 / Moonshine / Bun |
| Admin | `web/admin/` | Next.js, Firebase + Admin SDK |
| Plugins | `plugins/` | Legacy Cloud Run monolith + 28 independent `omi-*-app/` services |
| Firmware | `omi/firmware/` | Zephyr / nRF, BLE GATT |
| Glass | `omiGlass/` | ESP32 + Expo |
| MCP hosted | `backend/routers/mcp_sse.py` | OAuth + `omi_mcp_` keys |
| MCP local | `mcp/` | stdio server |
| Invariants | `product/invariants/` | Locked product law + CI citation |
| Parity | `contracts/parity/` | Cross-platform fixtures |

**Trust model (intended):** Firebase UID is identity. Clients never talk to Firestore. Backend Admin SDK + IAM is the data plane. `firestore.rules` deny all client reads/writes. Conversations/memories are AES-256-GCM per-uid. LLM gateway is not client-reachable.

**Data stores:** Firestore (SoT), Redis (cache / rate limit / locks — **fail-open**), GCS (audio/frames), Pinecone (vectors, derived), Stripe, PostHog. No production Postgres. `backend/AGENTS.md` still mentions Neo4j; `backend/database/knowledge_graph.py` is Firestore-only (doc drift).

**This repo is unusually well-guarded** for its size: deny-all Firestore rules, default-deny CORS, SSRF pinning for *app* webhooks, Stripe `construct_event`, Cloud Tasks OIDC, a huge checks-manifest, failure-class registry, BYOK fingerprinting, account-deletion fail-closed, INV-AUTH-1 session ownership. The remaining risk is concentrated in **god-keys, plugin auth, developer webhooks, wearable BLE, and CI deploy credentials**.

---

## 2. Architecture (trust boundaries)

```
Wearable BLE (unencrypted GATT audio)
    → Mobile / Desktop capture
        → Firebase ID token / desktop OAuth+PKCE
            → FastAPI (api.omi.me / api.omiapi.com)
                → Firestore Admin IAM  (client rules deny-all)
                → Redis fail-open
                → GCS / Pinecone / Stripe
                → LLM gateway (service bearer)
                → pusher / parakeet / diarizer / VAD (GKE GPU)
```

**Identity paths**

- HTTP: `Authorization: Bearer` Firebase ID token (`backend/utils/other/endpoints.py` `get_current_user_uid`).
- **ADMIN_KEY impersonation:** `Bearer <ADMIN_KEY><uid>` — default **on** (`ADMIN_KEY_AUTH_ENABLED` defaults `'true'`). Constant-time prefix compare. Same secret used as admin `secret-key` on many routers and as `OMI_API_SECRET_KEY` in `web/admin`.
- Local no-credential bypass: `LOCAL_DEVELOPMENT=true` + no SA/ADC → uid `'123'`. Gated; inert if real Firebase creds exist.
- Key families: `omi_mcp_` → MCP; `omi_dev_` → `/v1/dev*`; else Firebase.
- Desktop OAuth: `/v1/auth/*`, PKCE S256 required, redirects limited to custom schemes + HTTP loopback. `https://` redirects rejected (RFC 8252).
- MCP: OAuth (confidential + optional public PKCE) or hashed API keys. Refresh tokens 365 days default.
- Desktop-backend is a **separate** Cloud Run service. macOS Beta talks to `api.omiapi.com` but **production Firebase** (`INV-DATA-1` / `INV-BETA-1`).

**Native bridges**

- Flutter: Pigeon (BLE, watch recorder, Ray-Ban Meta, phone mic) — in-process. MethodChannels for phone calls, Apple Health, Reminders, battery widget.
- macOS: unsandboxed (`Omi-Release.entitlements`: sandbox false, Apple Events, mic, screen). Opt-in `LocalAgentAPIServer` on `127.0.0.1:47778` with Keychain Bearer.
- Windows: Electron `webSecurity` ON, `sandbox: false` on main window. CORS shim strips Origin and injects `access-control-allow-origin: *` for Omi APIs. Named pipes for agent tools use random path + hello token.

**Deploy**

- Main API: `gcp_backend.yml` (prod SHA needs Release Eligibility; hatch `skip_eligibility_proof` is gated).
- Desktop-backend independent of app release.
- macOS: hourly candidate → Codemagic → Beta; Stable is manual.
- Plugins monolith: `gcp_plugins.yml` **workflow_dispatch**, **arbitrary `branch` input**.
- OpenTofu exists only as a WIF pilot. Live GCP still uses long-lived `GCP_CREDENTIALS` JSON keys.

---

## 3. What is already strong

Do not “fix” these; they are the floor.

- Firestore client rules deny-all (`firestore.rules`). Memory/MCP key docs called out as server-owned.
- CORS: empty default, `*` raises (`backend/main.py`, `desktop_backend.py`). `FC-permissive-cors-origin-allowlist`.
- App-marketplace webhooks: `safe_request_target` + DNS-rebinding pin (`backend/utils/http_client.py`).
- Stripe webhooks: `Webhook.construct_event`.
- LLM gateway: service token + caller header; unconfigured → 503, not open.
- Account deletion fence fail-closed (503 if status unreadable).
- BYOK: raw keys not persisted; fingerprints only; WS handlers must extract headers explicitly.
- Desktop session ownership (`INV-AUTH-1`) with a large Swift test set + `check_desktop_auth_session.py`.
- Agent VM retired as unauthenticated tombstones (410 / null) so 401 cannot force-sign-out clients.
- Checks manifest, secret-name ratchet, dead-code ratchet, product-invariant citation, break-glass hatches that actually require confirm strings.
- `pull_request_target` only on `pr-declined-comment.yml`: no fork checkout, comments only.

**Runtime still needed:** prove deployed Firestore rules == this file (`backend/scripts/firestore_rules_iam_proof.py --execute`). In-repo comments say existing non-memory client rules must be added before deploy if a project still uses client SDK access.

---

## 4. Top risks

Severity: **P0** = unauthenticated or god-token path to other users’ data if the surface is live. **P1** = authenticated SSRF / cross-account / credential dump with realistic exploit. **P2** = defense-in-depth, leak-on-compromise, hygiene.

### P0

#### P0-1. Plugin fleet treats `uid` as authentication

**Confirmed in code.** Live exposure needs a URL check.

Independently deployed `plugins/omi-*-app/` services (28) plus the legacy monolith authenticate **by query/body uid**, not by Firebase token or HMAC from the backend.

Backend delivery (`backend/utils/app_integrations.py`) POSTs conversation JSON and **appends `?uid=`**. No `X-Omi-Signature`.

Concrete example — GitHub plugin:

- `POST /save-agent-key?uid=&provider=&key=` stores a provider API key with **no auth** (`plugins/omi-github-app/main.py` ~1335).
- Chat tools (`/tools/create_issue`) take `uid` from JSON and use that user’s stored GitHub `access_token`.
- Tokens live in plaintext `users_data.json` (`simple_storage.py`). Railway `/app/data` comments imply this is a real deploy.

Dropbox plugin: `/auth/dropbox?uid=`, `/disconnect?uid=`, `/update_settings?uid=` (`plugins/omi-dropbox-app/main.py`).

Legacy Notion OAuth: `state = uid` with **no CSRF nonce** (`plugins/oauth/client.py` — comment even says “Should use encryption on state”). Callback binds Notion token to that uid.

`plugins/notifications/hey_omi.py` `POST /webhook` takes `uid` from body and can send Omi notifications.

**Impact:** Anyone who can reach a plugin URL and guess/learn a Firebase uid can: steal/replace GitHub/Dropbox/Notion tokens, write issues as the user, inject conversation webhooks, store BYOK keys in query strings (access logs). Firebase uids leak in logs, referrals, shared links.

**Fix:** One shared webhook authenticator in `omi-plugin-sdk`: HMAC of body with per-install secret, plus backend-signed uid. Reject uid-only. Stop putting secrets in query strings. Encrypt token stores. Do not add features to the monolith (`LEGACY_MONOLITH.md`).

**Verify live:** which `omi-*-app` hostnames are public; whether `gcp_plugins.yml` prod still serves `hey_omi` / Notion OAuth.

---

#### P0-2. `ADMIN_KEY` is a production impersonation + admin god-token

**Confirmed.** Default on. Prod runtime_env binds `ADMIN_KEY` from Secret Manager. `ADMIN_KEY_AUTH_ENABLED` is **not** set in deploy overlays → remains `'true'`.

```python
# backend/utils/other/endpoints.py
if hmac.compare_digest(candidate, admin_key.encode()) and len(token) > len(admin_key):
    return token[len(admin_key):]  # any uid
```

Same secret:

- Impersonates any user via `Authorization: Bearer <ADMIN_KEY><uid>` (web admin does this on purpose).
- Authorizes admin routers via `secret_key != os.getenv('ADMIN_KEY')` (apps approve/reject, push-to-user, memory admin, announcements, updates). Several of those compares are **not** constant-time.

`.env.template` still describes this as a local-dev bypass.

**Impact:** One env leak (log, support dump, over-broad SA, compromised Actions secret) → every account + admin writes. Not unauthenticated, but blast radius is total.

**Fix:**

1. Prod: `ADMIN_KEY_AUTH_ENABLED=false` unless a dedicated break-glass env.
2. Split secrets: impersonation ≠ admin ≠ web-admin.
3. Short-lived scoped admin tokens (Firebase custom claims or signed JWT).
4. One `_verify_admin_key` with `compare_digest` and reject empty.

---

### P1

#### P1-1. Developer webhooks skip the SSRF guard used for app webhooks

App integrations use `safe_request_target` (private/loopback/link-local/CGNAT/metadata + DNS-rebinding pin).

Developer webhooks do **not**:

```python
# backend/routers/users.py
def set_user_webhook_endpoint(...):
    url = data.url
    set_user_webhook_db(uid, wtype, url)  # no assert_public_http_url
```

```python
# backend/utils/webhooks.py
response = await client.post(webhook_url, **request_kwargs)
```

`webhook_url_from_setting` only strips `audio_bytes` suffixes. Delivery logs the **full URL**. `uid` is appended as a query param.

**Impact:** Any signed-in user can point a webhook at `http://169.254.169.254/`, Redis, or internal GKE. Conversation text and **audio bytes** follow. Requires a valid Firebase session.

**Fix:** Same `safe_request_target` at **set and send**; HTTPS-only; pin IP; stop logging full URLs; HMAC.

**Runtime:** Cloud Run/GKE egress + IMDS hop limit.

---

#### P1-2. Integration OAuth tokens stored in Firestore plaintext

`backend/database/users.py` `set_integration` merge-sets `access_token` / `refresh_token` as-is. Conversations/memories use AES-GCM; integrations do not.

Client rules deny-all, so this is IAM / export / backup risk, not a client-SDK read.

**Fix:** Encrypt with the per-uid AES-GCM path before write. Audit SAs that can read `users/*/integrations`.

---

#### P1-3. macOS BYOK keys in UserDefaults

`desktop/macos/Desktop/Sources/APIKeyService.swift`: “Keys live in UserDefaults”. Storage keys `dev_openai_api_key`, etc. Windows uses Electron `safeStorage` (DPAPI). Auth tokens already go through `DesktopKeychainStore`.

**Impact:** Local malware, Time Machine, or another process in the container reads provider keys. BYOK users are exactly the people whose keys matter.

**Fix:** Keychain, same as session tokens. Treat as `FC-private-credential-file-permissions`.

---

#### P1-4. Wearable BLE audio GATT is unencrypted

`CONFIG_BT_SMP=y` and pairing callbacks exist, but characteristics use `BT_GATT_PERM_READ` / `WRITE` **without** `ENCRYPT` (`omi/firmware/omi/src/lib/core/transport.c`). Protocol is public (`sdks/device/PROTOCOL.md`). `CONFIG_BT_MAX_CONN=1`.

**Impact:** Proximity attacker can connect when the phone is not, subscribe to the audio notify characteristic, and stream microphone audio. Classic wearable issue; still a product secret (conversations).

**Fix:** `BT_GATT_PERM_READ_ENCRYPT` / bonding required before CCC enable. Confirm phone-side pairing is mandatory.

---

#### P1-5. Long-lived GCP JSON keys in GitHub Actions

Almost every deploy: `credentials_json: ${{ secrets.GCP_CREDENTIALS }}`. WIF exists only for the OpenTofu **pilot**.

`gcp_plugins.yml` accepts **any branch** into prod (environment protection is the only gate).

Most third-party actions are **floating tags** (`actions/checkout@v7`, `google-github-actions/auth@v3`). SHA pins are rare (`astral-sh/setup-uv`, bun). `pypa/gh-action-pypi-publish@release/v1` is a moving tag on a publish job.

PR checkouts generally `persist-credentials` default (write token in `.git`). Many workflows omit top-level `permissions:`.

**Impact:** Stolen Actions secret or compromised action = GCP principal. Compromised PR job with write token can push if org default is not read-only.

**Fix:** WIF for prod; SHA-pin secret-touching actions; `permissions: {}` + `persist-credentials: false` on PR jobs; drop arbitrary-branch plugin deploys.

---

#### P1-6. Windows Electron CORS shim + unsandboxed renderer

`desktop/windows/src/main/index.ts`: `webSecurity` ON (good) but Origin stripped and `access-control-allow-origin: *` injected for `api.omi.me` / desktop-backend / PostHog. Main window `sandbox: false`.

**Impact:** Renderer XSS becomes full authenticated API access as the user (screen capture already runs in-process).

**Fix:** Allow only the derived localhost origin; keep Origin; CSP; consider `sandbox: true` + preload-only.

---

### P2

| ID | Finding | Evidence | Fix |
|---|---|---|---|
| P2-1 | BYOK fingerprints unsalted unless `BYOK_FINGERPRINT_PEPPER` set; **pepper is not in `runtime_env.yaml`**. Legacy unpeppered hashes still accepted when pepper is set. | `backend/utils/byok.py` | Require pepper in prod; migrate; drop plaintext-hash compare |
| P2-2 | MCP/app API keys hashed with unsalted SHA-256 | `backend/utils/mcp_api_keys.py` | HMAC or KDF with server secret |
| P2-3 | Decrypt fail-open returns ciphertext as if plaintext | `backend/utils/encryption.py` | Raise / return error; never echo ciphertext |
| P2-4 | Redis rate-limit and listen lock fail-open | `backend/database/redis_db.py`, AGENTS.md | Fail-closed on listen / LLM |
| P2-5 | `verify_id_token` without `check_revoked=True` on almost all paths | `endpoints.py` | Revocation check on sensitive routes |
| P2-6 | Raw BYOK keys on every HTTP/WS header (`X-BYOK-*`) | `utils/byok.py` | Confirm access-log redaction; short-lived envelope |
| P2-7 | Developer/app webhooks have no HMAC | `utils/webhooks.py`, `app_integrations.py` | Per-user webhook secret |
| P2-8 | Admin `secret_key != ADMIN_KEY` timing | `memory_admin.py`, `apps.py`, `notifications.py`, `announcements.py`, `updates.py` | Shared compare_digest helper |
| P2-9 | Desktop OAuth allows **any** custom URL scheme except a denylist | `backend/routers/auth.py` | Allowlist `omi`, `omi-computer`, `com.omi.app`, loopback |
| P2-10 | MCP OAuth `hash_secret` is SHA-256; refresh TTL 365 days | `database/mcp_oauth.py` | HMAC; shorter refresh; reuse detection already exists |
| P2-11 | macOS local agent HTTP on TCP 47778 (opt-in, Bearer in Keychain) | `LocalAgentAPIServer.swift` | Unix socket mode 0600 |
| P2-12 | Flutter deep-link logging of full URIs | `app` AppLinks | Never log query/path tokens |
| P2-13 | Desktop auto-release `contents: write` + GitHub App token hourly | `desktop_auto_release.yml` | Environment reviewers on tag-push |
| P2-14 | Swift CI cache restore-keys prefix; PRs restore `.build` from main | `desktop-swift-ci.yml` | Exact-key restore only |
| P2-15 | `AGENTS.md` documents `desktop_auto_release.yml` `release_mode=break_glass` — **that input does not exist** | workflow + `test_plan_desktop_release.py` | Fix the hatch docs |
| P2-16 | PRODUCT.md still mentions a seven-day soak; invariant README says soak is gone | `PRODUCT.md` vs `product/invariants/README.md` | Align docs |
| P2-17 | No `storage.rules` in repo | — | Add GCS/Firebase Storage rules or document IAM-only |
| P2-18 | `ENCRYPTION_SECRET` imported at module load | `utils/encryption.py` | Lazy load; never default empty in tests that import prod |

---

## 5. Easy wins

Small, verifiable, high leverage.

1. **Prod env:** set `ADMIN_KEY_AUTH_ENABLED=false` (or a dedicated break-glass overlay). One line in `backend/deploy/runtime_env`.
2. **Call `safe_request_target` from `set_user_webhook_endpoint` and `_post_dev_webhook`.** The helper and tests already exist (`test_ssrf_public_url_guard.py`).
3. **`BYOK_FINGERPRINT_PEPPER` in Secret Manager + runtime_env.** Code already peppers when set.
4. **One `_verify_admin_key()`** replacing `secret_key != os.getenv('ADMIN_KEY')`.
5. **Decrypt fail-closed** in `utils/encryption.py` (return/raise, don’t return ciphertext).
6. **Stop logging full webhook URLs** (`utils/webhooks.py`).
7. **Allowlist OAuth redirect schemes** instead of “anything not https/javascript”.
8. **`persist-credentials: false`** on all `pull_request` checkouts.
9. **Fix AGENTS.md desktop break-glass** to match `desktop-swift-ci.yml` dispatch.
10. **Move macOS BYOK from UserDefaults to Keychain** — API already exists (`DesktopKeychainStore`).
11. **HMAC plugin webhooks** — even a single shared `OMI_PLUGIN_WEBHOOK_SECRET` is better than uid-only.
12. **GitHub plugin: delete `/save-agent-key` query-string API**; require POST body + signed uid; don’t store keys in `users_data.json` world-readable.

---

## 6. Dead code, drift, high-value product fixes

**Dead-code ratchet** (`.github/scripts/check_dead_code.py`):

| Area | Baseline unreachable | Allowlist |
|---|---|---|
| backend | `utils/llm/trends.py`, `memory/canonical_kg_promotion.py`, `legacy_backfill_inventory.py`, `projections.py`, `utils/other/task.py` | empty |
| flutter | empty | pigeon inputs only |
| agent / windows | empty | empty |

Leftover **compat models** (`TODO: remove after migration` in `backend/models/memories.py`, `chat.py`, `conversation.py`) are **live**, not dead — they violate the “no in-repo compatibility layers” rule until the last client is gone.

**Parity divergences** (`contracts/parity/README.md`) — user-visible, not theoretical:

1. Flutter has Overdue + 7-day aging; macOS/Windows fold past-due into Today.
2. Junk `due_at`: Dart rejects the **whole item**; Windows keeps it as no-due. One bad timestamp breaks mobile sync.
3. Missing `created_at`: Windows fills sync time; Dart keeps null.
4. JIT empty watchlist: macOS ambient vs Windows `none`.
5. macOS task/day adapter still pending (fixtures exist, Swift conformance does not).

Highest-value product fix: **strict vs tolerant `due_at`**.

**Doc drift**

- `backend/AGENTS.md` “Neo4j entity relationships” vs Firestore graph.
- Desktop hatch `release_mode=break_glass` vs actual workflows.
- PRODUCT.md seven-day soak vs locked-on-guard invariant registry.

**Plugins:** SDK auth helpers were **removed** July 2026 (`plugins/README.md`). That is why every app re-invented uid query params. Restoring a tiny HMAC helper in `omi-plugin-sdk` pays for 28 apps.

**Agent VM:** already tombstoned. Good.

---

## 7. CI / release hygiene (summary)

Good: no fork `pull_request_target` code execution; backend break-glass confirm+reason+audit; firmware publish must type `publish`; secret-name classification ratchet; hermetic unit lane excludes integration/live tests.

Fix next:

| Item | Severity |
|---|---|
| GCP JSON keys instead of WIF | P1 |
| Unpinned Actions on secret jobs | P1 |
| Plugin deploy from arbitrary branch | P1 |
| Missing workflow `permissions` + PR credential persist | P1 |
| Cache prefix restore (Flutter / Swift `.build`) | P2 |
| Hourly tag-push with App token | P2 |
| Hatch docs vs YAML mismatch | P2 |

---

## 8. Desktop / mobile bridges (summary)

| Bridge | Auth | Risk |
|---|---|---|
| Flutter Pigeon / MethodChannel | In-process | Dual stacks (mic, BLE, health) — audit handlers, not the transport |
| macOS LocalAgentAPI | Opt-in, loopback, Keychain Bearer, Host/Origin | Same-user RCE into unsandboxed app; prefer Unix socket |
| macOS DesktopAutomationBridge | Non-prod + token | Keep off production (already tested) |
| macOS OAuth loopback | `127.0.0.1` + state | OK |
| Windows named pipes | Random path + hello | OK |
| Windows renderer static server | Unauthenticated loopback | Low confidentiality |
| Windows CORS shim | Origin stripped | P1 XSS amplifier |
| Deep links | Associated domains + custom schemes | Token-in-URL; don’t log |

macOS production entitlements: **sandbox off**. Expected for computer-control; every local listener is therefore a full-privilege endpoint.

---

## 9. Suggested follow-ups (ordered)

**This week (security)**

1. Confirm live plugin hostnames and whether uid-only endpoints are public. If yes, treat P0-1 as incident: HMAC or take offline.
2. Set `ADMIN_KEY_AUTH_ENABLED=false` in prod overlay (or split keys).
3. SSRF-guard developer webhooks.
4. Prove deployed `firestore.rules` with `firestore_rules_iam_proof.py --execute`.

**This month**

5. Encrypt integration tokens at rest; Keychain BYOK on macOS.
6. Plugin SDK HMAC + migrate GitHub/Dropbox/Notion/hey_omi.
7. WIF for GCP deploys; SHA-pin Actions; `permissions: {}` + `persist-credentials: false`.
8. BLE GATT encrypt-required.
9. BYOK pepper + HMAC API-key hashes.

**Product / quality**

10. Converge `due_at` / Overdue buckets (parity register).
11. Delete or issue-link backend compat TODOs.
12. Align AGENTS.md hatches and PRODUCT.md soak text.
13. Shrink dead-code baseline (`trends.py` et al.) or allowlist with a reason.
14. Unix-socket local agent API; tighten Electron CORS.

**Do not**

- Deploy, merge, or “tighten” Firestore rules without a live `rules:get` proof (deny-all in git may already be prod — or not).
- Enable Firebase client access “for admin UI convenience”; admin already uses Admin SDK.
- Re-open Agent VM.

---

## 10. What this audit did not do

- No production HTTP, no secret values, no IAM enumeration.
- Did not fetch/merge the 227 commits on `origin/main` (post-2026-09-06). Re-scan if those include plugin auth or webhook SSRF work.
- Did not run the app, desktop named bundle, or firmware on hardware.
- Did not verify Google API-key application restrictions, Stripe endpoint secrets, or `RATE_LIMIT_SHADOW` in prod.
- `omiGlass/` and `desktop/context-for-claude/` were mapped, not fully audited.
- `sdks/react-native/node_modules` and `omiGlass/node_modules` exist locally; confirm they are gitignored.

---

## Appendix — key file index

| Topic | Path |
|---|---|
| Firestore rules | `firestore.rules` |
| Auth / ADMIN_KEY | `backend/utils/other/endpoints.py` |
| BYOK | `backend/utils/byok.py` |
| Encryption | `backend/utils/encryption.py` |
| SSRF | `backend/utils/http_client.py` |
| App webhooks | `backend/utils/app_integrations.py` |
| Dev webhooks | `backend/utils/webhooks.py`, `backend/routers/users.py` |
| MCP OAuth | `backend/database/mcp_oauth.py`, `backend/routers/mcp_sse.py` |
| LLM gateway auth | `backend/llm_gateway/gateway/auth.py` |
| Desktop CORS | `backend/desktop_backend.py` |
| Plugin GitHub IDOR | `plugins/omi-github-app/main.py` |
| Plugin Notion CSRF | `plugins/oauth/client.py` |
| BLE audio GATT | `omi/firmware/omi/src/lib/core/transport.c` |
| macOS BYOK storage | `desktop/macos/Desktop/Sources/APIKeyService.swift` |
| Local agent HTTP | `desktop/macos/Desktop/Sources/LocalAgentAPIServer.swift` |
| Windows CORS shim | `desktop/windows/src/main/index.ts` |
| CI secret ratchet | `.github/scripts/check_deployment_secret_boundary.py` |
| Dead code | `.github/scripts/check_dead_code.py` |
| Parity | `contracts/parity/README.md` |
| Invariants | `product/invariants/README.md` |
| Security policy | `SECURITY.md` |
