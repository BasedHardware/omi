import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

// Mock useAuth
const mockUser = {
  getIdToken: vi.fn(),
};

vi.mock('@/components/auth-provider', () => ({
  useAuth: vi.fn(() => ({ user: mockUser, loading: false })),
}));

import { useAuth } from '@/components/auth-provider';
import { useAuthToken, authenticatedFetcher, useAuthFetch } from '../useAuthToken';

describe('useAuthToken', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUser.getIdToken.mockResolvedValue('test-token-123');
  });

  it('returns token after user resolves', async () => {
    const { result } = renderHook(() => useAuthToken());
    await waitFor(() => expect(result.current.token).toBe('test-token-123'));
    expect(result.current.loading).toBe(false);
  });

  it('returns null when getIdToken fails', async () => {
    mockUser.getIdToken.mockRejectedValue(new Error('auth error'));
    const { result } = renderHook(() => useAuthToken());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.token).toBeNull();
  });

  it('returns null when no user', async () => {
    vi.mocked(useAuth).mockReturnValue({ user: null, loading: false, isAdmin: false } as any);
    const { result } = renderHook(() => useAuthToken());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.token).toBeNull();
  });
});

describe('authenticatedFetcher', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('sends Authorization header and returns JSON', async () => {
    const mockResponse = { data: 'test' };
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockResponse),
    });

    const result = await authenticatedFetcher(['/api/test', 'my-token']);
    expect(global.fetch).toHaveBeenCalledWith('/api/test', expect.objectContaining({
      headers: {
        Authorization: 'Bearer my-token',
        'Content-Type': 'application/json',
      },
    }));
    expect(result).toEqual(mockResponse);
  });

  it('throws on non-ok response', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: () => Promise.resolve({ error: 'unauthorized' }),
    });

    await expect(authenticatedFetcher(['/api/test', 'bad-token'])).rejects.toThrow();
  });
});

describe('useAuthFetch', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUser.getIdToken.mockResolvedValue('fetch-token');
    vi.mocked(useAuth).mockReturnValue({ user: mockUser, loading: false, isAdmin: true } as any);
    global.fetch = vi.fn().mockResolvedValue({ ok: true });
  });

  it('adds Authorization header to requests', async () => {
    const { result } = renderHook(() => useAuthFetch());
    await waitFor(() => expect(result.current.token).toBe('fetch-token'));

    await result.current.fetchWithAuth('/api/test', { method: 'POST', body: JSON.stringify({ a: 1 }) });

    expect(global.fetch).toHaveBeenCalledWith('/api/test', expect.objectContaining({
      method: 'POST',
      headers: expect.objectContaining({
        Authorization: 'Bearer fetch-token',
        'Content-Type': 'application/json',
      }),
    }));
  });

  it('preserves caller headers', async () => {
    const { result } = renderHook(() => useAuthFetch());
    await waitFor(() => expect(result.current.token).toBe('fetch-token'));

    await result.current.fetchWithAuth('/api/test', {
      headers: { 'X-Custom': 'value' } as any,
    });

    expect(global.fetch).toHaveBeenCalledWith('/api/test', expect.objectContaining({
      headers: expect.objectContaining({
        'X-Custom': 'value',
        Authorization: 'Bearer fetch-token',
      }),
    }));
  });

  it('retries with fresh token on 401', async () => {
    mockUser.getIdToken
      .mockResolvedValueOnce('stale-token')
      .mockResolvedValueOnce('fresh-token');
    vi.mocked(useAuth).mockReturnValue({ user: mockUser, loading: false, isAdmin: true } as any);

    global.fetch = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 401 })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ success: true }) });

    const { result } = renderHook(() => useAuthFetch());
    await waitFor(() => expect(result.current.token).toBe('stale-token'));

    const response = await result.current.fetchWithAuth('/api/test');
    expect(response.ok).toBe(true);
    expect(global.fetch).toHaveBeenCalledTimes(2);
  });

  it('skips Content-Type for FormData', async () => {
    const { result } = renderHook(() => useAuthFetch());
    await waitFor(() => expect(result.current.token).toBe('fetch-token'));

    const formData = new FormData();
    formData.append('file', 'test');
    await result.current.fetchWithAuth('/api/upload', { method: 'POST', body: formData });

    const call = vi.mocked(global.fetch).mock.calls[0];
    const headers = call[1]?.headers as Record<string, string>;
    expect(headers['Content-Type']).toBeUndefined();
    expect(headers['Authorization']).toBe('Bearer fetch-token');
  });
});
