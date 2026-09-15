import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {Text} from 'react-native';
import {
  formatTaskDue,
  clockLabel,
  conversationListTimeCopy,
  type ConversationProjection,
  type MemoryProjection,
  type TaskProjection,
} from '../desktopReadClient';
import {ConversationRow, MemoryRow, ReadRow, TaskRow} from './DesktopRows';

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

test('Home currents omit Flutter MemoryItem unused timestamp and citation count', () => {
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
  const cited: MemoryProjection = {
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
  let undated!: ReactTestRenderer.ReactTestRenderer;
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    undated = ReactTestRenderer.create(<ReadRow item={item} />);
    renderer = ReactTestRenderer.create(<ReadRow item={cited} />);
  });
  const copy = textOf(undated);
  expect(copy).toContain('Undated memory');
  expect(copy).not.toContain('Time unavailable');
  expect(copy).not.toContain('Date unavailable');
  expect(copy).not.toContain('0 citations');
  expect(copy).not.toContain('Synthesized memory');
  expect(copy).not.toContain('1970');
  expect(copy).not.toMatch(/(^| )Memory( |$)/);
  const citedCopy = textOf(renderer);
  expect(citedCopy).toContain('A walk.');
  expect(citedCopy).not.toContain('Synthesized memory');
  expect(citedCopy).not.toContain('2 citations');
  expect(citedCopy).not.toContain('1 citation');
  expect(citedCopy).not.toContain('0 citations');
  expect(citedCopy).not.toContain('citation-v1:launch');
  expect(citedCopy).not.toContain('input');
  expect(citedCopy).not.toContain('output');
  expect(citedCopy).not.toMatch(/(^| )Memory( |$)/);
});

test('Home currents name Flutter MemoryItem empty GET content', () => {
  const item: MemoryProjection = {
    kind: 'memory',
    id: 'memory-blank',
    title: '',
    summary: '',
    searchableText: '',
    citations: [],
    timestamp: null,
    provenance: {
      label: null,
      synthesisVersion: null,
      inputDigest: null,
      outputDigest: null,
    },
  };
  let home!: ReactTestRenderer.ReactTestRenderer;
  let card!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    home = ReactTestRenderer.create(<ReadRow item={item} />);
    card = ReactTestRenderer.create(<MemoryRow item={item} />);
  });
  expect(textOf(home)).not.toContain('Memory text unavailable');
  expect(textOf(card)).not.toContain('Memory text unavailable');
  expect(home.root.findAllByType(Text).length).toBeGreaterThan(0);
  expect(card.root.findAllByType(Text).length).toBeGreaterThan(0);
  const whitespaceItem: MemoryProjection = {
    ...item,
    title: ' \t',
    summary: ' \t',
    searchableText: ' \t',
  };
  let whitespaceHome!: ReactTestRenderer.ReactTestRenderer;
  let whitespaceCard!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    whitespaceHome = ReactTestRenderer.create(
      <ReadRow item={whitespaceItem} />,
    );
    whitespaceCard = ReactTestRenderer.create(
      <MemoryRow item={whitespaceItem} />,
    );
  });
  expect(textOf(whitespaceHome)).toContain(' \t');
  expect(textOf(whitespaceCard)).toContain(' \t');
});

test('Home currents name GET locked memories and omit unlocked rows', () => {
  const item: MemoryProjection = {
    kind: 'memory',
    id: 'memory-locked',
    title: 'A walk.',
    summary: 'A walk.',
    searchableText: 'A walk.',
    citations: [],
    timestamp: 1_788_492_408,
    provenance: {
      label: null,
      synthesisVersion: null,
      inputDigest: null,
      outputDigest: null,
    },
    locked: true,
  };
  let locked!: ReactTestRenderer.ReactTestRenderer;
  let open!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    locked = ReactTestRenderer.create(<ReadRow item={item} />);
    open = ReactTestRenderer.create(
      <ReadRow item={{...item, id: 'memory-open', locked: undefined}} />,
    );
  });
  expect(textOf(locked)).toContain('Locked');
  expect(textOf(locked)).not.toContain('Upgrade to unlimited');
  expect(textOf(open)).not.toContain('Locked');
});

test('Home currents omit Flutter MemoryItem unused synthesized-memory chrome', () => {
  const item: MemoryProjection = {
    kind: 'memory',
    id: 'memory-plain',
    title: 'A walk.',
    summary: 'A walk.',
    searchableText: 'A walk.',
    citations: ['citation-v1:launch'],
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
  expect(copy).not.toContain('1 citation');
  expect(copy).not.toContain('Synthesized memory');
  expect(copy).not.toContain('input');
  expect(copy).not.toContain('output');
});

test('Home currents name GET memory ledger chrome and omit empty fields', () => {
  const item: MemoryProjection = {
    kind: 'memory',
    id: 'memory-ledger',
    title: 'A walk.',
    summary: 'A walk.',
    searchableText: 'A walk.',
    citations: ['citation-v1:launch'],
    timestamp: 1_788_492_408,
    provenance: {
      label: null,
      synthesisVersion: null,
      inputDigest: null,
      outputDigest: null,
    },
    ledgerSlot: 'identity.full_name',
    ledgerBody: 'Open with the weekly recap.',
    isBaseline: true,
    captureDeviceLabel: 'Mac',
  };
  let named!: ReactTestRenderer.ReactTestRenderer;
  let padded!: ReactTestRenderer.ReactTestRenderer;
  let omitted!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    named = ReactTestRenderer.create(<ReadRow item={item} />);
    padded = ReactTestRenderer.create(
      <ReadRow
        item={{
          ...item,
          id: 'memory-ledger-padded',
          ledgerSlot: '  identity.full_name  ',
          ledgerBody: undefined,
          isBaseline: false,
          captureDeviceLabel: undefined,
        }}
      />,
    );
    omitted = ReactTestRenderer.create(
      <ReadRow
        item={{
          ...item,
          id: 'memory-ledger-omitted',
          ledgerSlot: ' \t',
          ledgerBody: '\u0085',
          isBaseline: false,
          captureDeviceLabel: '',
        }}
      />,
    );
  });
  const copy = textOf(named);
  expect(copy).toContain('identity.full_name');
  expect(textOf(padded)).toContain('  identity.full_name  ');
  expect(copy).toContain('Open with the weekly recap.');
  expect(copy).toContain('⚑');
  expect(copy).not.toContain('Baseline Memory');
  expect(copy).toContain('Mac');
  const omittedCopy = textOf(omitted);
  expect(omittedCopy).toContain('A walk.');
  expect(omittedCopy).not.toContain('identity.full_name');
  expect(omittedCopy).not.toContain('Open with the weekly recap.');
  expect(omittedCopy).not.toContain('⚑');
  expect(omittedCopy).not.toContain('Baseline Memory');
  expect(omittedCopy).not.toContain('Mac');
});

test('Home currents name GET memory History chrome and omit current rows', () => {
  const item: MemoryProjection = {
    kind: 'memory',
    id: 'memory-history',
    title: 'A walk.',
    summary: 'A walk.',
    searchableText: 'A walk.',
    citations: [],
    timestamp: 1_788_492_408,
    provenance: {
      label: null,
      synthesisVersion: null,
      inputDigest: null,
      outputDigest: null,
    },
    history: true,
  };
  let named!: ReactTestRenderer.ReactTestRenderer;
  let omitted!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    named = ReactTestRenderer.create(<ReadRow item={item} />);
    omitted = ReactTestRenderer.create(
      <ReadRow item={{...item, id: 'memory-current', history: false}} />,
    );
  });
  expect(textOf(named)).toContain('⟳');
  expect(textOf(named)).not.toContain('History');
  expect(textOf(omitted)).not.toContain('⟳');
  expect(textOf(omitted)).not.toContain('History');
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
  expect(copy).toContain('A walk.');
  expect(copy).not.toContain('0 citations');
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
  expect(textOf(renderer)).not.toContain(item.summary);
  expect(
    renderer.root.findAll(
      node =>
        node.props.numberOfLines === 2 && node.props.children === item.summary,
    ).length,
  ).toBe(0);
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
  ).toBe(0);
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
  expect(copy).toContain('20s');
  expect(copy).not.toContain('0 min');
  expect(
    renderer.root.findAll(
      node =>
        node.props.numberOfLines === 1 &&
        typeof node.props.children === 'string' &&
        node.props.children.includes('20s'),
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
  expect(copy).toContain('20s');
  expect(copy).not.toContain('0 min');
  expect(
    renderer.root.findAll(
      node =>
        node.props.numberOfLines === 1 &&
        typeof node.props.children === 'string' &&
        node.props.children.includes('20s'),
    ).length,
  ).toBe(0);
});

test('same-second conversation clocks omit compact duration on Home and Library', () => {
  const startedAt = '2026-09-07T12:00:00.000Z';
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'listen:zero-span',
    title: 'Instant note',
    summary: 'Finished in the same second.',
    searchableText: 'Instant note\nFinished in the same second.',
    createdAt: startedAt,
    updatedAt: startedAt,
    startedAt,
    finishedAt: startedAt,
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
  for (const renderer of [home, library]) {
    const copy = textOf(renderer);
    expect(copy).not.toContain('Duration unavailable');
    expect(copy).not.toContain('0s');
    expect(copy).not.toContain('0 min');
  }
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

test('discarded Home and Library rows name GET transcript span instead of Duration unavailable', () => {
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'listen:discarded-timed',
    title: 'Speaker 1: Hello from the recording',
    summary: 'Saved words',
    searchableText: 'Speaker 1: Hello from the recording\nSaved words',
    createdAt: '2026-09-07T00:00:00.000Z',
    updatedAt: '2026-09-07T00:01:00.000Z',
    startedAt: '2026-09-07T00:00:00.000Z',
    finishedAt: null,
    starred: false,
    status: 'completed',
    source: 'listen',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: true,
    transcriptEndSeconds: 120,
  };
  let home!: ReactTestRenderer.ReactTestRenderer;
  let library!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    home = ReactTestRenderer.create(<ReadRow item={item} />);
    library = ReactTestRenderer.create(<ConversationRow item={item} />);
  });
  for (const copy of [textOf(home), textOf(library)]) {
    expect(copy).toContain('2m');
    expect(copy).not.toContain('Duration unavailable');
  }
});

test('non-discarded Home and Library rows name GET transcript span instead of Duration unavailable', () => {
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'listen:timed',
    title: 'Product review',
    summary: 'Talked through the release.',
    searchableText: 'Product review\nTalked through the release.',
    createdAt: '2026-09-07T00:00:00.000Z',
    updatedAt: '2026-09-07T00:01:00.000Z',
    startedAt: '2026-09-07T00:00:00.000Z',
    finishedAt: null,
    starred: false,
    status: 'completed',
    source: 'listen',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: false,
    transcriptEndSeconds: 120,
  };
  let home!: ReactTestRenderer.ReactTestRenderer;
  let library!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    home = ReactTestRenderer.create(<ReadRow item={item} />);
    library = ReactTestRenderer.create(<ConversationRow item={item} />);
  });
  for (const copy of [textOf(home), textOf(library)]) {
    expect(copy).toContain('2m');
    expect(copy).not.toContain('Duration unavailable');
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

test('Home and Tasks rows omit Flutter ActionItemsPage due dates', () => {
  const dueAt = 1_767_225_600;
  let dated!: ReactTestRenderer.ReactTestRenderer;
  let completed!: ReactTestRenderer.ReactTestRenderer;
  let missing!: ReactTestRenderer.ReactTestRenderer;
  let zero!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    dated = ReactTestRenderer.create(<TaskRow item={taskItem(dueAt)} />);
    completed = ReactTestRenderer.create(
      <TaskRow item={taskItem(dueAt, true)} />,
    );
    missing = ReactTestRenderer.create(<TaskRow item={taskItem(null)} />);
    zero = ReactTestRenderer.create(<TaskRow item={taskItem(0)} />);
  });
  const datedCopy = textOf(dated);
  expect(datedCopy).toContain('Review notes');
  expect(datedCopy).not.toContain(formatTaskDue(dueAt));
  expect(datedCopy).not.toContain('No due date');
  expect(textOf(completed)).not.toContain(`Completed · ${formatTaskDue(dueAt)}`);
  expect(textOf(missing)).not.toContain('No due date');
  const zeroCopy = textOf(zero);
  expect(zeroCopy).not.toContain('Date unavailable');
  expect(zeroCopy).not.toContain('1970');
  expect(zeroCopy).not.toContain('No due date');
});

test('Home and Tasks rows keep GET indent instead of a flat list', () => {
  let nested!: ReactTestRenderer.ReactTestRenderer;
  let sibling!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    nested = ReactTestRenderer.create(
      <TaskRow item={{...taskItem(null), indentLevel: 2}} />,
    );
    sibling = ReactTestRenderer.create(
      <TaskRow item={{...taskItem(null), indentLevel: 0}} />,
    );
  });
  const nestedLead = nested.root.findAll(
    node => node.props.accessibilityLabel === 'Nested task',
  );
  expect(nestedLead.length).toBeGreaterThan(0);
  expect(
    nested.root.findAll(node =>
      [node.props.style]
        .flat(Infinity)
        .some(
          (entry: {paddingLeft?: number} | null) => entry?.paddingLeft === 56,
        ),
    ).length,
  ).toBeGreaterThan(0);
  expect(
    sibling.root.findAll(
      node => node.props.accessibilityLabel === 'Nested task',
    ),
  ).toHaveLength(0);
});

test('Home rows omit Flutter TodayTasksWidget export chrome', () => {
  let exported!: ReactTestRenderer.ReactTestRenderer;
  let omitted!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    exported = ReactTestRenderer.create(
      <TaskRow
        item={{
          ...taskItem(null),
          title: 'Call Sam',
          exportCopy: 'Exported to Todoist',
        }}
      />,
    );
    omitted = ReactTestRenderer.create(
      <TaskRow item={{...taskItem(null), title: 'Write recap'}} />,
    );
  });
  expect(textOf(exported)).toContain('Call Sam');
  expect(textOf(exported)).not.toContain('Exported to Todoist');
  expect(textOf(omitted)).not.toContain('Exported to');
});

test('Home and Tasks rows name Flutter empty GET descriptions', () => {
  let home!: ReactTestRenderer.ReactTestRenderer;
  let tasks!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    home = ReactTestRenderer.create(
      <ReadRow item={{...taskItem(null), title: '', searchableText: ''}} />,
    );
    tasks = ReactTestRenderer.create(
      <TaskRow item={{...taskItem(null), title: ' \t\n', searchableText: ''}} />,
    );
  });
  expect(textOf(home)).not.toContain('Task title unavailable');
  expect(textOf(tasks)).not.toContain('Task title unavailable');
  expect(
    tasks.root
      .findAllByType(Text)
      .some(node => node.props.children === ' \t\n'),
  ).toBe(true);
  expect(home.root.findAllByType(Text).length).toBeGreaterThan(0);
  expect(tasks.root.findAllByType(Text).length).toBeGreaterThan(0);
});

test('Tasks rows name GET exported platforms and omit missing exports', () => {
  let exported!: ReactTestRenderer.ReactTestRenderer;
  let omitted!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    exported = ReactTestRenderer.create(
      <TaskRow
        showExport
        item={{
          ...taskItem(null),
          title: 'Call Sam',
          exportCopy: 'Exported to Todoist',
        }}
      />,
    );
    omitted = ReactTestRenderer.create(
      <TaskRow
        showExport
        item={{...taskItem(null), title: 'Write recap'}}
      />,
    );
  });
  expect(textOf(exported)).toContain('Exported to Todoist');
  expect(textOf(omitted)).not.toContain('Exported to');
});

test('Home and Library rows omit Flutter ConversationListItem unused capturedAt', () => {
  const captured = new Date(2025, 7, 10, 12, 0);
  const expected = `Captured (device time) · ${clockLabel(
    captured.getTime(),
    Date.now(),
  )}`;
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'recording:captured-row',
    title: 'Device capture',
    summary: 'Recorded on the wearable.',
    searchableText: 'Device capture\nRecorded on the wearable.',
    createdAt: captured.toISOString(),
    updatedAt: captured.toISOString(),
    startedAt: captured.toISOString(),
    finishedAt: captured.toISOString(),
    capturedAtMs: captured.getTime(),
    starred: false,
    status: 'completed',
    source: 'omi',
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
    expect(copy).toContain('Device capture');
    expect(copy).not.toContain('Captured (device time)');
    expect(copy).not.toContain(expected);
    expect(copy).not.toContain('1970');
  }
  let plain!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    plain = ReactTestRenderer.create(
      <ReadRow item={{...item, capturedAtMs: undefined}} />,
    );
  });
  expect(textOf(plain)).not.toContain('Captured (device time)');
});

test('Home and Library conversation rows name Flutter ConversationListItem h:mm a', () => {
  const older = new Date(2025, 7, 10, 12, 0);
  const time = conversationListTimeCopy(older.toISOString());
  const dated = clockLabel(older.getTime(), Date.now());
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'listen:older-row',
    title: 'Product review',
    summary: 'Talked through the release.',
    searchableText: 'Product review\nTalked through the release.',
    createdAt: older.toISOString(),
    updatedAt: older.toISOString(),
    startedAt: older.toISOString(),
    finishedAt: older.toISOString(),
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
    expect(copy).toContain('Product review');
    expect(copy).toContain(time);
    expect(copy).not.toContain(dated);
  }
});

test('Home and Library rows keep GET locked flags and omit Flutter ConversationListItem Discarded chip', () => {
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'listen:locked-row',
    title: 'Kept recording',
    summary: 'Saved words',
    searchableText: 'Kept recording\nSaved words',
    createdAt: '2026-09-07T12:00:00.000Z',
    updatedAt: '2026-09-07T12:00:20.000Z',
    startedAt: '2026-09-07T12:00:00.000Z',
    finishedAt: '2026-09-07T12:00:20.000Z',
    starred: false,
    status: 'processing',
    source: 'listen',
    visibility: 'private',
    folderId: null,
    locked: true,
    discarded: true,
  };
  let home!: ReactTestRenderer.ReactTestRenderer;
  let library!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    home = ReactTestRenderer.create(<ReadRow item={item} />);
    library = ReactTestRenderer.create(<ConversationRow item={item} />);
  });
  for (const copy of [textOf(home), textOf(library)]) {
    expect(copy).toContain('Kept recording');
    expect(copy).toContain('Locked');
    expect(copy).not.toContain('Discarded');
  }
  let plain!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    plain = ReactTestRenderer.create(
      <ReadRow item={{...item, locked: false, discarded: false}} />,
    );
  });
  expect(textOf(plain)).not.toContain('Locked');
  expect(textOf(plain)).not.toContain('Discarded');
});

test('Home and Library rows name discarded empty GET transcript instead of structured title', () => {
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'omi-discarded-empty',
    title: '',
    summary: 'Actual overview',
    searchableText: '\nActual overview',
    createdAt: '2026-09-07T12:00:00.000Z',
    updatedAt: '2026-09-07T12:00:20.000Z',
    startedAt: '2026-09-07T12:00:00.000Z',
    finishedAt: '2026-09-07T12:00:20.000Z',
    starred: false,
    status: 'completed',
    source: 'omi',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: true,
  };
  let home!: ReactTestRenderer.ReactTestRenderer;
  let library!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    home = ReactTestRenderer.create(<ReadRow item={item} />);
    library = ReactTestRenderer.create(<ConversationRow item={item} />);
  });
  for (const copy of [textOf(home), textOf(library)]) {
    expect(copy).not.toContain('Actual overview');
    expect(copy).not.toContain('Kept title');
    expect(copy).not.toContain('Discarded');
    expect(copy).toContain('12:00 PM');
  }
});

test('Home and Library rows omit Flutter ConversationListItem Failed chips', () => {
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'recording:failed-row',
    title: '',
    summary: '',
    searchableText: '',
    createdAt: '2026-09-07T12:00:00.000Z',
    updatedAt: '2026-09-07T12:00:20.000Z',
    startedAt: '2026-09-07T12:00:00.000Z',
    finishedAt: '2026-09-07T12:00:20.000Z',
    starred: false,
    status: 'failed',
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
    expect(copy).not.toContain('Conversation title unavailable');
    expect(copy).not.toContain('Failed');
    expect(copy).not.toContain('In progress');
    expect(copy).toContain('12:00 PM');
    expect(copy).toContain('20s');
  }
  let plain!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    plain = ReactTestRenderer.create(
      <ReadRow
        item={{...item, status: 'completed', title: 'Kept recording'}}
      />,
    );
  });
  expect(textOf(plain)).not.toContain('Failed');
});

test('Home and Library rows name Flutter ConversationListItem empty GET title whitespace', () => {
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'recording:whitespace-title',
    title: ' \t\n',
    summary: '',
    searchableText: '',
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
  let whitespace!: ReactTestRenderer.ReactTestRenderer;
  let padded!: ReactTestRenderer.ReactTestRenderer;
  let nextLine!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    whitespace = ReactTestRenderer.create(<ReadRow item={item} />);
    padded = ReactTestRenderer.create(
      <ConversationRow item={{...item, title: '  Morning walk  '}} />,
    );
    nextLine = ReactTestRenderer.create(
      <ReadRow item={{...item, title: '\u0085'}} />,
    );
  });
  expect(
    whitespace.root.findAll(
      node => node.type === Text && node.props.children === ' \t\n',
    ).length,
  ).toBeGreaterThan(0);
  expect(
    padded.root.findAll(
      node => node.type === Text && node.props.children === '  Morning walk  ',
    ).length,
  ).toBeGreaterThan(0);
  expect(
    nextLine.root.findAll(
      node => node.type === Text && node.props.children === '\u0085',
    ).length,
  ).toBeGreaterThan(0);
  expect(textOf(whitespace)).not.toContain('Conversation title unavailable');
  expect(textOf(padded)).not.toContain('Conversation title unavailable');
});

test('Home and Library rows omit Flutter ConversationListItem Processing chips', () => {
  const processing: ConversationProjection = {
    kind: 'conversation',
    id: 'recording:processing-row',
    title: 'Morning standup',
    summary: 'Notes',
    searchableText: 'Morning standup\nNotes',
    createdAt: '2026-09-07T12:00:00.000Z',
    updatedAt: '2026-09-07T12:00:20.000Z',
    startedAt: '2026-09-07T12:00:00.000Z',
    finishedAt: '2026-09-07T12:00:20.000Z',
    starred: false,
    status: 'processing',
    source: 'listen',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: false,
  };
  const merging: ConversationProjection = {
    ...processing,
    id: 'recording:merging-row',
    title: 'Standup recap',
    searchableText: 'Standup recap\nNotes',
    status: 'merging',
  };
  let home!: ReactTestRenderer.ReactTestRenderer;
  let library!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    home = ReactTestRenderer.create(<ReadRow item={processing} />);
    library = ReactTestRenderer.create(<ConversationRow item={merging} />);
  });
  expect(textOf(home)).toContain('Morning standup');
  expect(textOf(home)).not.toContain('Processing');
  expect(textOf(library)).toContain('Standup recap');
  expect(textOf(library)).toContain('Merging...');
  expect(textOf(library)).not.toContain('Processing');
  let chat!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    chat = ReactTestRenderer.create(
      <ReadRow
        item={{
          ...processing,
          id: 'chat:chat-main',
          title: 'Hello',
          summary: 'Later turn',
          searchableText: 'Hello\nLater turn',
          status: 'in_progress',
          source: 'chat',
          finishedAt: null,
        }}
      />,
    );
  });
  expect(textOf(chat)).toContain('Hello');
  expect(textOf(chat)).not.toContain('Processing');
  expect(textOf(chat)).not.toContain('In progress');
});

test('Home and Library rows omit Flutter ConversationListItem unused overview', () => {
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'omi-overview-row',
    title: 'Morning standup',
    summary: 'Notes from the standup',
    searchableText: 'Morning standup\nNotes from the standup',
    createdAt: '2026-09-07T12:00:00.000Z',
    updatedAt: '2026-09-07T12:00:20.000Z',
    startedAt: '2026-09-07T12:00:00.000Z',
    finishedAt: '2026-09-07T12:00:20.000Z',
    starred: false,
    status: 'completed',
    source: 'omi',
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
  expect(textOf(home)).toContain('Morning standup');
  expect(textOf(home)).not.toContain('Notes from the standup');
  expect(textOf(library)).toContain('Morning standup');
  expect(textOf(library)).not.toContain('Notes from the standup');
});

test('library conversation rows name GET emoji including Flutter ConversationListItem empty GET emoji', () => {
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'omi-emoji',
    title: 'Morning standup',
    summary: 'Notes',
    searchableText: 'Morning standup\nNotes',
    createdAt: '2026-09-07T00:00:00.000Z',
    updatedAt: '2026-09-07T00:01:00.000Z',
    startedAt: '2026-09-07T00:00:00.000Z',
    finishedAt: '2026-09-07T00:01:00.000Z',
    starred: false,
    status: 'completed',
    source: 'omi',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: false,
    emoji: '🚀',
  };
  let shown!: ReactTestRenderer.ReactTestRenderer;
  let hidden!: ReactTestRenderer.ReactTestRenderer;
  let empty!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    shown = ReactTestRenderer.create(<ConversationRow item={item} />);
    hidden = ReactTestRenderer.create(
      <ConversationRow item={{...item, discarded: true, emoji: '🧠'}} />,
    );
    empty = ReactTestRenderer.create(
      <ConversationRow item={{...item, emoji: ' \u0085 '}} />,
    );
  });
  expect(textOf(shown)).toContain('🚀');
  expect(textOf(hidden)).not.toContain('🚀');
  expect(textOf(hidden)).not.toContain('🧠');
  expect(
    empty.root.findAll(
      node =>
        node.type === 'Text' &&
        node.props.numberOfLines === undefined &&
        node.props.children === ' \u0085 ',
    ).length,
  ).toBeGreaterThan(0);
  expect(textOf(empty)).toContain('\u0085');
});

test('library conversation rows name Flutter New chrome for a just-created row', () => {
  const now = Date.now();
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'omi-new',
    title: 'Morning standup',
    summary: 'Notes',
    searchableText: 'Morning standup\nNotes',
    createdAt: new Date(now - 50_000).toISOString(),
    updatedAt: new Date(now - 20_000).toISOString(),
    startedAt: new Date(now - 50_000).toISOString(),
    finishedAt: new Date(now - 20_000).toISOString(),
    starred: false,
    status: 'completed',
    source: 'omi',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: false,
  };
  let shown!: ReactTestRenderer.ReactTestRenderer;
  let hidden!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    shown = ReactTestRenderer.create(<ConversationRow item={item} />);
    hidden = ReactTestRenderer.create(
      <ConversationRow
        item={{
          ...item,
          id: 'omi-old',
          createdAt: '2026-09-07T00:00:00.000Z',
          updatedAt: '2026-09-07T00:01:00.000Z',
          startedAt: '2026-09-07T00:00:00.000Z',
          finishedAt: '2026-09-07T00:01:00.000Z',
        }}
      />,
    );
  });
  expect(textOf(shown)).toContain('New 🚀');
  expect(textOf(shown)).not.toContain('30s');
  expect(textOf(hidden)).not.toContain('New 🚀');
  expect(textOf(hidden)).toContain('1m');
});

test('library conversation rows name GET category and omit discarded or empty values', () => {
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'omi-work',
    title: 'Morning standup',
    summary: 'Notes',
    searchableText: 'Morning standup\nNotes',
    createdAt: '2026-09-07T00:00:00.000Z',
    updatedAt: '2026-09-07T00:01:00.000Z',
    startedAt: '2026-09-07T00:00:00.000Z',
    finishedAt: '2026-09-07T00:01:00.000Z',
    starred: false,
    status: 'completed',
    source: 'omi',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: false,
    category: 'work',
  };
  let shown!: ReactTestRenderer.ReactTestRenderer;
  let hidden!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    shown = ReactTestRenderer.create(<ConversationRow item={item} />);
    hidden = ReactTestRenderer.create(
      <ConversationRow item={{...item, discarded: true, category: 'work'}} />,
    );
  });
  expect(textOf(shown)).toContain('Work');
  expect(textOf(hidden)).not.toContain('Work');
});

test('library conversation rows name GET source remaps and omit ordinary sources', () => {
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'omi-screenpipe',
    title: 'Morning standup',
    summary: 'Notes',
    searchableText: 'Morning standup\nNotes',
    createdAt: '2026-09-07T00:00:00.000Z',
    updatedAt: '2026-09-07T00:01:00.000Z',
    startedAt: '2026-09-07T00:00:00.000Z',
    finishedAt: '2026-09-07T00:01:00.000Z',
    starred: false,
    status: 'completed',
    source: 'screenpipe',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: false,
    category: 'work',
  };
  let shown!: ReactTestRenderer.ReactTestRenderer;
  let ordinary!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    shown = ReactTestRenderer.create(<ConversationRow item={item} />);
    ordinary = ReactTestRenderer.create(
      <ConversationRow item={{...item, source: 'omi', category: undefined}} />,
    );
  });
  expect(textOf(shown)).toContain('Screenpipe');
  expect(textOf(shown)).not.toContain('Work');
  expect(textOf(ordinary)).not.toContain('Screenpipe');
  expect(textOf(ordinary)).not.toContain('omi');
});

test('library conversation rows omit Flutter getTag source remaps when GET category is empty', () => {
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'omi-screenpipe',
    title: 'Empty category talk',
    summary: 'Notes',
    searchableText: 'Empty category talk\nNotes',
    createdAt: '2026-09-07T00:00:00.000Z',
    updatedAt: '2026-09-07T00:01:00.000Z',
    startedAt: '2026-09-07T00:00:00.000Z',
    finishedAt: '2026-09-07T00:01:00.000Z',
    starred: false,
    status: 'completed',
    source: 'screenpipe',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: false,
  };
  let empty!: ReactTestRenderer.ReactTestRenderer;
  let whitespace!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    empty = ReactTestRenderer.create(<ConversationRow item={item} />);
    whitespace = ReactTestRenderer.create(
      <ConversationRow
        item={{...item, title: 'Whitespace category', category: ' \u0085 '}}
      />,
    );
  });
  expect(textOf(empty)).toContain('Empty category talk');
  expect(textOf(empty)).not.toContain('Screenpipe');
  expect(textOf(whitespace)).toContain('Screenpipe');
});

test('library conversation rows name Flutter ConversationListItem discarded photos only', () => {
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'omi-photos',
    title: 'Morning standup',
    summary: 'Notes',
    searchableText: 'Morning standup\nNotes',
    createdAt: '2026-09-07T00:00:00.000Z',
    updatedAt: '2026-09-07T00:01:00.000Z',
    startedAt: '2026-09-07T00:00:00.000Z',
    finishedAt: '2026-09-07T00:01:00.000Z',
    starred: false,
    status: 'completed',
    source: 'omi',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: true,
    photoCount: 2,
  };
  let shown!: ReactTestRenderer.ReactTestRenderer;
  let hidden!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    shown = ReactTestRenderer.create(<ConversationRow item={item} />);
    hidden = ReactTestRenderer.create(
      <ConversationRow item={{...item, discarded: false, photoCount: 3}} />,
    );
  });
  expect(textOf(shown)).toContain('2 photos');
  expect(textOf(hidden)).not.toContain('3 photos');
  expect(textOf(hidden)).not.toContain('2 photos');
});
