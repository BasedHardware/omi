import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
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
      status: 500,
      json: () => Promise.resolve({ error: 'server error' }),
    });

    await expect(authenticatedFetcher(['/api/test', 'bad-token'])).rejects.toThrow();
  });

  it('retries with fresh token on 401 when forceRefresh is registered', async () => {
    // First, render useAuthToken to register the module-level forceRefresh callback
    mockUser.getIdToken
      .mockResolvedValueOnce('stale-token')
      .mockResolvedValueOnce('fresh-token');
    vi.mocked(useAuth).mockReturnValue({ user: mockUser, loading: false, isAdmin: true } as any);

    const { result } = renderHook(() => useAuthToken());
    await waitFor(() => expect(result.current.token).toBe('stale-token'));

    // Now test authenticatedFetcher with a 401 → retry flow
    const mockData = { data: 'success' };
    global.fetch = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 401, json: () => Promise.resolve({ error: 'unauthorized' }) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(mockData) });

    const fetchResult = await authenticatedFetcher(['/api/test', 'stale-token']);
    expect(fetchResult).toEqual(mockData);
    expect(global.fetch).toHaveBeenCalledTimes(2);
    // Second call should use the fresh token
    expect(global.fetch).toHaveBeenLastCalledWith('/api/test', expect.objectContaining({
      headers: expect.objectContaining({ Authorization: 'Bearer fresh-token' }),
    }));
  });

  it('throws 401 when forceRefresh returns null', async () => {
    // Register forceRefresh with a user that fails to refresh
    vi.mocked(useAuth).mockReturnValue({ user: null, loading: false, isAdmin: false } as any);
    renderHook(() => useAuthToken());

    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: () => Promise.resolve({ error: 'unauthorized' }),
    });

    await expect(authenticatedFetcher(['/api/test', 'stale-token'])).rejects.toThrow();
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

  it('does not retry more than once on 401', async () => {
    mockUser.getIdToken
      .mockResolvedValueOnce('token-1')
      .mockResolvedValueOnce('token-2');
    vi.mocked(useAuth).mockReturnValue({ user: mockUser, loading: false, isAdmin: true } as any);

    // Both original and retry return 401
    global.fetch = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 401 })
      .mockResolvedValueOnce({ ok: false, status: 401 });

    const { result } = renderHook(() => useAuthFetch());
    await waitFor(() => expect(result.current.token).toBe('token-1'));

    const response = await result.current.fetchWithAuth('/api/test');
    expect(response.status).toBe(401);
    // Should only retry once (2 total calls), not loop
    expect(global.fetch).toHaveBeenCalledTimes(2);
  });
});

describe('authenticatedFetcher error objects', () => {
  it('throws error with status and info from non-ok response', async () => {
    const errorBody = { message: 'Forbidden', code: 'ACCESS_DENIED' };
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      json: () => Promise.resolve(errorBody),
    });

    try {
      await authenticatedFetcher(['/api/test', 'token']);
      expect.fail('should have thrown');
    } catch (error: any) {
      expect(error.status).toBe(403);
      expect(error.info).toEqual(errorBody);
    }
  });

  it('handles invalid JSON in error response gracefully', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: () => Promise.reject(new Error('invalid json')),
    });

    try {
      await authenticatedFetcher(['/api/test', 'token']);
      expect.fail('should have thrown');
    } catch (error: any) {
      expect(error.status).toBe(500);
      expect(error.info).toEqual({ message: 'Could not parse error JSON.' });
    }
  });
});

describe('useAuthToken ref-counting', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUser.getIdToken.mockResolvedValue('ref-token');
    vi.mocked(useAuth).mockReturnValue({ user: mockUser, loading: false, isAdmin: true } as any);
  });

  it('forceRefresh callback survives when one of multiple hooks unmounts', async () => {
    // Mount two hooks
    const hook1 = renderHook(() => useAuthToken());
    const hook2 = renderHook(() => useAuthToken());
    await waitFor(() => expect(hook1.result.current.token).toBe('ref-token'));
    await waitFor(() => expect(hook2.result.current.token).toBe('ref-token'));

    // Unmount one — callback should still work
    hook1.unmount();

    // Set up a 401 scenario to test the callback is still registered
    mockUser.getIdToken.mockResolvedValueOnce('fresh-after-unmount');
    global.fetch = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 401, json: () => Promise.resolve({}) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ ok: true }) });

    const result = await authenticatedFetcher(['/api/test', 'ref-token']);
    expect(result).toEqual({ ok: true });
    expect(global.fetch).toHaveBeenCalledTimes(2);
  });

  it('forceRefresh callback cleared when all hooks unmount', async () => {
    const hook1 = renderHook(() => useAuthToken());
    const hook2 = renderHook(() => useAuthToken());
    await waitFor(() => expect(hook1.result.current.token).toBe('ref-token'));
    await waitFor(() => expect(hook2.result.current.token).toBe('ref-token'));

    // Unmount both
    hook1.unmount();
    hook2.unmount();

    // 401 should not retry (callback is null) — should throw
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: () => Promise.resolve({ error: 'unauthorized' }),
    });

    await expect(authenticatedFetcher(['/api/test', 'ref-token'])).rejects.toThrow();
    // Should only have made 1 call (no retry)
    expect(global.fetch).toHaveBeenCalledTimes(1);
  });
});
