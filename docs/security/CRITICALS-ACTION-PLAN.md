# CRITICALs Action Plan — Human Decisions Required

**Branch:** `docs/security-criticals-action-plan` (from `arch/local-first-agent`)
**Audit source:** `HANDOFF.md` Part A2, cross-checked against `origin/security/transport-and-secrets-hardening`
**Date:** 2026-08-01

This document covers the six CRITICAL findings that still need a human decision or operational action after the security hardening branch. It also lists secret rotation items and deploy-ordering prerequisites from the audit.

---

## Executive summary

| # | Finding | Security branch status | Blocker type |
|---|---------|------------------------|--------------|
| 1 | Unauthenticated BLE microphone | Partial code fix; not compiled, not hardware-tested; unpair blocker | Product + firmware rollout |
| 2 | Committed firmware signing key | Not fixed | Key rotation + CI redesign |
| 3 | Agent-VM cleartext HTTP | Not fixed (VM hardening only) | Infra architecture |
| 4 | Org-wide Anthropic key on every VM | Not fixed | Secrets architecture |
| 5 | ACP auto-approve (`allow_always`) | Not fixed (intentional) | Product decision |
| 6 | `fetch_url_tool` exfiltration mandate | Partially fixed (prompt scoping) | Code + product review |

The security branch (`origin/security/transport-and-secrets-hardening`, ~80 fixes across 4 rounds) addresses many other CRITICALs but leaves these six unchanged or only partially mitigated. Round 4 also introduced new findings — a round 5 self-review is warranted before merge.

---

## 1. Unauthenticated BLE microphone (+ unpair blocker)

### Current state (`arch/local-first-agent`)

- **Firmware:** `omi/firmware/omi/src/lib/core/transport.c:144-152` — audio characteristic uses plain `BT_GATT_PERM_READ`; no `bt_conn_set_security()` anywhere in the tree.
- **Storage service:** equally open (`storage.c:79-96`).
- **SMP configured but unused:** `CONFIG_BT_SMP=y` in `omi.conf`, but bonds do not persist (`CONFIG_BT_SETTINGS` absent) and security is never requested on connect.
- **Pairing slot limit:** `CONFIG_BT_MAX_PAIRED=1` in `omi/omi.conf:113` — first phone to pair owns the device permanently.
- **No unpair path:** `bt_unpair` — zero hits in firmware; `DeviceConnection.unpair()` in Flutter is a no-op for Omi (`device_connection.dart:236`).
- **Android bonding gap:** `needsBond` is set only for `DeviceType.limitless` (`device_connection.dart:112`); Omi devices get `requiresBond: false`, so encrypted characteristics would fail silently on Android after a firmware fix.
- **omiGlass:** worse — unauthenticated BLE writes set WiFi credentials and OTA URL (`omiGlass/firmware/src/ota.cpp:99-118`). **No fix on the security branch.**
- **MCUmgr BLE auth:** `CONFIG_MCUMGR_TRANSPORT_BT_AUTHEN` does not appear anywhere; verify default in pinned NCS version — unauthenticated DFU over BLE may be a second CRITICAL.

### What's on `security/transport-and-secrets-hardening`

Commit `df14d5ed9e` (round 4) adds a partial fix behind `CONFIG_OMI_REQUIRE_BLE_ENCRYPTION` (default `y`):

| Change | File |
|--------|------|
| `ble_perm.h` — `OMI_GATT_PERM_READ/WRITE/CCC` resolve to `_ENCRYPT` variants when enabled | `omi/firmware/omi/src/lib/core/ble_perm.h` |
| Audio, storage, settings, time-sync, speaker characteristics switched to encrypted permissions | `transport.c`, `storage.c`, `devkit/src/transport.c` |
| `bt_conn_set_security(conn, BT_SECURITY_L2)` on connect | `transport.c` (link-security section) |
| Bond persistence: `CONFIG_BT_BONDABLE=y`, `CONFIG_BT_SETTINGS=y`, `CONFIG_BT_SMP_SC_PAIR_ONLY=y` | `omi/omi.conf` |
| Address privacy: `CONFIG_BT_PRIVACY=y` | `omi/omi.conf` |
| Speaker write bounds | `transport.c` |

**Not addressed:**

- No bond-clear / unpair mechanism (long-press, factory reset, or GATT command).
- Android `needsBond` not extended to `DeviceType.omi`.
- omiGlass firmware untouched.
- Never compiled (no NCS toolchain in audit environment) and never exercised against hardware.
- Breaking change: every field device will prompt to pair once; users replacing phones hit the `CONFIG_BT_MAX_PAIRED=1` brick.

### Fixable in code vs needs human decision

| Action | Owner |
|--------|-------|
| Merge BLE encryption changes from security branch | Engineering |
| Add user-facing unpair path (long-press, settings command, or factory-reset flow) | Product + firmware |
| Extend Android/iOS bonding for Omi device type | Mobile |
| Decide `CONFIG_BT_MAX_PAIRED` policy (1 vs N, phone-replacement UX) | Product |
| omiGlass BLE auth + WiFi/OTA credential protection | Product + firmware (separate device) |
| Verify `CONFIG_MCUMGR_TRANSPORT_BT_AUTHEN` default; enable if off | Firmware + security |
| Firmware rollout plan (staged OTA, comms to users, support runbook) | Product + ops |
| Hardware validation on real devices (pair, reconnect, phone swap, Android) | QA + hardware |

### Recommended action

1. **Do not ship BLE encryption without an unpair path.** The security branch fix plus `CONFIG_BT_MAX_PAIRED=1` and no bond-clear is a support brick for phone upgrades.
2. **Design unpair first**, then merge encryption. Minimum: long-press unpair or explicit "Forget device" that clears bonds on firmware and instructs user to forget in OS Bluetooth settings.
3. **Extend mobile clients before firmware rollout:** set `requiresBond: true` for `DeviceType.omi` on Android; verify iOS/macOS native BLE layer initiates pairing when ATT returns "Insufficient Authentication".
4. **Schedule hardware QA** with NCS toolchain before any DFU release.
5. **Scope omiGlass separately** — it has a distinct codebase and higher severity (WiFi + OTA takeover).
6. **Check MCUmgr BLE authentication** in the pinned NCS version immediately.

---

## 2. Committed firmware signing key

### Current state

- Private key committed at `omi/firmware/bootloader/mcuboot/root-rsa-2048.pem`.
- CI README (`omi/firmware/scripts/ci/README.md`) states this is the key releases are signed with.
- Public half burned into every shipped bootloader — anyone with repo access can produce validly signed DFU images.
- `enc-rsa2048-priv.pem` also committed; appears unused but should be audited.
- Security branch adds `*.pem` to `.gitignore` but **does not remove the key from history or rotate**.

### Fixable in code vs needs human decision

| Action | Owner |
|--------|-------|
| Remove key from repo; inject via CI secret / HSM | Security + CI |
| Rotate signing key with staged bootloader update (new key signed by old key) | Firmware + ops |
| Audit all shipped bootloaders for which public key is embedded | Firmware |
| Revoke/audit any third-party builds signed with the compromised key | Security |
| Decide whether to force-OTA all devices to new trust anchor | Product + ops |

### Recommended action

1. **Treat the key as compromised** — assume anyone who cloned the repo can sign firmware.
2. **Generate new key pair** stored only in CI secrets (GCP Secret Manager, GitHub encrypted secret, or HSM).
3. **Stage rotation:** ship a bootloader update signed with the *old* key that installs the new public key as trust anchor; only then begin signing application images with the new private key.
4. **Remove `root-rsa-2048.pem` from the repo** and scrub from git history (BFG or filter-repo) — coordinate with all fork consumers.
5. **Audit `enc-rsa2048-priv.pem`** — remove or rotate if ever used.

---

## 3. Agent-VM cleartext HTTP transport

### Current state

Desktop client dials the VM's public GCE IP directly over plain HTTP:

| Endpoint | Data exposed | File |
|----------|--------------|------|
| `http://<vmIP>:8080/upload?token=<token>` | Full gzipped `omi.db` (screen OCR, transcripts, memories) | `AgentVMService.swift:247` |
| `http://<vmIP>:8080/auth?token=<token>` | Firebase ID token in POST body | `AgentSyncService.swift:424`, `AgentVMService.swift:302` |
| `http://<vmIP>:8080/sync?token=<token>` | Incremental DB rows, base64-encoded | `AgentSyncService.swift:651` |
| `ws://<vmIP>:8080/ws?token=<token>` | Full agent conversation | `agent-proxy/main.py:682` |
| `http://<vmIP>:8080/health` | **Unauthenticated** — response trusted by client | `AgentSyncService.swift:378` |

Additional compounding issues:

- Token in query string → logged in GCE access logs, proxy logs, browser history.
- `NSAllowsArbitraryLoads: true` in `desktop/macos/Desktop/Info.plist:33` disables ATS app-wide.
- No firewall rule for tag `omi-agent-vm` in repo IaC — **verify in GCP whether 8080 is `0.0.0.0/0`**.
- VMs on default network inherit `default-allow-ssh` from `0.0.0.0/0`.
- Forging `{"databaseReady": false}` on `/health` triggers full DB re-upload (exfiltration amplifier).

### What's on `security/transport-and-secrets-hardening`

VM-side hardening only — **no TLS, no transport architecture change:**

- Container runs as uid 10001, `--cap-drop=ALL`, `--security-opt no-new-privileges` (`startup.sh`, `Dockerfile`).
- VM provisioning: shielded instance config, OS Login, SSH key block, SHA-256 VM names (`desktop_agent_vm.py`).
- Agent tool surface reduced (`permission_mode="default"`, MCP-only tools) — reduces blast radius of a MitM but does not encrypt transit.
- Sync client improvements: poison-batch breaker, Retry-After handling (`AgentSyncService.swift`).

**Cleartext HTTP remains in all client and proxy paths.**

### Fixable in code vs needs human decision

| Action | Owner |
|--------|-------|
| Terminate TLS on VM listener (Let's Encrypt, GCP-managed cert, or mTLS) | Infra |
| Route traffic through existing `agent.omi.me` ingress instead of direct IP | Infra + backend |
| Remove `NSAllowsArbitraryLoads`; pin to HTTPS endpoints only | Desktop |
| Move auth token from query string to `Authorization` header | Desktop + agent_vm |
| Authenticate `/health` or stop trusting unauthenticated health responses | Desktop + agent_vm |
| GCP firewall: restrict 8080 or eliminate public IP entirely | Infra |
| Verify current GCP firewall rules for `omi-agent-vm` tag | Infra (immediate) |

### Recommended action

1. **Immediate:** Verify GCP firewall — if 8080 is `0.0.0.0/0`, treat as active exposure and restrict or add TLS before any other agent-VM work.
2. **Architecture decision (pick one):**
   - **Option A:** Route all VM traffic through `agent.omi.me` (existing ingress + TLS); VMs have no public IP.
   - **Option B:** Per-VM TLS with cert provisioning at startup (complex, but keeps direct-dial model).
3. **Regardless of option:** move tokens out of query strings; authenticate `/health` or remove trust in its response.
4. **Delete `NSAppTransportSecurity` exception** once all agent-VM URLs are HTTPS — every other base URL in the app is already HTTPS.
5. No client-only fix exists; do not attempt to "fix" this with obfuscation or token rotation alone.

---

## 4. Org-wide Anthropic key on every user's internet-facing VM

### Current state

`backend/agent_vm/startup.sh:6-7`:

```bash
anthropic_api_key="$(gcloud secrets versions access latest --secret=DESKTOP_ANTHROPIC_API_KEY)"
gemini_api_key="$(gcloud secrets versions access latest --secret=GEMINI_API_KEY)"
```

Both keys are injected into every user's internet-facing VM container. Compromising one VM yields production billing credentials for the entire org. Revocation is all-or-nothing.

### What's on `security/transport-and-secrets-hardening`

- Container hardening reduces VM compromise likelihood (non-root, cap-drop).
- Agent tool surface reduced — fewer paths from prompt injection to key exfil, but keys still on disk in container env.
- **`startup.sh` still pulls the same org-wide secrets.** No per-VM or per-user key model.

### Fixable in code vs needs human decision

| Action | Owner |
|--------|-------|
| Route agent-VM inference through existing LLM gateway (`backend/routers/desktop_proxy.py`) | Backend + infra |
| Mint per-VM API keys with spend caps (Anthropic admin API, GCP billing alerts) | Security + finance |
| Use workload identity / short-lived tokens instead of long-lived keys in env | Infra |
| Decide acceptable spend per user / per VM | Product + finance |

### Recommended action

1. **Short term:** Ensure VM compromise paths are closed (items 3 and 5 above) before addressing key architecture — defense in depth.
2. **Medium term:** Route agent-VM model calls through the backend LLM gateway (already has rate limits and metering from round 1 fixes) instead of embedding raw keys on the VM.
3. **If direct provider access is required:** mint per-VM keys with individual spend caps and audit logging; store in Secret Manager keyed by VM name, not a shared secret.
4. **Set billing alerts** on Anthropic and Gemini accounts immediately as a stopgap.

---

## 5. ACP permission requests auto-approve

### Current state

`desktop/macos/agent/src/runtime/desktop-tool-policy.ts:304-312`:

```typescript
export function resolveAcpPermission(...) {
  const selected =
    input.options.find((option) => option.kind === "allow_always") ??
    input.options.find((option) => option.kind === "allow_once") ??
    ...
```

Every `session/request_permission` from the production ACP adapter is resolved with `allow_always` — no confirmation gate. This grants the child agent `Read`/`Write`/`Edit`/`Bash` on any absolute path in an unsandboxed process with Full Disk Access.

Documented as intentional at `omi-tool-manifest.ts:1064-1070` (`desktop_high_trust` policy; `capture_screen` depends on auto-approved `Read`).

**Contrast:** `resolveExternalAcpPermission` (same file, `:335-360`) is restrictive — prefers `allow_once`, rejects `allow_always`, fails closed if no non-permanent option exists. External adapters get a confirmation gate; the production desktop adapter does not.

**Security branch:** No changes to `desktop-tool-policy.ts`.

### Product decision needed

This is not an oversight — it is an explicit trust model. The decision is:

| Option | Tradeoff |
|--------|----------|
| **Keep `desktop_high_trust`** (status quo) | Best UX for a local-first agent with Full Disk Access; prompt injection from screen OCR, email, or web content can reach a shell without user confirmation |
| **Switch to `allow_once` default** | User confirms each permission scope; significant friction for multi-step agent tasks |
| **Scope-based auto-approve** | Auto-approve `Read` on agent workspace paths; require confirmation for `Bash`, `Write` outside workspace, network tools |
| **Per-tool policy in manifest** | High-trust for `capture_screen` + `Read`; constrained for `Bash`/`Write`/`Edit` — matches the external adapter pattern |
| **Disable ACP child agent entirely** | Eliminates the surface; may break core desktop agent workflows |

### Recommended action

1. **Product owner must sign off** on the trust model in writing before the security branch merges.
2. If keeping auto-approve: document the accepted risk in release notes and ensure other injection surfaces (fetch_url, agent-VM, screen sync) are closed first.
3. If changing policy: start with `resolveExternalAcpPermission`'s pattern as a template — it already implements the restrictive model.
4. Consider scoped auto-approve as a middle ground: the manifest already tags tools with `runtimePreconditions` and `intendedForAgents` — use these to drive policy per tool category.

---

## 6. `fetch_url_tool` mandated exfiltration channel

### Current state (`arch/local-first-agent`)

`backend/utils/retrieval/agentic.py:867-873` — system prompt instructs the model:

> When the user shares any URL ... you **MUST** call fetch_url_tool ... Always attempt to fetch it first.

This applies to URLs anywhere in context, including those arriving inside untrusted tool results (e.g. `get_memories_tool` output, email bodies, screen OCR). Combined with the tool running server-side with SSRF guards but no origin scoping, a malicious URL embedded in retrieved data can exfiltrate context via path/query injection.

Existing SSRF guards in `web_tools.py` block private IPs and limit body size — these prevent internal network scanning but **do not prevent outbound exfil to attacker-controlled public URLs**.

### What's on `security/transport-and-secrets-hardening`

Three-layer mitigation (commit `df14d5ed9e` / round 4):

| Layer | Mechanism | File |
|-------|-----------|------|
| **Prompt scoping** | Static `AGENT_SAFETY_INSTRUCTIONS`: fetch only URLs user typed this turn; forbid fetch from retrieved data | `agentic.py` |
| **Per-turn allowlist** | `_extract_user_turn_urls()` + `<user_provided_urls>` block injected into latest user turn | `agentic.py` |
| **Untrusted output wrapping** | All non-trusted tool results wrapped in `<untrusted_tool_output>` delimiters with injection neutralization | `tool_result_boundaries.py` |
| **Tool docstring** | Updated to reinforce scoping rules | `web_tools.py` |
| **Tests** | `test_untrusted_tool_result_boundary.py` — delimiter injection, deny-by-default for unknown tools | `backend/tests/unit/` |

### Is the scoping fix sufficient?

**Partially — not sufficient alone.**

| Mitigated | Not mitigated |
|-----------|---------------|
| Clear prompt instructions distinguish user URLs from retrieved URLs | No **runtime** allowlist enforcement — model can still call `fetch_url_tool(attacker_url)` regardless of prompt |
| Untrusted wrapping makes injection harder (tag breakout neutralized) | Determined model ignoring instructions (jailbreak / instruction-following failure) |
| Per-turn allowlist gives model explicit list of permitted URLs | User-typed URL in same turn as attacker payload in retrieved data — model may fetch user URL then append exfil data (prompt says "never append retrieved data" but this is not enforced) |
| SSRF guards prevent internal network access | Public attacker URL exfil still works if model complies with malicious instruction inside untrusted block |

**Verdict:** The security branch fix is a meaningful defense-in-depth improvement and should be merged, but it is **prompt-layer only**. A model that ignores instructions or a jailbreak inside untrusted content can still exfiltrate. For CRITICAL closure, add runtime enforcement.

### Fixable in code vs needs human decision

| Action | Owner | Type |
|--------|-------|------|
| Merge prompt scoping + untrusted wrapping from security branch | Engineering | Code (ready) |
| Add runtime allowlist: reject `fetch_url_tool` calls where URL ∉ `_extract_user_turn_urls()` for current turn | Engineering | Code (recommended) |
| Store per-turn allowlist in `agent_config_context` for tool-level check | Engineering | Code |
| Decide whether user can override ("fetch this link from my email") | Product | Decision |
| Add integration test: memory containing attacker URL → assert fetch blocked at runtime | Engineering | Code |

### Recommended action

1. **Merge the security branch scoping changes** — they are correct and tested for the wrapping layer.
2. **Add runtime allowlist enforcement** in `fetch_url_tool` or the tool dispatch path in `agentic.py`:
   - Read allowed URLs from `agent_config_context` (populated by `_extract_user_turn_urls` at turn start).
   - Return error if requested URL not in allowlist, regardless of model behavior.
3. **Optional product escape hatch:** if user explicitly says "fetch the URL from that email," require the URL to appear in the user's message text (already covered by allowlist extraction).
4. **Do not mark this CRITICAL closed until runtime enforcement ships.**

---

## Secret rotation list

These secrets were exposed by code paths fixed on the security branch. **Rotation is required even after the logging fixes merge** — assume any secret that passed through the vulnerable code is compromised.

| Secret | Exposure vector | Fixed on security branch? | Action |
|--------|-----------------|---------------------------|--------|
| **Notion access tokens** | Printed to stdout on every integration setup (`plugins/oauth/conversation_created.py`) | Yes (logging removed) | **Rotate every token that passed through this path.** Notify affected users to reconnect Notion. |
| **Hive API key** | Printed on every REST call (`plugins/omi-hive-app`) | Yes (logging removed) | **Rotate the Hive API key.** |
| **`OPENAI_API_KEY`** (mobile) | Compiled into IPA/APK via `codemagic.yaml` → `prod_env.dart`; XOR obfuscation recoverable in minutes | **No** — still compiled by CI | **Rotate if any published App Store / Play Store build carried it.** Audit `app/config/client_env_policy.yaml` (lists both under `server_secret_env.denied_exact`). |
| **`GOOGLE_CLIENT_SECRET`** (mobile) | Same CI injection path | **No** | **Rotate if any published mobile build carried it.** |

Additional rotation triggers from the broader audit (not Part A2 but related):

- Any **`ADMIN_KEY`** that was ever empty in prod (empty header authenticated before fail-closed fix).
- **`ENCRYPTION_SECRET`** if agent-proxy ever ran without it in prod (plaintext chat storage — fixed on security branch but data may already be exposed).

---

## Deploy ordering checklist

These six items from `HANDOFF.md` Part A2 **will break production or strand resources if ignored** when merging the security branch. Complete in order.

### Pre-deploy (before merging security branch)

- [ ] **1. Set `AGENT_VM_ENABLED=true`** in prod backend env. Without it, `_agent_disabled()` returns true and `/v2/agent/provision` → 503. Agent VMs go dark for everyone. This is intentional fail-closed but is a hard behaviour change on deploy.

- [ ] **2. Ensure `ENCRYPTION_SECRET` exists in `prod-omi-backend-secrets`.** agent-proxy now raises at import if missing/short — CrashLoopBackOff instead of silent plaintext writes. The pusher chart reads the same key from the same secret. Verify length ≥ 32 bytes.

- [ ] **3. Ensure `ADMIN_KEY` is non-empty** in every environment. Fail-closed fix: empty `ADMIN_KEY` + empty header no longer authenticates, but all admin routes (including `POST /v2/desktop/releases`) now 403 if unset.

- [ ] **4. Sign off on `ADMIN_KEY_AUTH_ENABLED`.** Default is `true` (preserves existing impersonation via `ADMIN_KEY` prefix + uid). Setting `false` disables a live impersonation mechanism in prod. Operator must explicitly decide: keep enabled (with ≥16 char key and audit logging) or disable.

- [ ] **5. Verify UEFI compatibility** of the `omi-agent` source image. `shieldedInstanceConfig` (Secure Boot, vTPM, integrity monitoring) requires a UEFI-enabled image or `instances.insert` fails outright.

- [ ] **6. Plan VM name migration.** VM names changed from `omi-agent-{uid[:12].lower()}` to `omi-agent-{sha256(uid)[:32]}`. Existing Firestore records keep working, but re-provisioned users get new instances; old VMs become unreferenced billable orphans. **No migration was written.** Choose: drain-and-rename, accept-plus-sweep, or feature-flag the new naming.

### Additional deploy items (from `SECURITY-AUDIT.md` §3 — not in HANDOFF's six but will also break things)

- [ ] **7. Rebuild agent VM Docker image** before rolling out new `startup.sh` — data volume path changed from `/root/omi-agent` to `/home/omi/omi-agent`; old image + new script = empty database.
- [ ] **8. Configure `AGENT_VM_SERVICE_ACCOUNT`** with `secretmanager.secretAccessor` on named secrets and `compute.instances.stop` scoped to agent VMs.
- [ ] **9. OS Login:** `enable-oslogin` + `block-project-ssh-keys` lock out project-wide SSH keys — ops team needs `roles/compute.osLogin`.
- [ ] **10. Android LAN cleartext:** new network security config covers loopback only; self-hosted STT over `192.168.x.x` HTTP will break. Product decision required.
- [ ] **11. Agent tool surface change:** VM agent loses `Bash`/`Read`/`Write`/`Edit`/`Glob`/`Grep`/`WebFetch` — verify MCP tools still work in one manual session before deploy.

---

## Security branch merge guidance

When merging `origin/security/transport-and-secrets-hardening`:

| Merge as-is | Merge + follow-up required | Do not merge without decision |
|-------------|---------------------------|-------------------------------|
| fetch_url prompt scoping + untrusted wrapping | BLE encryption (needs unpair + mobile bonding + HW test) | ACP auto-approve policy |
| Agent VM container hardening | fetch_url runtime allowlist | Cleartext HTTP transport |
| VM provisioning hardening (shielded, OS Login) | Firmware signing key rotation | Org-wide Anthropic key architecture |
| ~70 other fixes from rounds 1-4 | VM name orphan migration | omiGlass BLE |

**Recommended merge sequence:**

1. Complete deploy-ordering checklist items 1-6.
2. Merge security branch.
3. Immediately rotate Notion, Hive, and (if applicable) mobile secrets.
4. Schedule round 5 self-review over the merged diff.
5. Execute the six CRITICAL action items above in priority order: BLE (with unpair) → signing key rotation → TLS transport → key architecture → ACP decision → fetch_url runtime enforcement.

---

## References

- `HANDOFF.md` — Part A (all CRITICALs), Part A2 (human-needed items)
- `origin/security/transport-and-secrets-hardening:SECURITY-AUDIT.md` — full audit report
- `origin/security/transport-and-secrets-hardening:AUDIT-WORK-SUMMARY.md` — cost analysis and round summaries
- Key commits on security branch:
  - `df14d5ed9e` — round 4: BLE encryption, tool consent, memory safety
  - `9448e45e64` — agent-VM prompt-injection-to-root-shell fix
  - `87b2007891` / `b210e7a7ab` — auth, SSRF, CSRF hardening
