export type TimelineConversation = {
  kind: 'conversation';
  id: string;
  title: string;
  summary: string;
  searchableText: string;
  atMs: number | null;
};

export type TimelineRecall = {
  kind: 'recall';
  id: string;
  appName: string;
  windowTitle: string;
  searchableText: string;
  atMs: number | null;
  source: 'captured' | 'shipping' | 'backend';
  local: boolean;
};

export type TimelineMemory = {
  kind: 'memory';
  id: string;
  title: string;
  summary: string;
  searchableText: string;
  atMs: number | null;
  source: 'backend';
};

export type MixedTimelineItem =
  | TimelineConversation
  | TimelineRecall
  | TimelineMemory;

export type MixedTimelineGroup = {
  label: string;
  items: MixedTimelineItem[];
};

function compareNewest(
  left: MixedTimelineItem,
  right: MixedTimelineItem,
): number {
  const leftTs = left.atMs ?? Number.NEGATIVE_INFINITY;
  const rightTs = right.atMs ?? Number.NEGATIVE_INFINITY;
  if (rightTs !== leftTs) {
    return rightTs - leftTs;
  }
  if (left.kind !== right.kind) {
    const order = {conversation: 0, memory: 1, recall: 2} as const;
    return order[left.kind] - order[right.kind];
  }
  return left.id.localeCompare(right.id);
}

export function mergeMixedTimeline(input: {
  conversations: readonly TimelineConversation[];
  recall: readonly TimelineRecall[];
  memories?: readonly TimelineMemory[];
}): MixedTimelineItem[] {
  const recallById = new Map<string, TimelineRecall>();
  for (const item of input.recall) {
    const existing = recallById.get(item.id);
    if (existing === undefined) {
      recallById.set(item.id, item);
      continue;
    }
    recallById.set(item.id, existing.local ? existing : item);
  }
  const memoryById = new Map<string, TimelineMemory>();
  for (const item of input.memories ?? []) {
    if (!memoryById.has(item.id)) memoryById.set(item.id, item);
  }
  return [
    ...input.conversations,
    ...memoryById.values(),
    ...recallById.values(),
  ].sort(compareNewest);
}

export function filterMixedTimeline(
  items: readonly MixedTimelineItem[],
  query: string,
): MixedTimelineItem[] {
  const normalized = query.trim().toLocaleLowerCase();
  if (normalized === '') {
    return [...items];
  }
  return items.filter(item =>
    item.searchableText.toLocaleLowerCase().includes(normalized),
  );
}

export function groupMixedTimeline(
  items: readonly MixedTimelineItem[],
  nowEpochMilliseconds: number,
  dayLabel: (iso: string, now: number) => string,
): MixedTimelineGroup[] {
  const groups: MixedTimelineGroup[] = [];
  for (const item of items) {
    const label =
      item.atMs === null || !Number.isFinite(item.atMs)
        ? 'Date unavailable'
        : dayLabel(new Date(item.atMs).toISOString(), nowEpochMilliseconds);
    const current = groups[groups.length - 1];
    if (current !== undefined && current.label === label) {
      current.items.push(item);
    } else {
      groups.push({label, items: [item]});
    }
  }
  return groups;
}
