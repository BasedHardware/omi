import type {ChatMessage} from '../chatClient';

// Pure transcript layout: day separators replace per-message timestamps, and
// consecutive turns from the same sender close up. Shared by the desktop and
// mobile chat surfaces (docs/chat-ux.md).

/** Consecutive messages from one sender closer than this read as one group. */
export const CHAT_GROUP_WINDOW_MS = 5 * 60 * 1000;

/** The legacy wire mixes epoch seconds and milliseconds. */
export function chatMessageMs(createdAt: number): number {
  return createdAt > 100_000_000_000 ? createdAt : createdAt * 1000;
}

function startOfDay(ms: number): number {
  const date = new Date(ms);
  date.setHours(0, 0, 0, 0);
  return date.getTime();
}

/** "Today", "Yesterday", "Wed, Sep 23" (plus the year when it differs). */
export function chatDayLabel(ms: number, now: number = Date.now()): string {
  const day = startOfDay(ms);
  const today = startOfDay(now);
  if (day === today) {
    return 'Today';
  }
  // Calendar days, not 24-hour spans: a DST change must not skip Yesterday.
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  if (day === yesterday.getTime()) {
    return 'Yesterday';
  }
  const date = new Date(ms);
  const sameYear = date.getFullYear() === new Date(now).getFullYear();
  return date.toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    ...(sameYear ? {} : {year: 'numeric'}),
  });
}

/** Time of day for the hover tooltip / accessibility hint. */
export function chatTimeLabel(ms: number): string {
  return new Date(ms).toLocaleTimeString(undefined, {
    hour: 'numeric',
    minute: '2-digit',
  });
}

export type ChatTimelineItem =
  | {kind: 'day'; key: string; label: string}
  | {
      kind: 'message';
      key: string;
      message: ChatMessage;
      /** Same sender as the previous row, close in time: tight spacing. */
      grouped: boolean;
      /** The newest Omi reply: its action bar stays visible. */
      latestReply: boolean;
    };

export function buildChatTimeline(
  messages: readonly ChatMessage[],
  now: number = Date.now(),
): ChatTimelineItem[] {
  let latestReplyId: string | null = null;
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index].sender === 'ai') {
      latestReplyId = messages[index].id;
      break;
    }
  }
  const items: ChatTimelineItem[] = [];
  let previous: ChatMessage | null = null;
  let previousDay: number | null = null;
  for (const message of messages) {
    const ms = chatMessageMs(message.createdAt);
    const day = startOfDay(ms);
    const newDay = previousDay === null || day !== previousDay;
    if (newDay) {
      items.push({
        kind: 'day',
        key: `day-${message.id}`,
        label: chatDayLabel(ms, now),
      });
    }
    const grouped =
      !newDay &&
      previous !== null &&
      previous.sender === message.sender &&
      Math.abs(ms - chatMessageMs(previous.createdAt)) <= CHAT_GROUP_WINDOW_MS;
    items.push({
      kind: 'message',
      key: message.id,
      message,
      grouped,
      latestReply: message.id === latestReplyId,
    });
    previous = message;
    previousDay = day;
  }
  return items;
}
