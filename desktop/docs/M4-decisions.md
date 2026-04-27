# M4 — Decision Record

Decisions that unblock the 5-phase M4 plan. Each entry includes alternatives considered and the rationale, so a future engineer can revisit if context changes.

## Decision 1 — BYOK key encryption-at-rest

**Decision:** App-side AES-GCM encryption with a per-user key derived from a single `BYOK_MASTER_PEPPER` env-var via HKDF-SHA256 keyed by user UID.

**Date:** 2026-04-27.

**Status:** Decided. Unblocks M4.1.

### Alternatives considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **A. GCP Cloud KMS** | Audit logs, rotation, IAM-controlled access, FIPS 140-2 alignment | ~30ms latency per read/write, $0.06/key/month + per-operation cost, requires service account setup, every Firestore read needs a separate KMS API call | Reject — overkill for v1 BYOK; cost scales linearly with active users |
| **B. Env-var pepper + HKDF-derived per-user key** *(chosen)* | Zero infrastructure, ~0ms latency, pepper-rotation possible (re-encrypt all keys via batch job), protects against DB-only compromise | Anyone with prod env access can decrypt; pepper must be backed up safely | Accept |
| **C. User-supplied passphrase (zero-knowledge)** | Server can't decrypt without user input | Passphrase loss = permanent BYOK loss (no recovery), poor UX (user re-enters every session), cross-device sync complexity | Reject — bad UX-vs-privacy ratio for an opt-in convenience feature |
| **D. Plaintext in Firestore** | Simplest | Any DB dump exposes all BYOK keys at once | Reject — too risky for keys that grant API spend access |

### Rationale for Option B

Threat model alignment: BYOK is an opt-in convenience for power users who already trust Omi enough to install the desktop client (which stores the key in macOS Keychain — also a single-secret-protects-all model). The web BYOK store should match the same threat tier, not exceed it.

Cost: $0 vs ~$10/month per 100 users for Cloud KMS at the projected access pattern. The KMS savings are not material at our scale, but the latency win is — KMS adds ~30ms to every chat completion that needs to read the BYOK header.

Security wins: Option B protects against a Firestore-only data leak (the most plausible compromise vector — leaked service account, misconfigured rule). It does NOT protect against an attacker who has both the Firestore data AND the production environment, but that compromise scenario is already game-over for many other Omi secrets (Firebase admin SDK key, OpenAI org key, etc.) — adding KMS for BYOK alone would not raise the floor materially.

### Implementation outline (M4.1 reference)

Single file `web/frontend/src/lib/firestore/encryption.ts` (NEW), ~50 LOC:

```typescript
import { hkdf } from '@panva/hkdf'  // or webcrypto subtle if available
const MASTER = process.env.BYOK_MASTER_PEPPER  // 32+ random bytes, base64

async function deriveUserKey(uid: string): Promise<CryptoKey> {
  const salt = new TextEncoder().encode(uid)
  const ikm = base64Decode(MASTER)
  const okm = await hkdf('sha256', ikm, salt, 'omi-byok-v1', 32)
  return crypto.subtle.importKey('raw', okm, { name: 'AES-GCM' }, false, ['encrypt', 'decrypt'])
}

export async function encryptBYOK(uid: string, plaintext: string): Promise<{ ciphertext: string, iv: string }> {
  const key = await deriveUserKey(uid)
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const ct = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, new TextEncoder().encode(plaintext))
  return { ciphertext: base64(ct), iv: base64(iv) }
}

export async function decryptBYOK(uid: string, ciphertext: string, iv: string): Promise<string> { /* mirror */ }
```

Firestore schema (M4.1):

```
users/{uid}/settings: {
  eu_privacy_mode: bool,
  byok_keys: {
    openai:    { ciphertext: string, iv: string, hash: string } | null,
    anthropic: ...,
    gemini:    ...,
    deepgram:  ...,
    regolo:    ...,
  }
}
```

Where `hash` is the SHA-256 fingerprint of the plaintext key — used for `_check_byok_validity` server-side comparisons (matches existing backend BYOK fingerprint pattern at `backend/utils/byok.py:141`) without ever needing to decrypt.

### Operational requirements

- **`BYOK_MASTER_PEPPER` must be backed up safely** (Vault, 1Password Teams, or sealed-secret in the deploy repo). Loss of the pepper = loss of all encrypted BYOK keys.
- **Pepper rotation**: write a one-shot script that decrypts every user's BYOK keys with the old pepper and re-encrypts with the new. Run once when rotating. Log the count, no key material.
- **Pepper must be 32+ bytes of cryptographic randomness** (`openssl rand -base64 32`).
- **Pepper must NOT be `NEXT_PUBLIC_*`** — server-side only.

### Decision authority

Owner: web frontend lead (or whoever drives M4.1).
Reviewers: security + infra.

This record is editable until M4.1 ships. After M4.1 lands, changes to the encryption mechanism become a migration project (re-encrypt all stored ciphertexts).

## Decision 2 — Backend `/v1/chat` contract for M4.3

**Decision:** Reuse the existing endpoint omi backend exposes for desktop chat. The web frontend matches the desktop's request shape (Authorization Bearer + X-BYOK-* + X-Privacy-Mode headers; body is omi's internal chat shape).

**Status:** Confirmed by inspection of desktop's `APIClient.swift` BYOK header forwarding logic. M4.3 doesn't need a new endpoint.

## Decision 3 — `/v1/byok/validate` for M4.2 test-connection

**Decision:** Reuse desktop's `BYOKValidator` HTTP target. The desktop pings provider-specific URLs directly (e.g. regolo at `https://api.regolo.ai/v1/models`). The web frontend should follow the same pattern via a Next.js Server Action that proxies the validation call — never expose BYOK keys to the browser bundle.

**Status:** Decided. Implementation defers to M4.2.

## Open decisions (unresolved as of this writing)

- **Sister-repo distribution strategy for web frontend changes.** The Euraika `omi-regolo-integration` patch package mirrors only `backend/` and `desktop/`; web frontend patches have no canonical distribution channel today. Options: (a) extend sister repo with `web/frontend/` patch tree, (b) keep web changes monorepo-only and contribute upstream via a fork PR. Defer until M4.1 lands and the question becomes concrete.
