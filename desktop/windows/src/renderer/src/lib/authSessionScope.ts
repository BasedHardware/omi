import type { AxiosRequestConfig } from 'axios'

// authSession advances this renderer's generation on Firebase auth changes.
// This leaf stays import-pure so retries and caches share one revocation boundary.
let generation = 0

export function getAuthSessionGeneration(): number {
  return generation
}

export function advanceAuthSessionGeneration(): void {
  generation += 1
}

/** Capture before starting an asynchronous request, not when its retry runs. */
export function captureAuthRequestScope(
  originGeneration = generation
): AxiosRequestConfig & { __authGeneration: number } {
  return { __authGeneration: originGeneration }
}
