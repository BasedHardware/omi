/**
 * Public API module for marketplace
 * These endpoints don't require authentication
 */

// For public marketplace, use the configured API base URL or fallback to production
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'https://api.omi.me';

/**
 * Fetch approved apps for the public marketplace
 * Cached and doesn't require authentication
 */
export async function getApprovedApps(): Promise<{
  plugins: Array<{
    id: string;
    name: string;
    description: string;
    author: string;
    image: string;
    category: string;
    installs: number;
    rating_avg: number;
    rating_count: number;
    capabilities: string[];
    created_at: string;
    is_paid?: boolean;
    price?: number;
    payment_plan?: 'one_time' | 'monthly_recurring' | null;
    is_popular?: boolean;
  }>;
  stats: Array<{
    id: string;
    money: number;
  }>;
}> {
  try {
    const response = await fetch(`${API_BASE_URL}/v1/approved-apps?include_reviews=true`, {
      next: { revalidate: 300 }, // Cache for 5 minutes
    });

    if (!response.ok) {
      console.error('Failed to fetch approved apps:', response.status);
      return { plugins: [], stats: [] };
    }

    const data = await response.json();

    // Transform the data to include capabilities as an array
    return {
      plugins: data.plugins || data || [],
      stats: data.stats || [],
    };
  } catch (error) {
    console.error('Error fetching approved apps:', error);
    return { plugins: [], stats: [] };
  }
}

/**
 * Fetch a single app by ID for the public detail page
 * Fetches all apps and finds the matching one (since individual endpoint doesn't exist)
 * Cached and doesn't require authentication
 */
export async function getAppById(appId: string): Promise<{
  id: string;
  name: string;
  description: string;
  author: string;
  image: string;
  category: string;
  installs: number;
  rating_avg: number;
  rating_count: number;
  capabilities: string[];
  created_at: string;
  is_paid?: boolean;
  price?: number;
  payment_plan?: 'one_time' | 'monthly_recurring' | null;
  is_popular?: boolean;
  reviews?: Array<{
    id: string;
    user_name: string;
    rating: number;
    review: string;
    created_at: string;
  }>;
} | null> {
  try {
    // Fetch all approved apps and find the one by ID
    const { plugins } = await getApprovedApps();
    const app = plugins.find((p) => p.id === appId);
    return app || null;
  } catch (error) {
    console.error('Error fetching app:', error);
    return null;
  }
}

/**
 * Transform raw API data to Plugin format with Set for capabilities
 */
export function transformToPlugin(raw: {
  id: string;
  name: string;
  description: string;
  author: string;
  image: string;
  category: string;
  installs: number;
  rating_avg: number;
  rating_count: number;
  capabilities: string[];
  created_at: string | null;
  is_paid?: boolean;
  price?: number;
  payment_plan?: 'one_time' | 'monthly_recurring' | null;
  is_popular?: boolean;
}): {
  id: string;
  name: string;
  description: string;
  author: string;
  image: string;
  category: string;
  installs: number;
  rating_avg: number;
  rating_count: number;
  capabilities: Set<string>;
  created_at: string | null;
  is_paid?: boolean;
  price?: number;
  payment_plan?: 'one_time' | 'monthly_recurring' | null;
  is_popular?: boolean;
} {
  return {
    ...raw,
    capabilities: new Set(raw.capabilities || []),
  };
}

// ============================================================================
// V2 API Types and Functions
// ============================================================================

/**
 * V2 API type definitions for paginated app responses
 */

export interface V2PaginationInfo {
  total: number;
  count: number;
  offset: number;
  limit: number;
  hasNext: boolean;
  hasPrevious: boolean;
  links: {
    next: string | null;
    previous: string | null;
  };
}

export interface V2AppData {
  id: string;
  name: string;
  description: string;
  author: string;
  image: string;
  category: string;
  installs: number;
  rating_avg: number;
  rating_count: number;
  capabilities: string[];
  created_at: string | null;
  is_paid?: boolean;
  price?: number;
  payment_plan?: 'one_time' | 'monthly_recurring' | null;
  is_popular?: boolean;
  approved?: boolean;
  status?: string;
  uid?: string | null;
  private?: boolean;
  enabled?: boolean;
  trigger_workflow_memories?: boolean;
  score?: number;
  proactive_notification?: any;
  external_integration?: any;
  username?: string;
  connected_accounts?: any[];
  chat_tools?: any[];
  thumbnails?: any[];
  thumbnail_urls?: string[];
  is_influencer?: boolean;
  is_user_paid?: boolean;
  payment_link?: string | null;
}

export interface V2CapabilityGroup {
  capability: {
    id: string;
    title: string;
  };
  data: V2AppData[];
  pagination: V2PaginationInfo;
}

export interface V2AppsResponse {
  groups: V2CapabilityGroup[];
  meta: {
    capabilities: Array<{
      id: string;
      title: string;
    }>;
    groupCount: number;
    limit: number;
    offset: number;
  };
}

export interface V2SingleCapabilityResponse {
  data: V2AppData[];
  pagination: V2PaginationInfo;
  capability: {
    id: string;
    title: string;
  };
}

/**
 * Fetch apps from v2/apps endpoint (grouped by capability)
 * Returns paginated groups of apps (much smaller than v1)
 * @param includeReviews - Whether to include review data (default: false)
 */
export async function getAppsV2(includeReviews = false): Promise<V2AppsResponse> {
  try {
    const url = `${API_BASE_URL}/v2/apps${includeReviews ? '?include_reviews=true' : ''}`;
    const response = await fetch(url, {
      next: { revalidate: 300 }, // Cache for 5 minutes
    });

    if (!response.ok) {
      console.error('Failed to fetch v2 apps:', response.status);
      return { groups: [], meta: { capabilities: [], groupCount: 0, limit: 20, offset: 0 } };
    }

    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Error fetching v2 apps:', error);
    return { groups: [], meta: { capabilities: [], groupCount: 0, limit: 20, offset: 0 } };
  }
}

/**
 * Fetch apps for a specific capability from v2/apps endpoint
 * @param capability - The capability ID (e.g., 'chat', 'memories', 'external_integration')
 * @param offset - Pagination offset (default: 0)
 * @param limit - Number of items per page (default: 50, max: 50)
 * @param includeReviews - Whether to include review data (default: false)
 */
export async function getAppsByCapability(
  capability: string,
  offset = 0,
  limit = 50,
  includeReviews = false
): Promise<V2SingleCapabilityResponse> {
  try {
    const params = new URLSearchParams({
      capability,
      offset: offset.toString(),
      limit: limit.toString(),
    });

    if (includeReviews) {
      params.append('include_reviews', 'true');
    }

    const url = `${API_BASE_URL}/v2/apps?${params.toString()}`;
    const response = await fetch(url, {
      next: { revalidate: 300 }, // Cache for 5 minutes
    });

    if (!response.ok) {
      console.error(`Failed to fetch apps for capability ${capability}:`, response.status);
      return {
        data: [],
        pagination: {
          total: 0,
          count: 0,
          offset: 0,
          limit: limit,
          hasNext: false,
          hasPrevious: false,
          links: { next: null, previous: null },
        },
        capability: { id: capability, title: capability },
      };
    }

    const data = await response.json();
    return data;
  } catch (error) {
    console.error(`Error fetching apps for capability ${capability}:`, error);
    return {
      data: [],
      pagination: {
        total: 0,
        count: 0,
        offset: 0,
        limit: limit,
        hasNext: false,
        hasPrevious: false,
        links: { next: null, previous: null },
      },
      capability: { id: capability, title: capability },
    };
  }
}

/**
 * Fetch ALL apps from v2 by paginating through all capability groups
 * This should only be used during build time for SSG
 * Makes multiple requests but ensures all apps are available
 * @param includeReviews - Whether to include review/rating data (default: false)
 */
export async function getAllAppsV2(includeReviews = false): Promise<V2AppData[]> {
  try {
    const allApps: V2AppData[] = [];
    const { groups } = await getAppsV2(includeReviews);

    console.log('Fetching all v2 apps with pagination...');

    // For each capability group
    for (const group of groups) {
      console.log(`- ${group.capability.id}: ${group.pagination.count} of ${group.pagination.total} apps`);

      // Add first page apps
      allApps.push(...group.data);

      // If there are more pages, fetch them
      if (group.pagination.hasNext) {
        const totalPages = Math.ceil(group.pagination.total / group.pagination.limit);

        // Fetch remaining pages
        for (let page = 1; page < totalPages; page++) {
          const offset = page * group.pagination.limit;
          const response = await getAppsByCapability(
            group.capability.id,
            offset,
            group.pagination.limit,
            includeReviews
          );

          console.log(`  Fetched page ${page + 1}/${totalPages} (${response.data.length} apps)`);
          allApps.push(...response.data);
        }
      }
    }

    console.log(`Total apps fetched: ${allApps.length}`);

    // Deduplicate apps by ID (apps can appear in multiple capability groups)
    const uniqueAppsMap = new Map<string, V2AppData>();
    for (const app of allApps) {
      if (!uniqueAppsMap.has(app.id)) {
        uniqueAppsMap.set(app.id, app);
      }
    }

    const uniqueApps = Array.from(uniqueAppsMap.values());
    console.log(`Unique apps after deduplication: ${uniqueApps.length}`);

    return uniqueApps;
  } catch (error) {
    console.error('Error fetching all v2 apps:', error);
    return [];
  }
}

/**
 * Find a specific app by ID from v2/apps response
 * Searches through ALL apps (paginated) to find the app
 * @param id - The app ID to search for
 */
export async function findAppById(id: string): Promise<V2AppData | null> {
  try {
    // Use getAllAppsV2 to search through all 625 apps, not just first 85
    // Include reviews to get rating data
    const allApps = await getAllAppsV2(true);
    const app = allApps.find((app) => app.id === id);
    return app || null;
  } catch (error) {
    console.error(`Error finding app by ID ${id}:`, error);
    return null;
  }
}
