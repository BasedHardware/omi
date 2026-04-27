'use client';

/**
 * Notify the user when an EU Privacy Mode request had to fall back to a
 * non-EU provider. Mirrors the desktop's `PrivacyModeFallbackObserver`
 * (`desktop/Desktop/Sources/PrivacyModeFallbackObserver.swift`) reason
 * enum and copy so the two surfaces feel consistent.
 *
 * Usage:
 * ```ts
 * 'use client';
 * const notify = usePrivacyFallbackToast();
 * // After a backend call returns:
 * const reason = response.headers.get('X-Privacy-Mode-Fallback');
 * if (reason) notify(reason);
 * ```
 *
 * Backend contract: when the user sent `X-Privacy-Mode: on` but the
 * request could not actually be served by regolo.ai, the response carries
 * `X-Privacy-Mode-Fallback: <reason>`. Reasons map to friendly copy below;
 * unknown reasons fall back to a generic message rather than dropping
 * silently.
 *
 * Requires `<Toaster />` (from sonner) to be mounted in the app's root
 * layout — see `src/app/layout.tsx`.
 */

import { useCallback } from 'react';
import { toast } from 'sonner';

/**
 * Backend-defined reason tokens — kept in sync with the
 * PRIVACY_FALLBACK_* constants in backend/utils/byok.py and the desktop
 * observer's `Reason` enum. Unknown reasons surface as `other`.
 */
export type PrivacyFallbackReason =
  | 'vision_unsupported'
  | 'regolo_outage'
  | 'regolo_rate_limited'
  | 'no_regolo_key'
  | 'other';

const REASON_COPY: Record<PrivacyFallbackReason, string> = {
  vision_unsupported:
    "Vision isn't available on regolo.ai — this screenshot was processed by Gemini.",
  regolo_outage: 'Regolo.ai is unreachable — falling back to your regular LLM provider.',
  regolo_rate_limited: 'Regolo.ai rate limit hit — falling back to your regular LLM provider.',
  no_regolo_key: 'EU Privacy Mode is on but no Regolo key is configured. Add one in Settings.',
  other: 'This request left the EU.',
};

/** Pure mapping from raw header value → friendly copy. Exported for tests. */
export function privacyFallbackMessage(rawReason: string): string {
  const reason = (rawReason as PrivacyFallbackReason) in REASON_COPY
    ? (rawReason as PrivacyFallbackReason)
    : 'other';
  return REASON_COPY[reason];
}

export function usePrivacyFallbackToast() {
  return useCallback((rawReason: string) => {
    const message = privacyFallbackMessage(rawReason);
    toast.error(message, { duration: 6000, dismissible: true });
  }, []);
}

/**
 * Non-hook helper for non-React contexts (Server Actions handing back
 * results to a client component, etc.). Same mapping; caller is
 * responsible for invoking the toast on the client side.
 */
export const PRIVACY_FALLBACK_REASONS = REASON_COPY;
