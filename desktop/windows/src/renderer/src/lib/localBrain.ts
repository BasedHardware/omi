// Local "brain" router client — mirrors router/laya_server.py's /route contract.
//
// A Laya System-1 classifier (a Python sidecar, runs on the user's machine) makes a
// one-forward-pass decision about a request; here we turn that decision into a plan:
//   - local tools / small local LLM  -> keep it on-device (saves cloud quota)
//   - cloud                          -> the existing metered /v2/messages path
// Any error/timeout/disabled returns null so callers ALWAYS fall back to cloud.
// Laya classifies TEXT intent only; speaker identity comes from the local voiceprint.

export type LayaRoute =
  | 'confirm_or_refuse'
  | 'omi_local_memory'
  | 'omi_local_screen_history'
  | 'omi_task_tools'
  | 'small_local_llm'
  | 'large_local_llm_or_cloud'

export type LocalBrainDecision = {
  route: LayaRoute
  intent?: string | null
  needs_tools?: boolean
  difficulty?: number | null
}

export type BrainPlan =
  | { kind: 'confirm' }
  | { kind: 'local_tools' }
  | { kind: 'local_llm' }
  | { kind: 'cloud' }

const VALID_ROUTES = new Set<LayaRoute>([
  'confirm_or_refuse',
  'omi_local_memory',
  'omi_local_screen_history',
  'omi_task_tools',
  'small_local_llm',
  'large_local_llm_or_cloud'
])

/**
 * Pure mapping: decision -> plan. `hasLocalLLM` is whether a local model endpoint is
 * configured (the local tool loop and local answers both need it). Without a local
 * LLM, every "local" intent safely falls back to cloud. No network, unit-testable.
 */
export function planFromDecision(d: LocalBrainDecision | null, hasLocalLLM: boolean): BrainPlan {
  if (!d || !VALID_ROUTES.has(d.route)) return { kind: 'cloud' }
  switch (d.route) {
    case 'confirm_or_refuse':
      return { kind: 'confirm' }
    case 'omi_local_memory':
    case 'omi_local_screen_history':
    case 'omi_task_tools':
      return hasLocalLLM ? { kind: 'local_tools' } : { kind: 'cloud' }
    case 'small_local_llm':
      return hasLocalLLM ? { kind: 'local_llm' } : { kind: 'cloud' }
    default:
      return { kind: 'cloud' }
  }
}

/** Call the sidecar /route. Returns null on any error/timeout so the caller falls back. */
export async function requestLocalBrain(
  baseUrl: string,
  text: string,
  timeoutMs = 900
): Promise<LocalBrainDecision | null> {
  try {
    const res = await fetch(`${baseUrl.replace(/\/$/, '')}/route`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ request: text }),
      signal: AbortSignal.timeout(timeoutMs)
    })
    if (!res.ok) return null
    const data = (await res.json()) as Partial<LocalBrainDecision>
    if (!data || typeof data.route !== 'string') return null
    return {
      route: data.route as LayaRoute,
      intent: data.intent ?? null,
      needs_tools: data.needs_tools ?? false,
      difficulty: data.difficulty ?? null
    }
  } catch {
    return null
  }
}
