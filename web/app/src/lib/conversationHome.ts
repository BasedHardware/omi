/** Conversation processing admission.
 * Only an explicit failed projection overrides status; older servers retain
 * their existing behavior.
 */
import type { Conversation } from '@/types/conversation';

/** Older servers omit home_step and keep the existing status-only behavior. */
export function isConversationProcessing(conversation: Conversation): boolean {
  return conversation.home_step !== 'failed' && conversation.status === 'processing';
}

/** Failed rows belong only to Activity when placement is explicitly confirmed. */
export function isFailedConversation(conversation: Conversation): boolean {
  return conversation.home_step === 'failed' || conversation.status === 'failed';
}

export function conversationsForSurface(
  conversations: Conversation[],
  activity: boolean,
  confirmed: boolean,
): Conversation[] {
  if (!confirmed) return activity ? [] : conversations;
  return conversations.filter(
    (conversation) =>
      isFailedConversation(conversation) === activity &&
      (activity || conversation.home_step !== 'noise'),
  );
}
