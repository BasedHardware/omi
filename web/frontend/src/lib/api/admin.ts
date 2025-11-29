import { Plugin } from '@/src/app/apps/components/types';

export interface UnapprovedApp extends Plugin {
  uid: string;
  created_at: any;
  updated_at: any;
}

export interface PlatformAnalytics {
  users_count: number;
  memories_count: number;
  conversations_count: number;
  apps_count: number;
}

/**
 * Get all unapproved public apps (admin only)
 * Uses Next.js API proxy to avoid CORS issues
 */
export async function getUnapprovedApps(adminKey: string): Promise<UnapprovedApp[]> {
  const response = await fetch('/api/admin/apps', {
    headers: {
      'x-admin-key': adminKey,
    },
    cache: 'no-store', // Never cache admin data
  });

  if (!response.ok) {
    if (response.status === 403 || response.status === 401) {
      throw new Error('Unauthorized: Invalid admin key');
    }
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.error || `Failed to fetch unapproved apps: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Approve an app (admin only)
 * Uses Next.js API proxy to avoid CORS issues
 */
export async function approveApp(
  appId: string,
  uid: string,
  adminKey: string,
): Promise<{ status: string }> {
  const response = await fetch(`/api/admin/apps/${appId}/approve?uid=${uid}`, {
    method: 'POST',
    headers: {
      'x-admin-key': adminKey,
    },
  });

  if (!response.ok) {
    if (response.status === 403 || response.status === 401) {
      throw new Error('Unauthorized: Invalid admin key');
    }
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.error || `Failed to approve app: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Reject an app (admin only)
 * Uses Next.js API proxy to avoid CORS issues
 */
export async function rejectApp(
  appId: string,
  uid: string,
  adminKey: string,
): Promise<{ status: string }> {
  const response = await fetch(`/api/admin/apps/${appId}/reject?uid=${uid}`, {
    method: 'POST',
    headers: {
      'x-admin-key': adminKey,
    },
  });

  if (!response.ok) {
    if (response.status === 403 || response.status === 401) {
      throw new Error('Unauthorized: Invalid admin key');
    }
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.error || `Failed to reject app: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Set app as popular (admin only)
 * Uses Next.js API proxy to avoid CORS issues
 */
export async function setAppPopular(
  appId: string,
  value: boolean,
  adminKey: string,
): Promise<{ status: string }> {
  const response = await fetch(`/api/admin/apps/${appId}/popular?value=${value}`, {
    method: 'PATCH',
    headers: {
      'x-admin-key': adminKey,
    },
  });

  if (!response.ok) {
    if (response.status === 403 || response.status === 401) {
      throw new Error('Unauthorized: Invalid admin key');
    }
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.error || `Failed to update app popularity: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get platform-wide analytics (admin only)
 * Uses Next.js API proxy to avoid CORS issues
 */
export async function getPlatformAnalytics(adminKey: string): Promise<PlatformAnalytics> {
  const response = await fetch('/api/admin/analytics', {
    headers: {
      'x-admin-key': adminKey,
    },
    cache: 'no-store',
  });

  if (!response.ok) {
    if (response.status === 403 || response.status === 401) {
      throw new Error('Unauthorized: Invalid admin key');
    }
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.error || `Failed to fetch analytics: ${response.statusText}`);
  }

  return response.json();
}
