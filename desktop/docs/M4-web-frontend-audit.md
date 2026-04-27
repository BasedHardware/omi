# M4 Web Frontend Audit — Regolo Integration

**Branch:** `worktree-omi-regolo-integration` (omi monorepo, alongside the M3 desktop work).
**Decision:** Audit-only pass. M4 is the largest M-series lift (~700 LOC + a new dependency + Firestore schema). Sequencing matters more than speed; this doc plans the order before any code lands.

## Current state — confirmed by file-level inspection

`web/frontend/` is a Next.js (App Router) application with shadcn/ui + Radix primitives + Tailwind. Stack pieces relevant to M4:

| Stack piece | Status | M4 impact |
|---|---|---|
| Next.js App Router | ✅ in use (`src/app/`) | host for `/settings` route |
| shadcn/ui CLI configured | ✅ `components.json` present | scaffold new components via CLI |
| UI primitives | ✅ `accordion`, `button`, `card`, `dialog`, `drawer`, `input`, `label`, `progress`, `scroll-area` | enough to build a Settings page |
| Firebase SDK v11 | ✅ `firebase: ^11.8.1` in deps | Firestore reads/writes for user prefs |
| Tailwind | ✅ `tailwind.config.ts` | layout + theme |
| Toast / notification lib | ❌ **NOT installed** — no `sonner`, no `react-hot-toast`, no `@radix-ui/react-toast` | M4.5 must add `sonner` (~5KB, Tailwind-friendly) |
| Settings route | ❌ **does not exist** under `src/app/` | M4.2 creates from scratch |
| API-key management UI | ❌ does not exist anywhere | M4.2 ships it |

## AI-related code paths — exhaustive list

Two `api.openai.com` call sites, both in one Server Action:

| File | Line | Mode | Purpose |
|---|---|---|---|
| `src/actions/memories/chat-with-memory.ts` | 89 | `'use server'` Server Action | Initial chat completion |
| `src/actions/memories/chat-with-memory.ts` | 129 | same Server Action | Retry / continuation path |

**Important nuance correction.** Earlier discovery framing called this "OpenAI from the browser." That was imprecise. The file's first line is `'use server';` — this is a Next.js Server Action, executed on the Next.js server, NOT in the browser. The `OPENAI_API_KEY` (`envConfig.OPENAI_API_KEY` at line 19) is server-side env state and never reaches the browser bundle.

The actual M4 concern is therefore **routing**, not **secret exposure**:
- Today: chat-with-memory hits `api.openai.com` directly from the Next.js server, bypassing any backend that could enforce EU Privacy Mode.
- After M4: chat-with-memory must route through omi's backend (which then applies the M1 dispatcher logic — Regolo when Privacy Mode is on, else OpenAI).

## What's missing — exhaustive M4 gap list

| Capability | File / location | Status | Sub-phase |
|---|---|---|---|
| Settings route | `src/app/settings/page.tsx` (NEW) | missing | 4.2 |
| API-key manager UI (5 providers) | inside settings page | missing | 4.2 |
| Privacy Mode toggle | inside settings page | missing | 4.2 |
| Server-side user preferences | `src/lib/firestore/user-settings.ts` (NEW) | missing | 4.3 |
| Firestore schema `users/{uid}/settings` | Firestore | missing | 4.3 |
| Backend-routed chat client | refactor `chat-with-memory.ts` to call omi backend | partial | 4.1 |
| `X-BYOK-*` + `X-Privacy-Mode` header forwarder | `src/lib/api/regolo-forwarder.ts` (NEW) | missing | 4.4 |
| Sonner toast surface | install `sonner` + add `<Toaster />` to root layout | missing | 4.5 |
| `usePrivacyFallbackToast()` hook | `src/hooks/usePrivacyFallbackToast.ts` (NEW) | missing | 4.5 |
| Navbar shield indicator | edit existing nav component | missing | 4.5 |

## Recommended sub-phase order

The Define plan listed phases 4a–4e; I recommend a slight resequencing based on what enables what.

### M4.1 — Server-side preference store (½ day, ~80 LOC)

Why first: every other phase needs to read or write user prefs. Land the schema + the read/write helper, even if no UI consumes it yet.

Files:
- `src/lib/firestore/user-settings.ts` (NEW) — `getUserSettings(uid)`, `updateUserSettings(uid, partial)`. Schema: `{ eu_privacy_mode: bool, byok_keys: { openai, anthropic, gemini, deepgram, regolo: { encrypted: string, hash: string } } }`.
- `src/lib/firestore/encryption.ts` (NEW) — symmetric encryption for BYOK keys at rest using a KMS-derived key (or `NEXT_PUBLIC_*` is **NOT** acceptable here — keys must encrypt server-side only).

Risk: this leaks beyond M4 scope into KMS/key-encryption territory. Coordinate with infra on whether to use Firebase KMS, GCP KMS, or a raw env-var pepper. Decision needed before code lands.

### M4.2 — `/settings` route + API-key manager UI (1.5 days, ~350 LOC)

Files:
- `src/app/settings/page.tsx` (NEW) — server component that reads prefs via M4.1 helper.
- `src/app/settings/sections/api-keys.tsx` (NEW) — 5 rows (OpenAI, Anthropic, Gemini, Deepgram, Regolo), each with masked SecureInput, Save action, Test connection button. Mirrors desktop's `developerKeyField` pattern.
- `src/app/settings/sections/privacy.tsx` (NEW) — EU Privacy Mode toggle, copy mirroring desktop. First-run intro card optional.
- `src/app/settings/actions.ts` (NEW) — Server Actions for save/test-connection.

Test-connection target: backend endpoint `POST /v1/byok/validate` (which already exists per BYOKValidator behavior — desktop hits the same endpoint).

### M4.3 — Backend-routed chat (½ day, ~50 LOC refactor)

Replace direct `api.openai.com` fetch in `chat-with-memory.ts` with a call to omi backend `/v1/chat`. Backend's M1 dispatcher then applies Privacy Mode routing.

This unblocks the entire M4 privacy story: after this lands, web chat is no longer architecturally bypassing Regolo even if the user has Privacy Mode on.

### M4.4 — Header forwarder helper (½ day, ~70 LOC)

`src/lib/api/regolo-forwarder.ts` (NEW). Reads user prefs server-side via M4.1, attaches:
- `Authorization: Bearer <firebase-id-token>`
- `X-BYOK-OpenAI`, `X-BYOK-Anthropic`, etc., for whichever providers the user configured (one per provider; M1 backend already handles per-header BYOK)
- `X-Privacy-Mode: on` when toggle is on

Used by M4.3's chat refactor and any other future backend-routed call.

### M4.5 — Toast + privacy indicator (½ day, ~100 LOC + 1 dep)

- `npm install sonner` — ~5KB, Tailwind-friendly.
- Add `<Toaster />` to `src/app/layout.tsx` root.
- `src/hooks/usePrivacyFallbackToast.ts` (NEW) — reads `X-Privacy-Mode-Fallback` response header from API client wrapper, fires a red toast with the matching reason (mirrors desktop's `PrivacyModeFallbackObserver` 5-reason enum).
- Navbar component edit: shield icon when Privacy Mode is on. Find where the existing nav lives (likely `src/app/components/` or `src/components/`).

## Dependencies that need a decision before code

| Question | Owner | Decide by |
|---|---|---|
| BYOK key encryption-at-rest mechanism (Firebase KMS / GCP KMS / env-var pepper) | Infra + Web | M4.1 start |
| Backend `/v1/chat` endpoint contract — does it accept the same body shape as `chat-with-memory.ts` currently sends to OpenAI, or does it want omi's internal format? | Backend | M4.3 start |
| Whether `/v1/byok/validate` exists today; if not, what desktop's BYOKValidator hits today | Backend | M4.2 start |
| Whether the navbar component is a server or client component (affects how the shield reactively updates) | Web | M4.5 start |

## Estimated total — ~700 LOC + sonner dep + Firestore schema + 1 KMS decision

Calendar: 3 days for one full-stack engineer, or 2 days with one Web + one Backend in parallel after M4.1 lands.

## Decision: ship audit doc, no code

Same rationale as M2 audit: the natural first patch (M4.1 Firestore preferences) requires a KMS decision that isn't in scope for this session. Better to ship the audit + sequencing plan and let an actual M4.1 develop pass kick off after the encryption-at-rest decision is made.

## Files touched

| File | Change |
|---|---|
| `desktop/docs/M4-web-frontend-audit.md` | NEW (this doc) |

No code changes. No test changes. The audit + sub-phase plan is the deliverable.

## Sister-repo applicability

Unlike the M0/M1/M2 docs which the user pushed to the Euraika sister GitLab repo, this audit is entirely about the omi monorepo's `web/frontend/`. The sister repo doesn't currently mirror `web/frontend/` files — when M4.1 starts shipping code, the patch-package strategy needs a decision: extend sister repo with a `web/frontend/` patch tree, or keep web changes monorepo-only and use a different distribution mechanism.

## Cross-references

- M0 spec corrections: `desktop/docs/REGOLO_INTEGRATION.md`
- M0 probe results: `desktop/docs/regolo-probes.md`
- M1 deliver report: `desktop/docs/M1-deliver-report.md` (sister repo only — not in this monorepo branch)
- M2 embedding audit: sister repo `desktop/docs/M2-embedding-audit.md`
- M3 desktop polish: 6 commits on this branch (`947fa97a0`, `c15ebe8f4`, `47fd11a0c`, `6bdff2914`, `47811d004`, `ee7803e2a`)
