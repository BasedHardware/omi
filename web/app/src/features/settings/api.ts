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
  DailySummarySettings,
  TranscriptionPreferences,
  DeveloperWebhooks,
  WebhookSettings,
  RecordingPermission,
  UserUsage,
  UserUsageResponse,
  UsageStats,
  AllUsageData,
  UserSubscription,
  UserSubscriptionResponse,
  DeveloperApiKey,
  McpApiKey,
  AvailablePlansResponse,
  CheckoutSessionResponse,
  UpgradeSubscriptionResponse,
  CancelSubscriptionResponse,
  CustomerPortalResponse,
} from '@/types/user';
import { decodePlan, planGrantsPaidCapability } from '@/types/user';

export type WebhookType =
  'memory_created' | 'realtime_transcript' | 'audio_bytes' | 'day_summary';

export async function getUserLanguage(): Promise<string> {
  const response = await fetchWithAuth<{ language: string }>('/v1/users/language');
  return response.language;
}

/**
 * Set user's primary language
 */
export async function setUserLanguage(language: string): Promise<void> {
  await fetchWithAuth('/v1/users/language', {
    method: 'PATCH',
    body: JSON.stringify({ language }),
  });
}

/**
 * Get daily summary settings
 */
export async function getDailySummarySettings(): Promise<DailySummarySettings> {
  return fetchWithAuth<DailySummarySettings>('/v1/users/daily-summary-settings');
}

/**
 * Update daily summary settings
 */
export async function updateDailySummarySettings(
  settings: DailySummarySettings,
): Promise<void> {
  await fetchWithAuth('/v1/users/daily-summary-settings', {
    method: 'PATCH',
    body: JSON.stringify(settings),
  });
}

// ============================================================================
// Daily Summaries (Recaps) API
// ============================================================================

import type { DailySummary } from '@/types/recap';
export async function getTranscriptionPreferences(): Promise<TranscriptionPreferences> {
  return fetchWithAuth<TranscriptionPreferences>('/v1/users/transcription-preferences');
}

/**
 * Get developer webhook URL
 */
export async function getDeveloperWebhook(type: WebhookType): Promise<WebhookSettings> {
  return fetchWithAuth<WebhookSettings>(`/v1/users/developer/webhook/${type}`);
}

/**
 * Set developer webhook URL
 */
export async function setDeveloperWebhook(type: WebhookType, url: string): Promise<void> {
  await fetchWithAuth(`/v1/users/developer/webhook/${type}`, {
    method: 'POST',
    body: JSON.stringify({ url }),
  });
}

/**
 * Enable developer webhook
 */
export async function enableDeveloperWebhook(type: WebhookType): Promise<void> {
  await fetchWithAuth(`/v1/users/developer/webhook/${type}/enable`, {
    method: 'POST',
  });
}

/**
 * Disable developer webhook
 */
export async function disableDeveloperWebhook(type: WebhookType): Promise<void> {
  await fetchWithAuth(`/v1/users/developer/webhook/${type}/disable`, {
    method: 'POST',
  });
}

/**
 * Get all webhook statuses
 */
export async function getDeveloperWebhooksStatus(): Promise<DeveloperWebhooks> {
  return fetchWithAuth<DeveloperWebhooks>('/v1/users/developer/webhooks/status');
}

/**
 * Get store recording permission
 */
export async function getRecordingPermission(): Promise<RecordingPermission> {
  return fetchWithAuth<RecordingPermission>('/v1/users/store-recording-permission');
}

/**
 * Set store recording permission
 */
export async function setRecordingPermission(enabled: boolean): Promise<void> {
  await fetchWithAuth(`/v1/users/store-recording-permission?value=${enabled}`, {
    method: 'POST',
  });
}

/**
 * Get user usage stats for a specific period
 */
export async function getUserUsage(
  period: 'today' | 'monthly' | 'yearly' | 'all_time' = 'monthly',
): Promise<UserUsage | null> {
  try {
    const response = await fetchWithAuth<UserUsageResponse>(
      `/v1/users/me/usage?period=${period}`,
    );

    // Extract the relevant period's stats
    let stats: UsageStats | undefined;
    if (period === 'all_time') {
      stats = response.all_time;
    } else if (period === 'yearly') {
      stats = response.yearly;
    } else if (period === 'monthly') {
      stats = response.monthly;
    } else if (period === 'today') {
      stats = response.today;
    }

    // Fallback to any available stats
    if (!stats) {
      stats = response.all_time || response.monthly || response.yearly || response.today;
    }

    // Return data if we have stats OR history - some periods might have history without aggregate stats
    if (stats || response.history?.length) {
      return {
        transcription_seconds: stats?.transcription_seconds || 0,
        words_transcribed: stats?.words_transcribed || 0,
        insights_gained: stats?.insights_gained || 0,
        memories_created: stats?.memories_created || 0,
        history: response.history,
      };
    }
    return null;
  } catch (error) {
    console.error('getUserUsage error:', error);
    return null;
  }
}

/**
 * Get all usage data for all periods (for tabs display)
 */
export async function getAllUsageData(): Promise<AllUsageData> {
  const [today, monthly, yearly, all_time] = await Promise.all([
    getUserUsage('today'),
    getUserUsage('monthly'),
    getUserUsage('yearly'),
    getUserUsage('all_time'),
  ]);
  return { today, monthly, yearly, all_time };
}

/**
 * Get user subscription info
 */
export async function getUserSubscription(): Promise<UserSubscription | null> {
  try {
    const response = await fetchWithAuth<UserSubscriptionResponse>(
      '/v1/users/me/subscription',
    );

    const plan = decodePlan(response.subscription?.plan);
    const result: UserSubscription = {
      plan: plan.raw ?? '',
      plan_identity: plan,
      status: response.subscription?.status || 'active',
      // Unknown plans are deliberately excluded. A future wire value must not
      // inherit paid capability merely because it is non-empty.
      is_unlimited: planGrantsPaidCapability(plan),
      current_period_end: response.subscription?.current_period_end,
      stripe_subscription_id: response.subscription?.stripe_subscription_id,
      cancel_at_period_end: response.subscription?.cancel_at_period_end,
      current_price_id: response.subscription?.current_price_id,
      features: response.subscription?.features || [],
    };
    return result;
  } catch (error) {
    console.error('getUserSubscription error:', error);
    return null;
  }
}

/**
 * Get available subscription plans
 */
export async function getAvailablePlans(): Promise<AvailablePlansResponse | null> {
  try {
    const response = await fetchWithAuth<AvailablePlansResponse>(
      '/v1/payments/available-plans',
    );
    return response;
  } catch (error) {
    console.error('getAvailablePlans error:', error);
    return null;
  }
}

/**
 * Create a checkout session for subscription
 */
export async function createCheckoutSession(
  priceId: string,
): Promise<CheckoutSessionResponse | null> {
  try {
    const response = await fetchWithAuth<CheckoutSessionResponse>(
      '/v1/payments/checkout-session',
      {
        method: 'POST',
        body: JSON.stringify({ price_id: priceId }),
      },
    );
    return response;
  } catch (error) {
    console.error('createCheckoutSession error:', error);
    return null;
  }
}

/**
 * Upgrade subscription to a different plan
 */
export async function upgradeSubscription(
  priceId: string,
): Promise<UpgradeSubscriptionResponse | null> {
  try {
    const response = await fetchWithAuth<UpgradeSubscriptionResponse>(
      '/v1/payments/upgrade-subscription',
      {
        method: 'POST',
        body: JSON.stringify({ price_id: priceId }),
      },
    );
    return response;
  } catch (error) {
    console.error('upgradeSubscription error:', error);
    return null;
  }
}

/**
 * Cancel subscription
 */
export async function cancelSubscription(): Promise<CancelSubscriptionResponse | null> {
  try {
    const response = await fetchWithAuth<CancelSubscriptionResponse>(
      '/v1/payments/subscription',
      {
        method: 'DELETE',
      },
    );
    return response;
  } catch (error) {
    console.error('cancelSubscription error:', error);
    return null;
  }
}

/**
 * Get customer portal URL for managing payment methods
 */
export async function getCustomerPortal(): Promise<CustomerPortalResponse | null> {
  try {
    const response = await fetchWithAuth<CustomerPortalResponse>(
      '/v1/payments/customer-portal',
      {
        method: 'POST',
      },
    );
    return response;
  } catch (error) {
    console.error('getCustomerPortal error:', error);
    return null;
  }
}

/**
 * Delete the signed-in account permanently
 */
export async function deleteAccount(): Promise<void> {
  await fetchWithAuth('/v1/users/delete-account', {
    method: 'DELETE',
  });
}

/**
 * Get training data opt-in status
 */
export async function getTrainingDataOptIn(): Promise<{ opted_in: boolean }> {
  return fetchWithAuth<{ opted_in: boolean }>('/v1/users/training-data-opt-in');
}

/**
 * Set training data opt-in
 */
export async function setTrainingDataOptIn(optIn: boolean): Promise<void> {
  await fetchWithAuth('/v1/users/training-data-opt-in', {
    method: 'POST',
    body: JSON.stringify({ opted_in: optIn }),
  });
}

/**
 * Get user's developer API keys
 */
export async function getDeveloperApiKeys(): Promise<DeveloperApiKey[]> {
  try {
    return await fetchWithAuth<DeveloperApiKey[]>('/v1/dev/keys');
  } catch {
    return [];
  }
}

/**
 * Create a new developer API key with optional scopes
 */
export async function createDeveloperApiKey(
  name: string,
  scopes?: string[],
): Promise<DeveloperApiKey> {
  const body: { name: string; scopes?: string[] } = { name };
  if (scopes && scopes.length > 0) {
    body.scopes = scopes;
  }
  return fetchWithAuth<DeveloperApiKey>('/v1/dev/keys', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

/**
 * Delete a developer API key
 */
export async function deleteDeveloperApiKey(keyId: string): Promise<void> {
  await fetchWithAuth(`/v1/dev/keys/${keyId}`, {
    method: 'DELETE',
  });
}

// ============================================================================
// MCP API Keys
// ============================================================================

/**
 * Get user's MCP API keys
 */
export async function getMcpApiKeys(): Promise<McpApiKey[]> {
  try {
    return await fetchWithAuth<McpApiKey[]>('/v1/mcp/keys');
  } catch {
    return [];
  }
}

/**
 * Create a new MCP API key
 */
export async function createMcpApiKey(name: string): Promise<McpApiKey> {
  return fetchWithAuth<McpApiKey>('/v1/mcp/keys', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

/**
 * Delete an MCP API key
 */
export async function deleteMcpApiKey(keyId: string): Promise<void> {
  await fetchWithAuth(`/v1/mcp/keys/${keyId}`, {
    method: 'DELETE',
  });
}

// ============================================================================
// Data Export & Knowledge Graph
// ============================================================================

/**
 * Export all user data as a downloadable JSON blob (streamed from backend).
 */
export async function exportAllData(): Promise<Blob> {
  return fetchAuthorizedBlob('/v1/users/export');
}

/**
 * Custom vocabulary words stored on transcription preferences
 */
export async function getCustomVocabulary(): Promise<string[]> {
  try {
    const result = await fetchWithAuth<TranscriptionPreferences>(
      '/v1/users/transcription-preferences',
    );
    return result.vocabulary || [];
  } catch {
    return [];
  }
}

/**
 * Update custom vocabulary words via transcription preferences
 */
export async function updateCustomVocabulary(words: string[]): Promise<void> {
  await fetchWithAuth('/v1/users/transcription-preferences', {
    method: 'PATCH',
    body: JSON.stringify({ vocabulary: words }),
  });
}
