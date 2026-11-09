/** Home feed visibility and processing admission.
 * Only an explicit failed projection overrides status; older servers retain
 * their existing behavior.
 */
import type { Conversation } from '@/types/conversation';

/** Older servers omit home_step and keep the existing status-only behavior. */
export function isConversationProcessing(conversation: Conversation): boolean {
  return conversation.home_step !== 'failed' && conversation.status === 'processing';
}

/** Failed projections belong outside the Home conversation feed. */
export function isHomeConversationVisible(conversation: Conversation): boolean {
  return conversation.home_step !== 'failed';
}
