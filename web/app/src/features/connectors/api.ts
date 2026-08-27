import { getIdToken } from '@/lib/firebase';
import { getWebDeviceIdHash } from '@/lib/clientDevice';
import {
  invalidateCache,
  invalidationPatterns,
  fetchWithCache,
  cacheKeys,
  CACHE_TTL,
} from '@/lib/cache';
import {
  API_BASE_URL,
  fetchAuthorizedBlob,
  fetchWithAuth,
  getAudioAuthHeaders,
} from '@/shared/api/client';
import type {
  App,
  AppCategory,
  AppCapability,
  AppsGroupedResponse,
  AppsSearchResponse,
  AppsSearchParams,
  CreateAppRequest,
  UpdateAppRequest,
  ThumbnailUploadResponse,
  GenerateDescriptionResponse,
  NotificationScope,
  PaymentPlan,
} from '@/types/apps';
import type { Integration } from '@/types/user';
export type { App } from '@/types/apps';

export async function getAppsGrouped(
  params: {
    capability?: string;
    offset?: number;
    limit?: number;
  } = {},
): Promise<AppsGroupedResponse> {
  const { capability, offset = 0, limit = 20 } = params;

  const queryParams = new URLSearchParams({
    offset: offset.toString(),
    limit: limit.toString(),
  });

  if (capability) {
    queryParams.set('capability', capability);
  }

  return fetchWithAuth<AppsGroupedResponse>(`/v2/apps?${queryParams}`);
}

/**
 * Search apps with filters
 */
export async function searchApps(
  params: AppsSearchParams = {},
): Promise<AppsSearchResponse> {
  const queryParams = new URLSearchParams();

  if (params.q) queryParams.set('q', params.q);
  if (params.category) queryParams.set('category', params.category);
  if (params.capability) queryParams.set('capability', params.capability);
  if (params.rating !== undefined) queryParams.set('rating', params.rating.toString());
  if (params.sort) queryParams.set('sort', params.sort);
  if (params.my_apps) queryParams.set('my_apps', 'true');
  if (params.installed_apps) queryParams.set('installed_apps', 'true');
  queryParams.set('offset', (params.offset || 0).toString());
  queryParams.set('limit', (params.limit || 20).toString());

  return fetchWithAuth<AppsSearchResponse>(`/v2/apps/search?${queryParams}`);
}

/**
 * Get popular apps
 */
export async function getPopularApps(): Promise<App[]> {
  return fetchWithAuth<App[]>('/v1/apps/popular');
}

/**
 * Get a single app by ID
 */
export async function getApp(appId: string): Promise<App> {
  return fetchWithAuth<App>(`/v1/apps/${appId}`);
}

/**
 * Get app categories
 */
export async function getAppCategories(): Promise<AppCategory[]> {
  return fetchWithAuth<AppCategory[]>('/v1/app-categories');
}

/**
 * Get app capabilities
 */
export async function getAppCapabilities(): Promise<AppCapability[]> {
  return fetchWithAuth<AppCapability[]>('/v1/app-capabilities');
}

/**
 * Enable (install) an app
 */
export async function enableApp(appId: string): Promise<{ status: string }> {
  return fetchWithAuth<{ status: string }>(`/v1/apps/enable?app_id=${appId}`, {
    method: 'POST',
  });
}

/**
 * Disable (uninstall) an app
 */
export async function disableApp(appId: string): Promise<{ status: string }> {
  return fetchWithAuth<{ status: string }>(`/v1/apps/disable?app_id=${appId}`, {
    method: 'POST',
  });
}

/**
 * Get installed apps
 */
export async function getInstalledApps(): Promise<AppsSearchResponse> {
  return searchApps({ installed_apps: true, limit: 100 });
}

/**
 * Get chat-enabled apps (apps with 'chat' or 'persona' capability)
 */
export async function getChatApps(): Promise<App[]> {
  const response = await searchApps({ installed_apps: true, limit: 100 });
  return response.data.filter(
    (app) => app.capabilities?.includes('chat') || app.capabilities?.includes('persona'),
  );
}

// ============================================================================
// App Creation/Editing API
// ============================================================================

/**
 * Create a new app
 */
export async function createApp(
  data: CreateAppRequest & {
    deleted?: boolean;
    price?: number;
    thumbnails?: string[];
    uid?: string;
  },
  imageFile?: File,
): Promise<{ app_id: string }> {
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

  const url = `${API_BASE_URL}/v1/apps`;

  const formData = new FormData();
  formData.append('app_data', JSON.stringify(data));
  if (imageFile) {
    formData.append('file', imageFile, imageFile.name);
  }

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: formData,
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => 'No error body');
    console.error('Create app error:', response.status, errorText);
    throw new Error(`Failed to create app: ${response.status}`);
  }

  return response.json();
}

/**
 * Update an existing app
 */
export async function updateApp(
  appId: string,
  data: Partial<CreateAppRequest>,
  imageFile?: File,
): Promise<void> {
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

  const url = `${API_BASE_URL}/v1/apps/${appId}`;

  // The API requires the id to be included in the app_data
  const dataWithId = { ...data, id: appId };

  const formData = new FormData();
  formData.append('app_data', JSON.stringify(dataWithId));
  if (imageFile) {
    formData.append('file', imageFile, imageFile.name);
  }

  const response = await fetch(url, {
    method: 'PATCH',
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: formData,
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => 'No error body');
    console.error('Update app error:', response.status, errorText);
    throw new Error(`Failed to update app: ${response.status}`);
  }
}

/**
 * Re-enable an app that the backend auto-disabled after webhook failures.
 *
 * Sends `disabled: false` explicitly — the backend re-enable branch reads an
 * unset-exclusive payload, so omitting the field is a no-op rather than a
 * failure. The endpoint re-checks every configured URL and rejects the request
 * with a specific reason, so that detail is surfaced instead of the status code.
 */
export async function reEnableApp(appId: string): Promise<void> {
  const token = await getIdToken();
  if (!token) {
    throw new Error('Not authenticated');
  }

  const formData = new FormData();
  formData.append('app_data', JSON.stringify({ id: appId, disabled: false }));

  const response = await fetch(`${API_BASE_URL}/v1/apps/${appId}`, {
    method: 'PATCH',
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });

  if (!response.ok) {
    const detail = await response
      .json()
      .then((body) => body?.detail)
      .catch(() => null);
    throw new Error(detail || `Failed to re-enable app: ${response.status}`);
  }
}

/**
 * Delete an app
 */
export async function deleteApp(appId: string): Promise<void> {
  await fetchWithAuth(`/v1/apps/${appId}`, {
    method: 'DELETE',
  });
}

/**
 * Upload app thumbnail
 */
export async function uploadAppThumbnail(file: File): Promise<ThumbnailUploadResponse> {
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

  const url = `${API_BASE_URL}/v1/app/thumbnails`;

  const formData = new FormData();
  formData.append('file', file, file.name);

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: formData,
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => 'No error body');
    console.error('Upload thumbnail error:', response.status, errorText);
    throw new Error(`Failed to upload thumbnail: ${response.status}`);
  }

  return response.json();
}

/**
 * Generate app description using AI
 */
export async function generateAppDescription(
  name: string,
  currentDescription: string,
): Promise<string> {
  const response = await fetchWithAuth<GenerateDescriptionResponse>(
    '/v1/app/generate-description',
    {
      method: 'POST',
      body: JSON.stringify({ name, description: currentDescription }),
    },
  );
  return response.description;
}

/**
 * Generate app description and emoji using AI
 * Used for quick template creation (matches mobile app behavior)
 */
export async function generateAppDescriptionAndEmoji(
  name: string,
  prompt: string,
): Promise<{ description: string; emoji: string }> {
  try {
    const response = await fetchWithAuth<{
      description: string;
      emoji: string;
    }>('/v1/app/generate-description-emoji', {
      method: 'POST',
      body: JSON.stringify({ name, prompt }),
    });
    return {
      description: response.description || '',
      emoji: response.emoji || '✨',
    };
  } catch {
    // Fallback: generate description only and use default emoji
    const description = await generateAppDescription(name, prompt);
    return { description, emoji: '✨' };
  }
}

/**
 * Get proactive notification scopes
 * Note: This endpoint may not exist in all API versions, returns empty array on 404
 */
export async function getNotificationScopes(): Promise<NotificationScope[]> {
  try {
    const token = await getIdToken();
    if (!token) return [];

    const response = await fetch(
      `${API_BASE_URL}/v1/apps/proactive-notification-scopes`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
          'X-App-Platform': 'web',
        },
      },
    );

    if (!response.ok) return [];
    return response.json();
  } catch {
    return [];
  }
}

/**
 * Get available payment plans
 * Note: This endpoint may not exist in all API versions, returns empty array on 404
 */
export async function getPaymentPlans(): Promise<PaymentPlan[]> {
  try {
    const token = await getIdToken();
    if (!token) return [];

    const response = await fetch(`${API_BASE_URL}/v1/app/plans`, {
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
        'X-App-Platform': 'web',
      },
    });

    if (!response.ok) return [];
    return response.json();
  } catch {
    return [];
  }
}

// Integration definitions with logo paths
const INTEGRATION_DEFINITIONS: Array<{
  id: string;
  appKey: string;
  name: string;
  description: string;
  logo: string;
  coming_soon?: boolean;
}> = [
  {
    id: 'google_calendar',
    appKey: 'google_calendar',
    name: 'Google Calendar',
    description: 'Sync with your calendar',
    logo: '/integrations/google-calendar.png',
  },
  {
    id: 'whoop',
    appKey: 'whoop',
    name: 'Whoop',
    description: 'Health & fitness tracking',
    logo: '/integrations/whoop.png',
  },
  {
    id: 'notion',
    appKey: 'notion',
    name: 'Notion',
    description: 'Sync notes to Notion',
    logo: '/integrations/notion-logo.png',
  },
  {
    id: 'github',
    appKey: 'github',
    name: 'GitHub',
    description: 'Create issues and notes',
    logo: '/integrations/github-logo.png',
  },
  {
    id: 'twitter',
    appKey: 'twitter',
    name: 'X (Twitter)',
    description: 'Share to Twitter',
    logo: '/integrations/x-logo.avif',
  },
  {
    id: 'gmail',
    appKey: 'gmail',
    name: 'Gmail',
    description: 'Email integrations',
    logo: '/integrations/gmail-logo.jpeg',
  },
];

/**
 * Get individual integration connection status (like mobile app)
 */
async function getIntegrationStatus(appKey: string): Promise<{ connected: boolean }> {
  try {
    const response = await fetchWithAuth<{
      connected: boolean;
      app_key: string;
    }>(`/v1/integrations/${appKey}`);
    return { connected: response.connected ?? false };
  } catch {
    return { connected: false };
  }
}

/**
 * Get available integrations with connection status
 * Fetches individual integration statuses like the mobile app does
 */
export async function getIntegrations(): Promise<Integration[]> {
  // Fetch all integration statuses in parallel
  const statusPromises = INTEGRATION_DEFINITIONS.map(async (def) => {
    const status = await getIntegrationStatus(def.appKey);
    return {
      id: def.id,
      name: def.name,
      description: def.description,
      icon: def.logo,
      connected: status.connected,
      coming_soon: def.coming_soon,
    };
  });

  return Promise.all(statusPromises);
}

/**
 * Get OAuth URL for an integration
 * Opens the OAuth flow for the user to authorize
 */
export async function getIntegrationOAuthUrl(
  integrationId: string,
): Promise<string | null> {
  try {
    const response = await fetchWithAuth<{ auth_url: string }>(
      `/v1/integrations/${integrationId}/oauth-url`,
    );
    return response.auth_url || null;
  } catch {
    return null;
  }
}

/**
 * Disconnect an integration
 */
export async function disconnectIntegration(integrationId: string): Promise<void> {
  await fetchWithAuth(`/v1/integrations/${integrationId}`, {
    method: 'DELETE',
  });
}
