// Track 2 (AI clone) — pure decision logic for what happens to a drafted
// reply. Kept separate from the drafting itself (personaDraftPrompt.ts) and
// from sending (ipc/aiClone.ts) so the actual "is this safe to auto-send"
// judgment call is one small, fully-tested function.
//
// Default posture is REVIEW, not auto-send: 'off' and 'draft' both stop short
// of actually messaging someone as the user without a human glance first.
// 'auto_send' is an explicit per-chat opt-in the settings UI must ask for
// separately — see chatSettingsStore.ts — and even then, a message that looks
// like it touches money, legal, medical, or relationship-ending territory is
// downgraded to a review queue item rather than sent, because getting one of
// those wrong in someone's own voice is a much worse failure than a delayed
// reply.

import type { AiCloneChatMode } from '../../shared/types'

/** Re-exported so existing imports (`import type { ChatReplyMode } from
 *  './autoReplyPolicy'`) keep working unchanged — shared/types.ts is the
 *  single source of truth so main and renderer can't drift on what the three
 *  modes mean. */
export type ChatReplyMode = AiCloneChatMode

export type ReplyDecision = 'skip' | 'queue_for_review' | 'send'

export interface ReplyDecisionInput {
  mode: ChatReplyMode
  draftText: string
  /** True when the draft itself flagged that it needs a human (see
   *  personaDraftPrompt.draftNeedsInput) — always forces review, even in
   *  auto_send mode. */
  needsInput?: boolean
}

/** Phrases that mean "a human should read this before it goes out as me,"
 *  regardless of how confident the draft sounds. Pattern-level, not
 *  exhaustive — a false negative just means an extra review-queue item next
 *  time this list is extended, a false positive costs one tap in the UI. */
const SENSITIVE_HINTS =
  /\b(password|ssn|social security|wire transfer|bank account|routing number|credit card number|breaking up|break up with|divorc\w*|lawsuit|diagnos\w*|prescription|i quit|i'?m quitting|got fired|laid off|layoff)\b/i

export function looksSensitive(text: string): boolean {
  return SENSITIVE_HINTS.test(text)
}

export function decideReplyAction(input: ReplyDecisionInput): ReplyDecision {
  const text = input.draftText.trim()
  if (input.mode === 'off') return 'skip'
  if (!text) return 'skip'
  if (input.mode === 'draft') return 'queue_for_review'
  // mode === 'auto_send'
  if (input.needsInput) return 'queue_for_review'
  return looksSensitive(text) ? 'queue_for_review' : 'send'
}
