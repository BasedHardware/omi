import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Memory } from '@/types/conversation';
import { clearAllCache } from '@/lib/cache';

vi.mock('@/features/memories/api', () => ({
  getMemories: vi.fn(),
  createMemory: vi.fn(),
  updateMemoryContent: vi.fn(),
  updateMemoryVisibility: vi.fn(),
  deleteMemory: vi.fn(),
  deleteMemoriesBatch: vi.fn(),
  reviewMemory: vi.fn(),
}));

vi.mock('@/lib/indexeddb', () => ({
  getCachedMemories: vi.fn().mockResolvedValue(null),
  cacheMemories: vi.fn().mockResolvedValue(undefined),
}));

const api = await import('@/features/memories/api');
const { useMemories } = await import('@/features/memories/useMemories');

function memory(overrides: Partial<Memory> = {}): Memory {
  return {
    id: 'm1',
    uid: 'u1',
    content: 'Remember this',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    layer: 'long_term',
    ...overrides,
  } as Memory;
}

async function renderLoaded(initial: Memory[] = [memory()]) {
  vi.mocked(api.getMemories).mockResolvedValue(initial);
  const view = renderHook(() => useMemories());
  await waitFor(() => expect(view.result.current.loading).toBe(false));
  return view;
}

beforeEach(() => {
  vi.clearAllMocks();
  clearAllCache();
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

describe('useMemories', () => {
  it('loads memories on mount', async () => {
    const { result } = await renderLoaded();
    expect(result.current.memories.map((entry) => entry.id)).toEqual(['m1']);
  });

  it('rolls content back when an edit is rejected', async () => {
    const { result } = await renderLoaded();
    vi.mocked(api.updateMemoryContent).mockRejectedValue(new Error('conflict'));

    let succeeded = true;
    await act(async () => {
      succeeded = await result.current.editMemory('m1', 'changed');
    });

    expect(succeeded).toBe(false);
    expect(result.current.memories[0]?.content).toBe('Remember this');
    expect(result.current.error).toBe('conflict');
  });
});
