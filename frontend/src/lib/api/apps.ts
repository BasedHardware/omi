import { cache } from 'react';
import envConfig from '@/src/constants/envConfig';
import { Plugin, PluginStat } from '@/src/app/apps/components/types';

// Store last successful response in memory
let lastSuccessfulResponse: Plugin[] | null = null;

/**
 * Cached fetch utility for approved apps
 * Uses React's cache() for route segment caching
 * Includes runtime caching for rate limit handling
 */
export const getApprovedApps = cache(async () => {
  try {
    const response = await fetch(
      `${envConfig.API_URL}/v1/approved-apps?include_reviews=true`,
      {
        next: { revalidate: 21600 }, // 6 hours
      },
    );

    if (!response.ok) {
      if (response.status === 429 && lastSuccessfulResponse) {
        console.log('Rate limit hit, using cached data');
        return lastSuccessfulResponse;
      }
      throw new Error(`Failed to fetch apps: ${response.statusText}`);
    }

    const plugins = (await response.json()) as Plugin[];
    // Store successful response in memory
    lastSuccessfulResponse = plugins;
    return plugins;
  } catch (error) {
    console.error('Error fetching approved apps:', error);
    // Return cached data for any network errors if available
    if (lastSuccessfulResponse) {
      console.log('Error occurred, using cached data');
      return lastSuccessfulResponse;
    }
    throw error;
  }
});

/**
 * Get a single app by ID using the cached data
 */
export const getAppById = cache(async (id: string) => {
  const plugins = await getApprovedApps();
  return plugins.find((p) => p.id === id);
});

/**
 * Get apps by category using the cached data
 */
export const getAppsByCategory = cache(async (category: string) => {
  const plugins = await getApprovedApps();
  return category === 'integration'
    ? plugins.filter(
        (plugin) =>
          Array.isArray(plugin.capabilities) &&
          plugin.capabilities.includes('external_integration'),
      )
    : plugins.filter((plugin) => plugin.category === category);
});
