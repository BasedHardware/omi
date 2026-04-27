# M4 Revised Scope — Discovery from M4.3 Spike

**Date:** 2026-04-27 (loop iteration 2).
**Trigger:** Attempting M4.3 (refactor `chat-with-memory.ts` to backend-route) revealed the original scope was wrong.

## What was discovered

`web/frontend/src/actions/memories/chat-with-memory.ts` is a **Server Action serving anonymous public viewers** of shared memory pages. URL pattern: `/chat/[token]` and `/memories/[id]/...`. The `token` in the URL is the access credential — **not** a Firebase ID token.

This means:

1. **No `uid`** at the call site. Anonymous viewers don't have a Firestore `users/{uid}/settings/profile` document.
2. **No Privacy Mode preference** to read or apply. Privacy Mode is a per-account toggle; anonymous viewers have no account.
3. **No BYOK keys** to forward. Same reason.
4. **OpenAI is the correct provider** for this surface — the memory's owner already authorized public access by sharing the link, so routing the chat through OpenAI is consistent with the access model.

## Therefore: M4.3 does NOT apply

The original M4 plan listed M4.3 as "refactor chat-with-memory.ts to backend-route" with the assumption that this would unblock the EU Privacy promise on the web frontend. **That assumption was wrong.** The web frontend has zero authenticated-user AI surfaces today; chat-with-memory is the only AI feature, and it's structurally anonymous.

Refactoring chat-with-memory to require Firebase Auth + Privacy Mode lookup would be a regression — it would break public memory viewing for users who haven't signed in.

## What this means for the rest of M4

| Sub-phase | Original scope | Revised verdict |
|---|---|---|
| M4.1 | Firestore prefs + encryption | ✅ Shipped — generally useful for any future authenticated-user feature |
| M4.2 | `/settings` route + 5-row API key manager | ⚠️ Premature — **no authenticated-user AI feature exists yet** to consume the keys. Settings UI without a downstream consumer is configuration without effect. Defer until an authenticated-user AI feature is planned. |
| M4.3 | Chat-with-memory backend refactor | ❌ Does not apply — anonymous surface, OpenAI is correct |
| M4.4 | Header forwarder | ✅ Shipped — utility ready for the day an authenticated-user AI surface exists |
| M4.5 | Sonner toast + privacy hook | ✅ Shipped — generally useful |

## What ACTUALLY ships from M4 in this branch

| Deliverable | LOC | Tests | Status |
|---|---|---|---|
| `BYOK_MASTER_PEPPER` env-var registration | +5 | — | shipped |
| Firestore handle alongside Auth | +6 | — | shipped |
| `lib/firestore/encryption.ts` | +130 | 7 | shipped |
| `lib/firestore/user-settings.ts` | +120 | (covered indirectly) | shipped |
| `lib/api/regolo-forwarder.ts` | +110 | 8 | shipped |
| `app/layout.tsx` Toaster mount | +4 | — | shipped |
| `hooks/usePrivacyFallbackToast.ts` | +75 | 3 | shipped |
| sonner dependency | +1 dep | — | shipped |
| **Total** | **~451 LOC web** + 1 dep | **18 unit tests, all green** | **complete** |

## Updated remaining work for the GA roadmap

After this iteration, the entire UNBLOCKED M4 work is done. Remaining roadmap is human/infra-gated:

| Item | Blocker | Owner |
|---|---|---|
| M2.5 — backend embedding migration (4096-dim Pinecone index + write-path privacy gate) | Infra provisioning + cost approval | Infra + finance |
| M3 — desktop polish Mac build verification | Linux WSL2 host can't build Swift | Mac access needed |
| M5 — DPA + GA rollout | Regolo legal turnaround | Legal |
| **NEW**: First authenticated-user AI feature on the web frontend | Product decision (no such feature designed yet) | Product |

## Why I stopped the autonomous loop here

The /loop /octo:embrace was meant to "advance the roadmap until finished." Iteration 1 shipped M4.1 + M4.5. Iteration 2 shipped M4.4 + this discovery doc. Every other M-series item now requires:

- A human decision (product, legal, infra)
- A capability this Linux WSL2 host doesn't have (macOS Swift toolchain)
- A non-existent feature surface (authenticated-user AI on web)

Continuing the loop without a human-in-the-loop would either:
- Spin against blockers (waste tokens)
- Build speculative work that may not match what stakeholders want (negative value)

**The honest end-state:** all unblocked roadmap work is complete; the loop self-stops here.

## Sign-off checklist

- [ ] PR #7056 carries M3 desktop + M4.1/M4.4/M4.5 web. Convert from Draft → Ready-for-Review after a Mac build verifies the desktop changes.
- [ ] Resolve the M2 audit P1 question (privacy-write gap) — pick (a) ship M2.5 fast, (b) update Settings copy to disclose, or (c) HARD_BLOCK conversation embedding.
- [ ] Product: design or rule out the first authenticated-user AI feature on the web frontend. Without it, the M4 settings-UI never ships.
- [ ] Legal: open the Regolo DPA conversation.
- [ ] Infra: cost+capacity approval for second 4096-dim Pinecone index in staging.
