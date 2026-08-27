import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { KnowledgeGraph } from '@/types/conversation';

vi.mock('@/features/memories/api', () => ({
  getKnowledgeGraph: vi.fn(),
  rebuildKnowledgeGraph: vi.fn(),
}));

const api = await import('@/features/memories/api');
const { useKnowledgeGraph } = await import('@/features/memories/useKnowledgeGraph');

function graph(): KnowledgeGraph {
  return {
    nodes: [
      {
        id: 'n1',
        label: 'Ada',
        node_type: 'person',
        aliases: [],
        memory_ids: ['m1'],
      },
    ],
    edges: [],
  } as unknown as KnowledgeGraph;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

describe('useKnowledgeGraph', () => {
  it('loads the graph and adds a center user node', async () => {
    vi.mocked(api.getKnowledgeGraph).mockResolvedValue(graph());
    const { result } = renderHook(() => useKnowledgeGraph());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.graphData?.nodes.map((node) => node.id)).toEqual(['user', 'n1']);
    expect(result.current.graphData?.links.some((link) => link.source === 'user')).toBe(
      true,
    );
  });

  it('selects a node without refetching', async () => {
    vi.mocked(api.getKnowledgeGraph).mockResolvedValue(graph());
    const { result } = renderHook(() => useKnowledgeGraph());
    await waitFor(() => expect(result.current.loading).toBe(false));

    const node = result.current.graphData?.nodes[1] ?? null;
    act(() => {
      result.current.selectNode(node);
    });

    expect(result.current.selectedNode?.id).toBe('n1');
    expect(api.getKnowledgeGraph).toHaveBeenCalledTimes(1);
  });
});
