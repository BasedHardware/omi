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
  created_at: string;
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
  created_at: string;
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
