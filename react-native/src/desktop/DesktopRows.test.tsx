import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {Text} from 'react-native';
import {
  formatTaskDue,
  type ConversationProjection,
  type MemoryProjection,
  type TaskProjection,
} from '../desktopReadClient';
import {ConversationRow, ReadRow, TaskRow} from './DesktopRows';

function textOf(renderer: ReactTestRenderer.ReactTestRenderer): string {
  return renderer.root
    .findAllByType(Text)
    .flatMap(node =>
      Array.isArray(node.props.children)
        ? node.props.children
        : [node.props.children],
    )
    .filter(
      (value): value is string | number =>
        typeof value === 'string' || typeof value === 'number',
    )
    .join(' ');
}

test('a zero Home current timestamp says Time unavailable instead of omitting the clock', () => {
  const item: MemoryProjection = {
    kind: 'memory',
    id: 'memory-epoch',
    title: 'Undated memory',
    summary: 'Body',
    searchableText: 'Undated memory\nBody',
    citations: [],
    timestamp: 0,
    provenance: {
      label: null,
      synthesisVersion: null,
      inputDigest: null,
      outputDigest: null,
    },
  };
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(<ReadRow item={item} />);
  });
  const copy = textOf(renderer);
  expect(copy).toContain('Time unavailable');
  expect(copy).toContain('Undated memory');
  expect(copy).toContain('0 citations');
  expect(copy).not.toContain('1970');
  expect(copy).not.toMatch(/(^| )Memory( |$)/);
});

test('Home currents keep memory citation counts instead of a Memory kind label', () => {
  const item: MemoryProjection = {
    kind: 'memory',
    id: 'memory-cited',
    title: 'A walk.',
    summary: 'A walk.',
    searchableText: 'A walk.',
    citations: ['citation-v1:launch', 'citation-v1:home'],
    timestamp: 1_788_492_408,
    provenance: {
      label: null,
      synthesisVersion: 'v1',
      inputDigest: 'input',
      outputDigest: 'output',
    },
  };
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(<ReadRow item={item} />);
  });
  const copy = textOf(renderer);
  expect(copy).toContain('A walk.');
  expect(copy).toContain('2 citations');
  expect(copy).not.toContain('citation-v1:launch');
  expect(copy).not.toMatch(/(^| )Memory( |$)/);
});

test('Home currents omit whitespace-only memory citations from the count', () => {
  const item: MemoryProjection = {
    kind: 'memory',
    id: 'memory-blank-citations',
    title: 'A walk.',
    summary: 'A walk.',
    searchableText: 'A walk.',
    citations: [' \t\n', ''],
    timestamp: null,
    provenance: {
      label: null,
      synthesisVersion: null,
      inputDigest: null,
      outputDigest: null,
    },
  };
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(<ReadRow item={item} />);
  });
  const copy = textOf(renderer);
  expect(copy).toContain('0 citations');
  expect(copy).not.toContain('2 citations');
});

test('Home currents keep listen overview speech on the row title', () => {
  const title = 'a'.repeat(80);
  const summary = `${title} later speech`;
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'conversation-one',
    title,
    summary,
    searchableText: `${title}\n${summary}`,
    createdAt: '2026-09-07T00:00:00.000Z',
    updatedAt: '2026-09-07T00:01:00.000Z',
    startedAt: '2026-09-07T00:00:00.000Z',
    finishedAt: '2026-09-07T00:01:00.000Z',
    starred: false,
    status: 'completed',
    source: 'listen',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: false,
  };
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(<ReadRow item={item} />);
  });
  expect(textOf(renderer)).toContain(summary);
  expect(
    renderer.root.findAll(
      node => node.props.numberOfLines === 3 && node.props.children === summary,
    ).length,
  ).toBeGreaterThan(0);
});

test('Home currents keep chat last-turn overview off the timestamp meta', () => {
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'chat:session-alpha',
    title: 'Hi',
    summary:
      'Later independent turn with more speech than a timestamp line keeps',
    searchableText:
      'Hi\nLater independent turn with more speech than a timestamp line keeps',
    createdAt: '2026-09-07T00:00:00.000Z',
    updatedAt: '2026-09-07T00:01:00.000Z',
    startedAt: '2026-09-07T00:00:00.000Z',
    finishedAt: null,
    starred: false,
    status: 'in_progress',
    source: 'chat',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: false,
  };
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(<ReadRow item={item} />);
  });
  expect(textOf(renderer)).toContain('Hi');
  expect(textOf(renderer)).toContain(item.summary);
  expect(
    renderer.root.findAll(
      node =>
        node.props.numberOfLines === 2 && node.props.children === item.summary,
    ).length,
  ).toBeGreaterThan(0);
  expect(
    renderer.root.findAll(
      node =>
        node.props.numberOfLines === 1 &&
        typeof node.props.children === 'string' &&
        node.props.children.includes(item.summary),
    ).length,
  ).toBe(0);
  expect(textOf(renderer)).not.toContain('Duration unavailable');
});

test('Library rows keep chat last-turn overview off the timestamp meta', () => {
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'chat:session-alpha',
    title: 'Hi',
    summary:
      'Later independent turn with more speech than a timestamp line keeps',
    searchableText:
      'Hi\nLater independent turn with more speech than a timestamp line keeps',
    createdAt: '2026-09-07T00:00:00.000Z',
    updatedAt: '2026-09-07T00:01:00.000Z',
    startedAt: '2026-09-07T00:00:00.000Z',
    finishedAt: null,
    starred: false,
    status: 'in_progress',
    source: 'chat',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: false,
  };
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(<ConversationRow item={item} />);
  });
  expect(
    renderer.root.findAll(
      node =>
        node.props.numberOfLines === 2 && node.props.children === item.summary,
    ).length,
  ).toBeGreaterThan(0);
  expect(
    renderer.root.findAll(
      node =>
        node.props.numberOfLines === 1 &&
        typeof node.props.children === 'string' &&
        node.props.children.includes(item.summary),
    ).length,
  ).toBe(0);
  expect(textOf(renderer)).not.toContain('Duration unavailable');
});

test('Home currents keep GET duration instead of clock-only', () => {
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'listen:quick',
    title: 'Quick note',
    summary: 'Twenty seconds.',
    searchableText: 'Quick note\nTwenty seconds.',
    createdAt: '2026-09-07T12:00:00.000Z',
    updatedAt: '2026-09-07T12:00:20.000Z',
    startedAt: '2026-09-07T12:00:00.000Z',
    finishedAt: '2026-09-07T12:00:20.000Z',
    starred: false,
    status: 'completed',
    source: 'listen',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: false,
  };
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(<ReadRow item={item} />);
  });
  const copy = textOf(renderer);
  expect(copy).toContain('Quick note');
  expect(copy).toContain('< 1 min');
  expect(copy).not.toContain('0 min');
  expect(
    renderer.root.findAll(
      node =>
        node.props.numberOfLines === 1 &&
        typeof node.props.children === 'string' &&
        node.props.children.includes('< 1 min'),
    ).length,
  ).toBe(0);
});

test('Library rows keep GET duration instead of clock-only', () => {
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'listen:quick',
    title: 'Quick note',
    summary: 'Twenty seconds.',
    searchableText: 'Quick note\nTwenty seconds.',
    createdAt: '2026-09-07T12:00:00.000Z',
    updatedAt: '2026-09-07T12:00:20.000Z',
    startedAt: '2026-09-07T12:00:00.000Z',
    finishedAt: '2026-09-07T12:00:20.000Z',
    starred: false,
    status: 'completed',
    source: 'listen',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: false,
  };
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(<ConversationRow item={item} />);
  });
  const copy = textOf(renderer);
  expect(copy).toContain('Quick note');
  expect(copy).toContain('< 1 min');
  expect(copy).not.toContain('0 min');
  expect(
    renderer.root.findAll(
      node =>
        node.props.numberOfLines === 1 &&
        typeof node.props.children === 'string' &&
        node.props.children.includes('< 1 min'),
    ).length,
  ).toBe(0);
});

test('a zero conversation start time on Home and Library rows says Duration unavailable', () => {
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'listen:epoch-duration',
    title: 'Missing start',
    summary: 'Finished without a real start time.',
    searchableText: 'Missing start\nFinished without a real start time.',
    createdAt: new Date(0).toISOString(),
    updatedAt: '2026-09-07T12:00:00.000Z',
    startedAt: new Date(0).toISOString(),
    finishedAt: '2026-09-07T12:00:00.000Z',
    starred: false,
    status: 'completed',
    source: 'listen',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: false,
  };
  let home!: ReactTestRenderer.ReactTestRenderer;
  let library!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    home = ReactTestRenderer.create(<ReadRow item={item} />);
    library = ReactTestRenderer.create(<ConversationRow item={item} />);
  });
  for (const copy of [textOf(home), textOf(library)]) {
    expect(copy).toContain('Duration unavailable');
    expect(copy).not.toContain('hr');
  }
});

function taskItem(dueAt: number | null, completed = false): TaskProjection {
  return {
    kind: 'task',
    id: 'task-due',
    title: 'Review notes',
    summary: '',
    searchableText: 'Review notes',
    completed,
    completedAt: null,
    dueAt,
    owner: null,
    source: 'omi',
    provenance: [],
    sortOrder: 0,
    indentLevel: 0,
    createdAt: null,
    updatedAt: null,
    revision: null,
  };
}

test('Home and Tasks rows keep GET due dates instead of title-only', () => {
  const dueAt = 1_767_225_600;
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(<TaskRow item={taskItem(dueAt)} />);
  });
  const copy = textOf(renderer);
  expect(copy).toContain('Review notes');
  expect(copy).toContain(formatTaskDue(dueAt));
  expect(copy).not.toContain('Completed');
});

test('completed Home and Tasks rows keep GET due dates', () => {
  const dueAt = 1_767_225_600;
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <TaskRow item={taskItem(dueAt, true)} />,
    );
  });
  expect(textOf(renderer)).toContain(`Completed · ${formatTaskDue(dueAt)}`);
});

test('Home and Tasks rows with no due date say No due date', () => {
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(<TaskRow item={taskItem(null)} />);
  });
  expect(textOf(renderer)).toContain('No due date');
});

test('a zero task due timestamp on Home and Tasks rows says Date unavailable instead of 1970', () => {
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(<TaskRow item={taskItem(0)} />);
  });
  const copy = textOf(renderer);
  expect(copy).toContain('Date unavailable');
  expect(copy).not.toContain('1970');
  expect(copy).not.toContain('No due date');
});
