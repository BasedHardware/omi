import { moonshineJson } from '@tschk/moonshine-next/server';
import Fuse from 'fuse.js';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'https://api.omi.me';

// In-memory cache
let appsCache: any[] | null = null;
let cacheTimestamp = 0;
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

async function getAllApps() {
  const now = Date.now();

  // Return cached data if valid
  if (appsCache && now - cacheTimestamp < CACHE_TTL) {
    return appsCache;
  }

  // Fetch fresh data
  const response = await fetch(`${API_BASE_URL}/v1/approved-apps`);

  if (!response.ok) {
    throw new Error('Failed to fetch apps');
  }

  const apps = await response.json();

  // Update cache
  appsCache = apps;
  cacheTimestamp = now;

  return apps;
}

export async function GET(request: Request) {
  try {
    const searchParams = new URL(request.url).searchParams;
    const query = searchParams.get('q');

    if (!query || query.trim().length === 0) {
      return moonshineJson({ results: [], count: 0, query: '' });
    }

    // Get all apps (from cache or fresh fetch)
    const allApps = await getAllApps();

    // Search with Fuse.js
    const fuse = new Fuse(allApps, {
      keys: ['name', 'description', 'author', 'category', 'capabilities'],
      threshold: 0.3,
      includeMatches: true,
    });

    const searchResults = fuse.search(query.trim());
    const results = searchResults.map((result) => result.item);

    return moonshineJson({
      results,
      count: results.length,
      query: query.trim(),
    });
  } catch (error) {
    console.error('Search error:', error);
    return moonshineJson(
      { error: 'Search failed', results: [], count: 0 },
      { status: 500 },
    );
  }
}
