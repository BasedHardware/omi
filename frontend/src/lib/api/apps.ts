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
  console.log('Starting getApprovedApps fetch...');
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 15000); // 15s timeout

  try {
    console.log('Fetching from API...');
    const response = await fetch(
      `${envConfig.API_URL}/v1/approved-apps?include_reviews=true`,
      {
        next: { revalidate: 3600 }, // Reduced to 1 hour
        signal: controller.signal,
        headers: {
          'Accept-Encoding': 'gzip',
        },
      },
    );

    clearTimeout(timeoutId);
    console.log(`API response status: ${response.status}`);

    if (!response.ok) {
      if (response.status === 429 && lastSuccessfulResponse) {
        console.log('Rate limit hit, using cached data');
        return lastSuccessfulResponse;
      }
      throw new Error(`Failed to fetch apps: ${response.statusText}`);
    }

    console.log('Starting response parsing...');
    // Get response as buffer for more efficient parsing
    const buffer = await response.arrayBuffer();
    const decoder = new TextDecoder();
    const text = decoder.decode(buffer);
    const plugins = JSON.parse(text) as Plugin[];
    console.log(`Successfully parsed ${plugins.length} plugins`);

    // Store successful response in memory
    lastSuccessfulResponse = plugins;
    return plugins;
  } catch (error: unknown) {
    clearTimeout(timeoutId);
    const err = error as Error;
    console.error('Error details:', {
      name: err.name,
      message: err.message,
      stack: err.stack,
    });

    if (err instanceof Error && err.name === 'AbortError') {
      console.log('Request timed out, using cached data');
      return lastSuccessfulResponse ?? [];
    }

    // Return cached data for any network errors if available
    if (lastSuccessfulResponse) {
      console.log('Error occurred, using cached data');
      return lastSuccessfulResponse;
    }

    console.log('No cached data available, returning empty array');
    return [];
  }
});

/**
 * Get a single app by ID using the cached data
 */
export const getAppById = cache(async (id: string): Promise<Plugin | undefined> => {
  const plugins = await getApprovedApps();
  return plugins.find((p) => p.id === id);
});

/**
 * Get apps by category using the cached data
 */
export const getAppsByCategory = cache(async (category: string): Promise<Plugin[]> => {
  const plugins = await getApprovedApps();
  return category === 'integration'
    ? plugins.filter(
        (plugin) =>
          Array.isArray(plugin.capabilities) &&
          plugin.capabilities.includes('external_integration'),
      )
    : plugins.filter((plugin) => plugin.category === category);
});
