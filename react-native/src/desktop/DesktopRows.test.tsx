import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {Text} from 'react-native';
import {
  formatTaskDue,
  clockLabel,
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
  expect(copy).not.toContain('Synthesized memory');
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
  expect(copy).toContain('Synthesized memory');
  expect(copy).not.toContain('citation-v1:launch');
  expect(copy).not.toContain('input');
  expect(copy).not.toContain('output');
  expect(copy).not.toMatch(/(^| )Memory( |$)/);
});

test('Home currents omit synthesized-memory chrome when GET synthesisVersion is missing', () => {
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
      synthesisVersion: ' \t\n',
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
  expect(copy).toContain('1 citation');
  expect(copy).not.toContain('Synthesized memory');
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
      [node.props.style].flat(Infinity).some(
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

test('Home and Library rows keep GET capture time instead of started-only', () => {
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
    expect(copy).toContain(expected);
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

test('Home and Library rows keep GET locked and discarded flags instead of title-only', () => {
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
    expect(copy).toContain('Discarded');
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

test('Home and Library rows keep GET failed status instead of title-only', () => {
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
    expect(copy).toContain('Conversation title unavailable');
    expect(copy).toContain('Failed');
    expect(copy).not.toContain('In progress');
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

test('library conversation rows name GET emoji and omit discarded or empty values', () => {
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
  act(() => {
    shown = ReactTestRenderer.create(<ConversationRow item={item} />);
    hidden = ReactTestRenderer.create(
      <ConversationRow item={{...item, discarded: true, emoji: '🧠'}} />,
    );
  });
  expect(textOf(shown)).toContain('🚀');
  expect(textOf(hidden)).not.toContain('🚀');
  expect(textOf(hidden)).not.toContain('🧠');
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

test('library conversation rows name discarded GET photo counts', () => {
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
