import { getIdToken } from '@/lib/firebase';
import { getWebDeviceIdHash } from '@/lib/clientDevice';

/** Browser → `/api/proxy` → api.omi.me, so CORS never hits the origin. */
export const API_BASE_URL = '/api/proxy';

/**
 * Authenticated JSON (or empty) request against the API proxy.
 *
 * FormData must keep its own Content-Type so fetch can set the multipart
 * boundary; forcing application/json here produces a body the server cannot
 * parse.
 */
export async function fetchWithAuth<T>(
  endpoint: string,
  options: RequestInit = {},
): Promise<T> {
  let token: string | null = null;

  try {
    token = await getIdToken();
  } catch (tokenError) {
    console.error('Failed to get auth token:', tokenError);
    throw new Error('Failed to get authentication token');
  }

  if (!token) {
    throw new Error('Not authenticated');
  }

  const url = `${API_BASE_URL}${endpoint}`;
  const deviceIdHash = await getWebDeviceIdHash();
  const headers = new Headers({ Authorization: `Bearer ${token}` });
  if (!(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }
  new Headers(options.headers).forEach((value, name) => headers.set(name, value));
  headers.set('X-App-Platform', 'web');
  if (deviceIdHash) {
    headers.set('X-Device-Id-Hash', deviceIdHash);
  }

  try {
    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const errorText = await response.text().catch(() => 'No error body');
      if (response.status !== 404) {
        console.error('API error response:', response.status, errorText);
      }

      if (response.status === 401) {
        throw new Error('Unauthorized - please sign in again');
      }
      throw new Error(`API error: ${response.status} ${response.statusText}`);
    }

    if (response.status === 204) {
      return undefined as T;
    }

    return response.json();
  } catch (fetchError) {
    if (fetchError instanceof TypeError && fetchError.message === 'Failed to fetch') {
      console.error('Network error - possible CORS issue or API unavailable');
      throw new Error(
        'Network error: Unable to reach the API. Please check your connection.',
      );
    }
    throw fetchError;
  }
}

export async function fetchAuthorizedBlob(endpoint: string): Promise<Blob> {
  const token = await getIdToken();
  if (!token) {
    throw new Error('Not authenticated');
  }
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    throw new Error(`Export failed: ${response.status} ${response.statusText}`);
  }
  return response.blob();
}

export async function getAudioAuthHeaders(): Promise<Record<string, string>> {
  const token = await getIdToken();
  if (!token) {
    throw new Error('Not authenticated');
  }
  return {
    Authorization: `Bearer ${token}`,
  };
}
