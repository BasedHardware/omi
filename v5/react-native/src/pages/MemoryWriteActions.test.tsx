import React from 'react';
import Renderer, {act} from 'react-test-renderer';
import {Text} from 'react-native';
import type {
  DomainReadOutcome,
  MemoryProjection,
  ReadPageState,
} from '../desktopReadClient';

const mockRequest = jest.fn();
const mockLoadMemories = jest.fn();
jest.mock('../omiNative', () => ({
  omiBackend: {
    getApiContract: async () => 'omi',
    request: (...args: unknown[]) => mockRequest(...args),
  },
}));
jest.mock('../desktopReadClient', () => ({
  loadMemories: (...args: unknown[]) => mockLoadMemories(...args),
}));
import {MemoriesPage} from './Memories';

const mounted: Renderer.ReactTestRenderer[] = [];

const memory: MemoryProjection = {
  kind: 'memory',
  id: 'memory-1',
  title: 'A fact',
  summary: 'A fact',
  searchableText: 'A fact',
  visibility: 'private',
  citations: [],
  timestamp: null,
  provenance: {
    label: null,
    synthesisVersion: null,
    inputDigest: null,
    outputDigest: null,
  },
};
const page: ReadPageState = {
  windowStatus: 'complete',
  complete: true,
  hasMore: false,
  nextCursor: null,
  completenessStatus: 'complete',
  reasons: [],
};
const outcome = (
  items: MemoryProjection[],
): DomainReadOutcome<MemoryProjection> => ({
  status: 'success',
  value: {
    apiContract: 'omi',
    items,
    page,
  },
});
const press = (view: Renderer.ReactTestRenderer, label: string) =>
  view.root
    .find(node => node.props.accessibilityLabel === label)
    .props.onPress();
const textInput = (view: Renderer.ReactTestRenderer, label: string) =>
  view.root.find(node => node.props.accessibilityLabel === label);

beforeEach(() => {
  mockRequest.mockReset();
  mockRequest.mockResolvedValue({status: 200, body: '{"status":"ok"}'});
  mockLoadMemories.mockReset();
  mockLoadMemories.mockResolvedValue({
    items: [memory],
    page,
  });
});

afterEach(() => {
  for (const view of mounted.splice(0)) {
    act(() => view.unmount());
  }
});

test('desktop Memories creates a memory and refreshes the read adapter', async () => {
  const created = {...memory, id: 'memory-created'};
  mockRequest.mockResolvedValueOnce({
    status: 200,
    body: JSON.stringify({id: created.id, content: created.summary}),
  });
  mockLoadMemories.mockResolvedValueOnce({
    items: [created],
    page,
  });
  let view!: Renderer.ReactTestRenderer;
  act(() => {
    view = Renderer.create(
      <MemoriesPage outcome={outcome([])} loading={false} />,
    );
  });
  mounted.push(view);
  act(() => {
    textInput(view, 'New memory content').props.onChangeText('Remember this');
  });
  await act(async () => {
    press(view, 'Add memory');
  });
  expect(mockRequest).toHaveBeenCalledWith(
    expect.objectContaining({
      method: 'POST',
      path: '/v3/memories',
      body: '{"content":"Remember this","category":"manual","visibility":"private","tags":[]}',
    }),
  );
  expect(mockLoadMemories).toHaveBeenCalledTimes(1);
  expect(
    view.root
      .findAllByType(Text)
      .some(node => node.props.children === 'A fact'),
  ).toBe(true);
});

test('desktop memory detail supports edit and refreshes after saving', async () => {
  let view!: Renderer.ReactTestRenderer;
  act(() => {
    view = Renderer.create(
      <MemoriesPage outcome={outcome([memory])} loading={false} />,
    );
  });
  mounted.push(view);
  act(() => press(view, 'Open memory A fact'));
  await act(async () => {
    press(view, 'Edit memory');
  });
  act(() => {
    textInput(view, 'Edit memory content').props.onChangeText('Updated fact');
  });
  await act(async () => {
    press(view, 'Save memory');
  });
  expect(mockRequest).toHaveBeenCalledWith(
    expect.objectContaining({
      method: 'PATCH',
      path: '/v3/memories/memory-1',
      body: '{"value":"Updated fact"}',
    }),
  );
  expect(mockLoadMemories).toHaveBeenCalledTimes(1);
});

test('desktop memory detail confirms deletion and refreshes on legacy 404', async () => {
  mockRequest.mockResolvedValueOnce({status: 404, body: '{"detail":"gone"}'});
  let view!: Renderer.ReactTestRenderer;
  act(() => {
    view = Renderer.create(
      <MemoriesPage outcome={outcome([memory])} loading={false} />,
    );
  });
  mounted.push(view);
  act(() => press(view, 'Open memory A fact'));
  await act(async () => {
    press(view, 'Delete memory');
  });
  expect(
    view.root
      .findAllByType(Text)
      .some(node => node.props.children === 'Delete this memory?'),
  ).toBe(true);
  await act(async () => press(view, 'Confirm delete memory'));
  expect(mockRequest).toHaveBeenCalledWith(
    expect.objectContaining({method: 'DELETE', path: '/v3/memories/memory-1'}),
  );
  expect(mockLoadMemories).toHaveBeenCalledTimes(1);
});

test('desktop memory detail changes visibility and refreshes', async () => {
  let view!: Renderer.ReactTestRenderer;
  act(() => {
    view = Renderer.create(
      <MemoriesPage outcome={outcome([memory])} loading={false} />,
    );
  });
  mounted.push(view);
  act(() => press(view, 'Open memory A fact'));
  await act(async () => press(view, 'Make memory public'));
  expect(mockRequest).toHaveBeenCalledWith(
    expect.objectContaining({
      method: 'PATCH',
      path: '/v3/memories/memory-1/visibility',
      body: '{"value":"public"}',
    }),
  );
  expect(mockLoadMemories).toHaveBeenCalledTimes(1);
});
