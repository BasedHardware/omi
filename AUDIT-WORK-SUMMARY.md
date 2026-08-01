# Security audit — work summary

Branch: `security/transport-and-secrets-hardening`
Base: `upstream/main` @ `6c4d752b2f`
Date: 2026-08-01

This is the process-and-outcome record. The findings themselves, including the ones
deliberately **not** fixed, are in [`SECURITY-AUDIT.md`](./SECURITY-AUDIT.md) — read that
before deploying anything.

---

## 1. What this was

A whole-repo security audit run as two rounds of parallel agents, with the confirmed
findings fixed on one branch. It started as an investigation into why a chat request was
hanging, which surfaced the agent-VM transport, and expanded from there.

**Nothing here originates from a feature PR. All of it is on `main` today.**

### Goal

Keep running audit→fix rounds until a full round produces no new HIGH or CRITICAL findings.
**Not met yet** — round 2 found more than round 1, so the loop is still open. See §7.

---

## 2. Method

Eight parallel agents per round, each given a distinct lens, explicit instructions to report
`file:line` with quoted evidence and a confidence score, and a standing instruction to say
"could not determine" rather than guess. Findings were then fixed by a second fleet of
agents partitioned by file so they could not collide.

| Round | Lenses |
|---|---|
| 1 | desktop transport · backend authz/IDOR · secrets & credentials · data storage & PII · infrastructure & agent VM · local attack surface · mobile & firmware · storage volume for costing |
| 2 | dependencies & modernization · concurrency/races/TOCTOU · billing & business-logic abuse · resource exhaustion · crypto & Windows Electron · web tier & SDKs · fail-open patterns · *(AI tool surface — dropped, hit the concurrency cap)* |

Round 2's lenses were chosen specifically because round 1 never applied them. That is why
round 2 found *more*, not less.

**What agents were told not to do:** never print a full secret value, never output personal
message or mail content, never edit outside their assigned file set, never commit or push.

---

## 3. What changed

```
182 files changed, 4,523 insertions(+), 831 deletions(-)
21 commits
```

| Area | Files |
|---|---|
| `backend/` | 86 |
| `desktop/` | 45 |
| `web/` | 28 |
| `app/` | 8 |
| `plugins/` | 6 |
| `.github/` | 6 |
| other | 3 |

Roughly **80 distinct fixes**: ~35 in round 1, ~45 in round 2.

### Commits

```
e315cb5826  fix(backend)   cross-tenant write, path traversal, unauthenticated webhooks
1c3d390250  fix(backend)   public URLs, logs, and LangSmith content leakage
9448e45e64  fix(agent-vm)  prompt-injection-to-root-shell
71f38e60a3  fix(desktop)   shell injection, path traversal, content logging
7470ba3b5c  fix(mobile)    token leakage to third-party and log surfaces
58224ec641  docs           security audit report and agent-VM cost model
32c884832b  chore          line-count baselines
6b4706ad18  chore(desktop) e2e flow coverage map
ac0b97148d  fix(backend)   pyright on the new admin gate and GCE insert body
87f6d945d3  fix(web)       unauthenticated memory injection and stored XSS
97c6b3f7e3  fix(backend)   unmetered spend and marketplace/billing abuse
d31aa1ec27  fix(backend)   decompression, regex, and request fan-out bounds
3d2231dde5  fix(backend)   make security controls fail closed
7fee4508be  test(backend)  cover the fail-closed and bounds changes
5206107179  fix(desktop)   /tmp write primitive; make retention real
89915df046  fix(deps)      advisories + persistent renderer RCE
d76db9a992  docs           round 2 findings
29f84bf589  chore          ratchet baselines
1f45404095  chore(desktop) e2e flow coverage map
91d434a05c  chore(docs)    regenerate app-client OpenAPI
049f24f423  fix(backend)   bound id lists without breaking the app-client contract
```

---

## 4. Highest-severity findings, fixed

Full detail in `SECURITY-AUDIT.md`. The short list:

**Round 1**

- Agent VM ran Claude with `permission_mode="bypassPermissions"` and full `Bash`, as root,
  over the user's screen-OCR database. Indirect prompt injection was a root shell.
- `update_app`/`update_persona` authorized on the path id and wrote the body id — any app
  owner could rewrite any other developer's app, including its webhook and payment link.
- Chat thumbnails were `make_public()`'d at a uid-derived, guessable URL.
- Account deletion never purged voiceprints or conversation audio. GDPR Art. 17 failure.
- `TaskAgentManager` executed LLM-extracted task text through a double shell.
- The Firebase ID token attached to any URL merely *containing* `api.omi.me`.
- LangSmith received raw chat despite `LANGCHAIN_TRACING_V2=false`.

**Round 2**

- A one-line binding error made the Gemini daily cap unreachable (§5).
- agent-proxy stored "enhanced protection" chat in **plaintext** and relabelled the record
  `'standard'` — the prod chart never supplied `ENCRYPTION_SECRET`, so this was the shipped
  configuration.
- `personas/api/store-facts` was unauthenticated and wrote memories into any account.
- Three unmetered LLM spend paths (§5).
- `/tmp/omi.log` was a symlink-write primitive into any path the user can write.
- Quadratic regexes pinned the backend event loop from one chat message.
- A `429` made the sync client retry *faster* than a `500` did — forever.
- Desktop retention was largely fictional: three retention functions with zero call sites,
  observations that survived the sweep, WAL audio at 30 MB/h that only swept on successful
  upload, and no `VACUUM` anywhere.

---

## 5. Cost

Three different things get conflated in "savings". Separating them:

### 5a. Risk eliminated — worst-case exposure that was live and is now closed

None of this is money already spent. It is what a single abusive account could have
extracted, per day, before these fixes. Whether any of it *was* being extracted is not
determinable from the repo — it needs a look at actual GCP/OpenAI/Gemini billing.

| Path | Before | After | Basis |
|---|---|---|---|
| **Gemini proxy** (`desktop_proxy.py`) | 43,200 req/day/account | 1,500 req/day/account | The 1,500 cap tested `remaining` as if it were `current`, so it never fired. Only the 30/60s burst limit was live. **28.8×** |
| **Realtime relay** (`/v1/omni/relay`) | unbounded concurrent sockets, unbounded duration | 3 concurrent, 30 min max | No quota, no rate policy, no connection cap, no usage recording |
| **Realtime mint** (`/v2/realtime/session`) | unlimited OpenAI secrets, no expiry | quota-gated, expiry set | Secrets were usable directly against OpenAI, bypassing Omi — invisible until the invoice |
| **Sync upload** | ~500 files × 200 MB per request | 50 files | ~900 h of audio ≈ **$230 of STT per request**, repeatable |
| **MCP batch** | 1 rate-limit token → unbounded tool calls | batch ≤ 20, charged per message | ~**100,000×** bypass |
| **`/v1/tools/conversations`** | `limit=5000` → 5,001 Firestore round trips | `limit=200`, photo-free query | Unrate-limited N+1 |

**Illustrative sizing, not a claim.** A single abusive account on the Gemini path at
43,200 req/day × ~10k input tokens ≈ 432M tokens/day. At gemini-2.5-flash input pricing
(~$0.30/M) that is **~$130/day/account**; ten such accounts ≈ **$39k/month**. The realtime
paths are worse per-unit (~$4–6/hour/session at the rates the codebase itself lists) and had
*no* cap at all, so their worst case is bounded only by how many sockets someone opens.

Treat these as risk removed, not invoice reduction. The honest statement is: **if nobody was
abusing these, the saving is $0 and the value was insurance; if anyone was, it was five to
six figures a month and would not have shown up as anything but "our model spend grew."**

### 5b. Revenue leakage closed

- **Paid-app entitlement was never revoked** on refund, chargeback, or cancellation — a
  30-day Redis key with no expiry path. Subscribe → enable → dispute → keep access. It also
  failed the other way: legitimate annual subscribers lost access on day 31.
- **Client picked its own Stripe `price_id`** with no membership check, and `LEGACY_PRICE_MAP`
  accepted retired prices — subscribe at the old $19.99 tier, receive current entitlements.
- **Stripe checkout minted a random idempotency key per call**, so a double-tap produced two
  live subscriptions, and cancellation only cancelled the one Firestore knew about.
- **Install counts and ratings were inflatable**, and both drive marketplace ranking — which
  drives paid-app revenue.

Not quantifiable without billing data. All four are now closed.

### 5c. Opportunity — the architecture, NOT yet changed

This is the large number, and none of it is realized on this branch.

The per-user agent VM is an `e2e-small` with a **50 GB `pd-balanced`** boot disk. It
self-stops after 30 min idle, so vCPU and IP are usage-proportional. **The disk is not.**
`autoDelete: true` only fires on instance *delete*, and nothing in the product ever deletes
an instance — there is no deprovision route, and the reaper CronJob ships `DRY_RUN=true`.

At 300,000 users, us-central1 list price, assuming 30% DAU at ~3h/day:

| | Monthly |
|---|---|
| 50 GB pd-balanced × 300k, billed forever | **$1,500,000** |
| e2-small compute | ~$100,000 |
| External IP while attached | ~$30,000 |
| **Total** | **~$1.63M/month** |

**92% of that is idle disk**, held for users who may have opened the app once.

Cloudflare R2 equivalent — storage only, with the write path batched:

| | Monthly |
|---|---|
| Storage, ~1 GB/user avg @ $0.015/GB | $4,500 |
| Class A writes, batched to ~1 object/min while active | ~$14,500 |
| Class B reads | <$500 |
| Egress (R2 charges none) | $0 |
| **Total** | **~$20,000/month** |

**≈ $1.6M/month, ~99%.**

Three conditions on that number:

1. **Do not lift the sync cadence as-is.** `AgentSyncService` syncs every **3 seconds** —
   ~10k–30k writes per active user per day. Mapped naively to R2 Class A operations at 300k
   users that is ~180 billion ops/month, **~$810M**. The write path must be batched first.
   This single detail is the difference between a 99% saving and a catastrophe.
2. **R2 replaces storage, not compute.** The VM also runs the Claude agent, a headless
   Playwright browser, and SQL. That has to consolidate into shared multi-tenant workers
   separately — that is where the remaining ~$130k lives.
3. **SQLite-on-object-storage is a poor fit for the read path.** `semantic_search`
   full-scans the embedding column and computes cosine similarity in Python; on R2 that is a
   whole-object read per query. The realistic target is a shared vector store plus Postgres.

**Two changes that need no architecture work at all:**

- **Turn the reaper live.** It ships `DRY_RUN=true` with no CD path. This alone reclaims
  most of the disk spend.
- **Change one integer.** `"diskSizeGb": "50"` is hardcoded for a database estimated at
  1–4 GB. Dropping to 10 GB cuts the largest line item by 80% — $1.5M → $300k — with a
  roughly one-character diff.

At the current bill (~$9.4k/month per the GCP console), the same two changes are the
cheapest thing on this list to try and the easiest to measure.

**Weakest input:** per-user DB size (assumed 1 GB average). Worth measuring on a real
install before committing to a plan. There is no pruning for `transcription_segments` or
`observations` server-side and no `VACUUM`, so the file only ratchets up to its high-water
mark.

### 5d. Not costed

GDPR Art. 17 exposure from account deletion never purging voiceprints and conversation
audio, and the reputational/regulatory exposure of an unauthenticated always-on microphone
on shipped hardware. Both are real and neither is estimable from here.

---

## 6. Deviations worth knowing about

- **Dropped `firebase-admin`** from the personas fix rather than regenerate an npm lockfile.
  The project's Bun-only rule and that app's npm-based CI collide. Replaced with a
  zero-dependency WebCrypto RS256 verifier against Google's JWKS, tested against a 19-case
  matrix (wrong issuer, wrong audience, expired, `alg:none`, tampered payload, unknown kid,
  and a token signed by a different key claiming a known kid — all rejected).
- **Moved three list caps out of the Pydantic schemas into validators.** Adding `maxItems`
  to a released contract is a breaking change and the repo's own gate blocks it. Same
  limits, same rejection, unchanged published schema. A *declared* limit properly belongs on
  a versioned endpoint — this is a compromise, and it is noted in the code.
- **Reverted a `firestore.rules` cleanup.** Removing two dead helper functions was correct
  but broke a source-text tripwire test. Cosmetic, LOW, not worth the churn.
- **Tagged fix commits `Failure-Class: none`** rather than registering a new class.
  "Authorization proven on one identifier, mutation applied to another" appeared twice in
  `apps.py` and is a genuine recurring class worth registering — left to whoever owns the
  registry.

---

## 7. Still open

### Needs a decision, not a patch

1. **The wearable is an unauthenticated open microphone.** BLE audio characteristic has no
   encryption requirement; `bt_conn_set_security()` is never called anywhere in the
   firmware. Anyone in range connects with no pairing and receives the live stream. Stored
   SD-card recordings are equally open. omiGlass is worse — unauthenticated BLE writes set
   the WiFi credentials *and* the OTA firmware URL. Fixing this breaks every paired device
   and needs a rollout plan. **This is the most serious finding in the audit.**
2. **The firmware signing key is committed** (`root-rsa-2048.pem`) and CI's own README says
   it is the key releases are signed with. Rotation needs a staged bootloader update.
3. **Agent-VM traffic is cleartext HTTP** with the token in the query string. Needs TLS on
   the VM listener or removal of the external IP — no client-only fix exists.
4. **A single org-wide Anthropic key sits on every user's internet-facing VM.**
5. **`resolveAcpPermission` auto-approves with `allow_always`** — documented as intentional,
   so it is a product call.

### Rotate now

- Every **Notion token** that passed through `plugins/oauth/conversation_created.py` — it
  printed live, non-expiring tokens to stdout on every integration setup.
- The **Hive API key** — printed raw on every REST call.
- **`OPENAI_API_KEY` and `GOOGLE_CLIENT_SECRET`** if any published mobile build carried
  them (CI injects both, contradicting the repo's own `client_env_policy.yaml`).

### Needs its own PR

- **`websockets` 12 → 15.** Blocks the `langsmith` CVE fix. Note
  `backend/openapi-requirements.txt` already pins an unsatisfiable langsmith+websockets
  combination that only survives because it has no solver-verified lock.
- **Electron 39.8.10** — EOL since 2026-05-05, four majors behind, so every Chromium CVE
  since then is permanently unpatched in a shipped app. Native-ABI migration.
- **Starlette 0.49.3 → 1.3.1** — CVE-2026-54283 is reachable at the unauthenticated
  `/token` endpoint. Needs a coordinated FastAPI bump.

### Round 3, not yet run

The **AI/agent tool-surface lens** hit the concurrency cap and never ran: a complete
inventory of every tool exposed to a model, which are destructive or exfiltrating without
confirmation, and what a malicious marketplace app can do to an installing user. Given that
`resolveAcpPermission` auto-approves everything, this is a real gap.

Also carried forward: `RewindSettings` is still unsynchronized (the password-manager
screenshot-exclusion gate — making it `@MainActor` cascades into ~15 files across four
subsystems); screen OCR is still unencrypted in Firestore while everything else is; mobile
still has no secure storage and no certificate pinning.

---

## 8. Verification

| Check | Result |
|---|---|
| `swift build` | clean |
| SwiftLint | 0 violations, 977 files |
| swift-format | clean |
| pyright | clean |
| black / dart format | clean |
| Backend unit tests | 802/812 file-isolated pass; the 10 failures reproduce with these changes stashed |
| Windows vitest | 5,126 passed, 0 failed |
| web admin / personas / frontend | typecheck + tests pass |
| OpenAPI contract | regenerated, no breaking change |
| Full `pr-preflight` | pass |

**Measured, not assumed:** the two regex DoS fixes — `web_tools` 7.4s → 0.18s at 140 KB,
`notification_text` 21s → 0.000s at 100 KB.

**Not verified:** `swift test` is broken in this workspace (Sparkle `dlopen`, pre-existing);
the agent-VM Docker image was never built; `permission_mode="default"` was never exercised
against a live VM; no live Firebase token exercised the new personas verifier; whether the
agent VM's port 8080 is open to `0.0.0.0/0` needs checking in GCP, not the repo.

---

## 9. Deploy ordering

These will break things if rolled out carelessly. Full list in `SECURITY-AUDIT.md` §3 and §5.8.

1. **`AGENT_VM_ENABLED=true` must be set** before this deploys, or agent VM provisioning
   goes dark for everyone.
2. **`ENCRYPTION_SECRET` must exist in `prod-omi-backend-secrets`** before the agent-proxy
   chart is applied — agent-proxy now raises at import rather than silently writing
   plaintext, so a missing value is a CrashLoopBackOff.
3. **`ADMIN_KEY` must be non-empty** in every environment, or all admin routes — including
   desktop release publishing — now 403.
4. **The VM name change orphans currently-provisioned VMs.** No migration was written.
5. **`shieldedInstanceConfig` requires a UEFI-enabled source image**, or `instances.insert`
   fails outright.
6. **`enable-oslogin` + `block-project-ssh-keys` lock out project-wide SSH keys.**
7. **The agent VM image must be rebuilt** before `startup.sh` rolls out.
8. **Android LAN cleartext** — the new network security config covers loopback only, so
   self-hosted STT over plain HTTP to a `192.168.x.x` host will break. Product call.
9. **Desktop retention now actually deletes**, so historical derived data disappears on
   first run after upgrade, and existing databases get a one-time full `VACUUM`.
10. **Capture stops below 2 GB free** instead of filling the disk.
