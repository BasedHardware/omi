import {
  filterMixedTimeline,
  groupMixedTimeline,
  mergeMixedTimeline,
  type TimelineConversation,
  type TimelineRecall,
} from './mixedTimeline';

const conversation = (
  id: string,
  atMs: number | null,
): TimelineConversation => ({
  kind: 'conversation',
  id,
  title: id,
  summary: '',
  searchableText: id,
  atMs,
});

const recall = (
  id: string,
  atMs: number | null,
  local = true,
): TimelineRecall => ({
  kind: 'recall',
  id,
  appName: 'Notes',
  windowTitle: id,
  searchableText: `Notes ${id}`,
  atMs,
  source: local ? 'captured' : 'backend',
  local,
});

test('interleaves conversations and recall newest first without dropping either source', () => {
  const items = mergeMixedTimeline({
    conversations: [conversation('talk-late', 300), conversation('talk-early', 100)],
    recall: [recall('screen-mid', 200), recall('screen-oldest', 50)],
  });
  expect(items.map(item => item.id)).toEqual([
    'talk-late',
    'screen-mid',
    'talk-early',
    'screen-oldest',
  ]);
});

test('equal timestamps keep conversations ahead of recall, then sort by id', () => {
  const items = mergeMixedTimeline({
    conversations: [conversation('b-talk', 100), conversation('a-talk', 100)],
    recall: [recall('z-screen', 100), recall('a-screen', 100)],
  });
  expect(items.map(item => `${item.kind}:${item.id}`)).toEqual([
    'conversation:a-talk',
    'conversation:b-talk',
    'recall:a-screen',
    'recall:z-screen',
  ]);
});

test('local recall wins over a backend copy of the same id', () => {
  const items = mergeMixedTimeline({
    conversations: [],
    recall: [
      recall('captured:abc:1', 10, false),
      recall('captured:abc:1', 10, true),
    ],
  });
  expect(items).toHaveLength(1);
  expect(items[0]).toMatchObject({id: 'captured:abc:1', local: true});
});

test('search covers loaded titles only', () => {
  const items = mergeMixedTimeline({
    conversations: [conversation('Product standup', 2)],
    recall: [recall('Figma', 1)],
  });
  expect(filterMixedTimeline(items, 'stand').map(item => item.id)).toEqual([
    'Product standup',
  ]);
  expect(filterMixedTimeline(items, 'figma').map(item => item.id)).toEqual([
    'Figma',
  ]);
});

test('day grouping preserves newest-first order inside each day', () => {
  const items = mergeMixedTimeline({
    conversations: [conversation('today-talk', Date.parse('2026-09-17T12:00:00Z'))],
    recall: [recall('yesterday-screen', Date.parse('2026-09-16T12:00:00Z'))],
  });
  const groups = groupMixedTimeline(
    items,
    Date.parse('2026-09-17T18:00:00Z'),
    iso => (iso.startsWith('2026-09-17') ? 'Today' : 'Yesterday'),
  );
  expect(groups.map(group => group.label)).toEqual(['Today', 'Yesterday']);
});
