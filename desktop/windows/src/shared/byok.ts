// BYOK (Bring Your Own Keys) header + fingerprint helpers.
//
// Mirrors the backend contract in `backend/utils/byok.py` (BYOK_HEADERS,
// SHA-256 fingerprints) and the Rust `Backend-Rust/src/byok.rs`. The desktop
// client sends user-provided provider keys as per-request headers; the backend
// reads them case-insensitively (`x-byok-{provider}`) but clients send the
// canonical casing below. The backend enforces ALL-OR-NOTHING enrollment via
// `has_all_byok_keys()` — a partial set is not a valid BYOK-active state.
//
// Pure, browser-safe module: no Node built-ins, no Electron, no I/O. It is
// imported by BOTH the main process and the renderer (the axios/fetch BYOK
// header lanes). The enrollment fingerprint helper — the one piece that needs
// `node:crypto` — lives in `byokFingerprint.ts` (main-process only) so this
// file never drags a Node built-in into the web bundle.

/** A provider whose API key a user can bring themselves. */
export type ByokProvider = 'openai' | 'anthropic' | 'gemini' | 'deepgram'

/** The four BYOK providers, in the backend's canonical order. */
export const BYOK_PROVIDERS: readonly ByokProvider[] = ['openai', 'anthropic', 'gemini', 'deepgram']

/** Canonical header casing clients send (backend matches case-insensitively). */
export const BYOK_HEADER_NAMES: Record<ByokProvider, string> = {
  openai: 'X-BYOK-OpenAI',
  anthropic: 'X-BYOK-Anthropic',
  gemini: 'X-BYOK-Gemini',
  deepgram: 'X-BYOK-Deepgram'
}

/**
 * Env-var names the pi-mono subprocess reads for BYOK. The bundled
 * omi-provider extension reads exactly these `OMI_BYOK_*` names and re-emits
 * them as `X-BYOK-*` headers (see `desktop/macos/pi-mono-extension/index.ts`),
 * so the casing here — `OMI_BYOK_<PROVIDER-UPPERCASE>` — must match the macOS
 * source (`AgentRuntimeProcess.byokEnvironmentKey`).
 */
export const BYOK_ENV_NAMES: Record<ByokProvider, string> = {
  openai: 'OMI_BYOK_OPENAI',
  anthropic: 'OMI_BYOK_ANTHROPIC',
  gemini: 'OMI_BYOK_GEMINI',
  deepgram: 'OMI_BYOK_DEEPGRAM'
}

/** A (possibly partial) map of provider → raw provider key. */
export type ByokKeys = Partial<Record<ByokProvider, string>>

/** Why a key failed live validation — distinct kinds so the UI can phrase copy. */
export type ByokFailureKind = 'empty' | 'rejected' | 'http' | 'network' | 'timeout'

/** Outcome of validating one provider key. `ok` mirrors a 2xx auth check. */
export interface ByokKeyValidation {
  ok: boolean
  /** Present only when `!ok`. */
  kind?: ByokFailureKind
  /** Human-readable detail for the failing case (never contains the key). */
  detail?: string
}

/** Per-provider validation results. */
export type ByokValidationResults = Partial<Record<ByokProvider, ByokKeyValidation>>

/** Outcome of an enrollment attempt, returned to the renderer Settings UI. */
export interface ByokEnrollResult {
  /** True only when all four keys authenticated AND the backend accepted them. */
  active: boolean
  /** Per-provider live-validation results (empty when the set wasn't full). */
  results: ByokValidationResults
  /**
   * Set only when the keys all validated but the backend enroll call itself
   * failed (network/HTTP) — distinct from a provider rejecting a key.
   */
  backendError?: string
}

/**
 * Return a NEW headers object with `X-BYOK-*` attached for every provider that
 * has a non-empty trimmed key. Keys are sent raw (trimmed, NO `Bearer` prefix)
 * exactly as the backend expects. Never mutates the input `headers` or `keys`.
 */
export function withByokHeaders(
  headers: Record<string, string>,
  keys: ByokKeys
): Record<string, string> {
  const out: Record<string, string> = { ...headers }
  for (const provider of BYOK_PROVIDERS) {
    const value = keys[provider]?.trim()
    if (value) {
      out[BYOK_HEADER_NAMES[provider]] = value
    }
  }
  return out
}

/**
 * True only when ALL four providers have a non-empty trimmed key — matches the
 * backend's all-or-nothing gate (`has_all_byok_keys()`). A partial set is not
 * BYOK-active.
 */
export function isByokActive(keys: ByokKeys): boolean {
  return BYOK_PROVIDERS.every((provider) => Boolean(keys[provider]?.trim()))
}

/**
 * The `OMI_BYOK_*` env set to inject into the pi-mono subprocess, or `{}` when
 * BYOK is not active. All-or-nothing, exactly like `withByokHeaders`'s consumer:
 * a partial set is never injected (the backend's `has_all_byok_keys()` requires
 * all four), so a 3/4 configuration falls through to Omi-managed billing rather
 * than silently sending an incomplete BYOK set. Values are trimmed to match the
 * wire value the backend fingerprints.
 */
export function byokEnvVars(keys: ByokKeys): Record<string, string> {
  if (!isByokActive(keys)) return {}
  const out: Record<string, string> = {}
  for (const provider of BYOK_PROVIDERS) {
    // isByokActive guarantees a non-empty trimmed value for every provider.
    out[BYOK_ENV_NAMES[provider]] = (keys[provider] as string).trim()
  }
  return out
}
