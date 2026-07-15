// Change-gated frame distribution — pure. Port of Mac's
// `ProactiveFrameDistributionGate` (`ProactiveAssistantOrchestrationPolicy`).
//
// This is the layer that stops continuous polling from becoming continuous
// ANALYSIS. Capture writes a new frame row whenever the screen's perceptual hash
// moves more than a few bits — i.e. about once a second while someone is typing.
// Without this gate, ten minutes of editing one file would hand the assistants
// ~200 frames (one per coordinator tick) where the user's context never changed
// once. Each of those is a full screenshot an assistant may ship to a cloud
// model, so the gate is worth real money, battery, and pixels-off-device.
//
// It belongs in the framework, not in each assistant's `shouldAnalyze`: an
// assistant that forgets to implement its own throttle would otherwise burn all
// three silently.

export const DEBOUNCE_MS = 3_000
export const FALLBACK_MS = 60_000
/** Messaging apps get a shorter fallback: new content (a reply landing) arrives
 *  without any context change, so the 60s floor would make an assistant blind to
 *  a whole conversation. */
export const MESSAGING_FALLBACK_MS = 15_000

const MESSAGING_APPS = [
  'telegram',
  'messages',
  'imessage',
  'whatsapp',
  'signal',
  'slack',
  'discord',
  'messenger'
]

export function fallbackIntervalMs(app: string): number {
  const name = app.toLowerCase()
  return MESSAGING_APPS.some((m) => name.includes(m)) ? MESSAGING_FALLBACK_MS : FALLBACK_MS
}

export type DistributionDecision =
  /** Hand this frame to the assistants now. */
  | 'flushNow'
  /** Context just changed — wait DEBOUNCE_MS for it to settle, then flush the
   *  LATEST frame (rapid app-hopping should produce one distribution, not five). */
  | 'scheduleDebounce'
  /** Nothing changed and the fallback has not elapsed — drop this frame. */
  | 'skip'

export type DistributionInput = {
  contextChanged: boolean
  /** Foreground app of the frame in hand (picks the fallback interval). */
  app: string
  now: number
  /** null = nothing has ever been distributed. */
  lastDistributedAt: number | null
}

export function distributionDecision(input: DistributionInput): DistributionDecision {
  if (input.lastDistributedAt === null) return 'flushNow' // first frame ever
  if (input.contextChanged) return 'scheduleDebounce'
  const elapsed = input.now - input.lastDistributedAt
  return elapsed >= fallbackIntervalMs(input.app) ? 'flushNow' : 'skip'
}
