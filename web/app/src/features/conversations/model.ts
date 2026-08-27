import type { Conversation } from '@/types/conversation';
import type { DailySummary, GroupedDailySummaries } from '@/types/recap';

/**
 * A single tile in the Timeline gallery. Conversations and daily recaps share
 * one chronological stream, so they share one item type.
 */
export type TimelineItem =
  | {
      kind: 'conversation';
      id: string;
      sortTime: number;
      conversation: Conversation;
    }
  | {
      kind: 'recap';
      id: string;
      sortTime: number;
      recap: DailySummary;
    };

/** One day's worth of tiles, newest day first. */
export interface TimelineDayGroup {
  /** Local `YYYY-MM-DD`, stable across renders and usable as a React key. */
  key: string;
  /** Human heading: `Today`, `Yesterday`, or `Mon, Jan 15`. */
  label: string;
  /** Local midnight for the day, in epoch milliseconds. */
  dayStart: number;
  items: TimelineItem[];
}

export interface BuildTimelineOptions {
  conversations: Conversation[];
  recaps: DailySummary[];
  /** Injectable clock so `Today` / `Yesterday` labels are testable. */
  now?: Date;
}

function pad2(value: number): string {
  return value < 10 ? `0${value}` : `${value}`;
}

/** Local calendar day key for a Date — not UTC, so late-evening items stay put. */
export function dayKeyOf(date: Date): string {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

/** Parse a backend `YYYY-MM-DD` recap date as a local date rather than UTC. */
export function parseLocalDay(dateString: string): Date {
  const [year, month, day] = dateString.split('-').map(Number);
  return new Date(year, (month || 1) - 1, day || 1);
}

export function dayLabel(date: Date, now: Date): string {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const subject = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const dayMs = 24 * 60 * 60 * 1000;
  const delta = Math.round((today.getTime() - subject.getTime()) / dayMs);

  if (delta === 0) return 'Today';
  if (delta === 1) return 'Yesterday';

  return date.toLocaleDateString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  });
}

export function conversationDate(conversation: Conversation): Date {
  return new Date(conversation.started_at || conversation.created_at);
}

/**
 * Interleave recaps with conversations into newest-first day groups.
 *
 * A recap summarises a whole day, so it leads its day rather than slotting in
 * at a wall-clock position no conversation shares.
 */
export function buildTimelineDayGroups({
  conversations,
  recaps,
  now = new Date(),
}: BuildTimelineOptions): TimelineDayGroup[] {
  const groups = new Map<string, TimelineDayGroup>();

  const ensureGroup = (date: Date): TimelineDayGroup => {
    const key = dayKeyOf(date);
    const existing = groups.get(key);
    if (existing) return existing;

    const dayStart = new Date(
      date.getFullYear(),
      date.getMonth(),
      date.getDate(),
    ).getTime();
    const created: TimelineDayGroup = {
      key,
      label: dayLabel(date, now),
      dayStart,
      items: [],
    };
    groups.set(key, created);
    return created;
  };

  for (const recap of recaps) {
    if (!recap?.date) continue;
    const date = parseLocalDay(recap.date);
    if (Number.isNaN(date.getTime())) continue;
    ensureGroup(date).items.push({
      kind: 'recap',
      id: recap.id,
      sortTime: Number.POSITIVE_INFINITY,
      recap,
    });
  }

  for (const conversation of conversations) {
    const date = conversationDate(conversation);
    if (Number.isNaN(date.getTime())) continue;
    ensureGroup(date).items.push({
      kind: 'conversation',
      id: conversation.id,
      sortTime: date.getTime(),
      conversation,
    });
  }

  const ordered = Array.from(groups.values()).sort((a, b) => b.dayStart - a.dayStart);

  for (const group of ordered) {
    group.items.sort((a, b) => b.sortTime - a.sortTime);
  }

  return ordered;
}

/** The scannable signal a gallery tile shows without opening the detail pane. */
export interface ConversationSignals {
  excerpt: string;
  category: string | null;
  actionItemCount: number;
  speakerCount: number;
}

export function conversationSignals(conversation: Conversation): ConversationSignals {
  const structured = conversation.structured ?? {};
  const category =
    structured.category && structured.category !== 'other' ? structured.category : null;

  const segments = conversation.transcript_segments ?? [];
  const speakers = new Set<string>();
  for (const segment of segments) {
    // `speaker` is the label the STT provider assigned; `speaker_id` is its
    // numeric form. Either identifies a distinct voice, neither is guaranteed.
    const identity =
      segment.speaker ?? (segment.speaker_id != null ? `id:${segment.speaker_id}` : null);
    if (identity) speakers.add(identity);
  }

  return {
    excerpt: (structured.overview ?? '').trim(),
    category,
    actionItemCount: structured.action_items?.length ?? 0,
    speakerCount: speakers.size,
  };
}

/** Total tile count across every day group. */
export function countTimelineItems(groups: TimelineDayGroup[]): number {
  return groups.reduce((total, group) => total + group.items.length, 0);
}

/** Flatten day groups back into a single newest-first item stream. */
export function flattenTimelineItems(groups: TimelineDayGroup[]): TimelineItem[] {
  return groups.flatMap((group) => group.items);
}

export const MIN_CONVERSATION_DETAIL_WIDTH = 360;
export const MIN_CONVERSATION_GALLERY_WIDTH = 280;

export function resizeConversationDetailPanel(
  currentWidth: number,
  pointerDelta: number,
  containerWidth: number,
): number {
  const maximum = Math.max(
    MIN_CONVERSATION_DETAIL_WIDTH,
    containerWidth - MIN_CONVERSATION_GALLERY_WIDTH,
  );
  return Math.min(
    maximum,
    Math.max(MIN_CONVERSATION_DETAIL_WIDTH, currentWidth - pointerDelta),
  );
}

export type ConversationSelection =
  | { kind: 'conversation'; id: string }
  | { kind: 'recap'; id: string }
  | null;

export function selectionFromSearchParams(
  conversationId: string | null,
  recapId: string | null,
): ConversationSelection {
  if (recapId) return { kind: 'recap', id: recapId };
  if (conversationId) return { kind: 'conversation', id: conversationId };
  return null;
}

export function formatConversationDate(dateString: string | null): string {
  if (!dateString) return '';
  const date = new Date(dateString);
  return date.toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}

export function conversationDurationSeconds(start: string | null, end: string | null): number {
  if (!start || !end) return 0;
  const startDate = new Date(start);
  const endDate = new Date(end);
  return Math.floor((endDate.getTime() - startDate.getTime()) / 1000);
}

/** Group recaps by calendar month (e.g. "January 2025") for the recap list. */
export function groupRecapsByMonth(recaps: DailySummary[]): GroupedDailySummaries {
  if (!Array.isArray(recaps) || recaps.length === 0) {
    return {};
  }
  return recaps.reduce((groups, recap) => {
    const date = parseLocalDay(recap.date);
    const monthKey = date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
    });
    if (!groups[monthKey]) {
      groups[monthKey] = [];
    }
    groups[monthKey].push(recap);
    return groups;
  }, {} as GroupedDailySummaries);
}
