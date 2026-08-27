import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Person } from '@/types/user';

vi.mock('@/features/conversations/api', () => ({
  getPeople: vi.fn(),
  createPerson: vi.fn(),
  updatePersonName: vi.fn(),
  deletePerson: vi.fn(),
}));

const api = await import('@/features/conversations/api');
const { usePeople } = await import('@/features/conversations/usePeople');

function person(overrides: Partial<Person> = {}): Person {
  return {
    id: 'p1',
    name: 'Ada',
    created_at: '2026-01-01T00:00:00Z',
    speech_samples_count: 0,
    ...overrides,
  };
}

async function renderLoaded(initial: Person[] = [person()]) {
  vi.mocked(api.getPeople).mockResolvedValue(initial);
  const view = renderHook(() => usePeople());
  await waitFor(() => expect(view.result.current.loading).toBe(false));
  return view;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

describe('usePeople', () => {
  it('loads people on mount', async () => {
    const { result } = await renderLoaded();
    expect(result.current.people.map((entry) => entry.name)).toEqual(['Ada']);
  });

  it('rolls a rename back when the server rejects it', async () => {
    const { result } = await renderLoaded();
    vi.mocked(api.updatePersonName).mockRejectedValue(new Error('conflict'));

    let succeeded = true;
    await act(async () => {
      succeeded = await result.current.updatePerson('p1', 'Grace');
    });

    expect(succeeded).toBe(false);
    expect(result.current.people[0].name).toBe('Ada');
    expect(result.current.error).toBe('conflict');
  });
});
