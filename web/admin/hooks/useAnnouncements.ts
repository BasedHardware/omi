'use client';

import useSWR from 'swr';
import { useAuthToken, authenticatedFetcher, useAuthFetch } from '@/hooks/useAuthToken';

export type AnnouncementType = 'changelog' | 'feature' | 'announcement';

export interface ChangelogItem {
  title: string;
  description: string;
  icon?: string;
}

export interface ChangelogContent {
  title: string;
  changes: ChangelogItem[];
}

export interface FeatureStep {
  title: string;
  description: string;
  image_url?: string;
  video_url?: string;
  highlight_text?: string;
}

export interface FeatureContent {
  title: string;
  steps: FeatureStep[];
}

export interface AnnouncementCTA {
  text: string;
  action: string;
}

export interface AnnouncementContent {
  title: string;
  body: string;
  image_url?: string;
  cta?: AnnouncementCTA;
}

export type TriggerType = 'immediate' | 'version_upgrade' | 'firmware_upgrade';
export type PlatformType = 'ios' | 'android';

export interface AnnouncementTargeting {
  app_version_min?: string;
  app_version_max?: string;
  firmware_version_min?: string;
  firmware_version_max?: string;
  device_models?: string[];
  platforms?: PlatformType[];
  trigger?: TriggerType;
  test_uids?: string[]; // If set, only these users see the announcement (for testing)
}

export interface AnnouncementDisplay {
  priority?: number;
  start_at?: string;
  expires_at?: string;
  dismissible?: boolean;
  show_once?: boolean;
}

export interface Announcement {
  id: string;
  type: AnnouncementType;
  created_at: string;
  active: boolean;
  // Legacy fields (kept for backward compatibility)
  app_version?: string;
  firmware_version?: string;
  device_models?: string[];
  expires_at?: string;
  // New optional targeting and display fields
  targeting?: AnnouncementTargeting;
  display?: AnnouncementDisplay;
  content: ChangelogContent | FeatureContent | AnnouncementContent;
}

export interface CreateAnnouncementData {
  type: AnnouncementType;
  // Legacy fields
  app_version?: string;
  firmware_version?: string;
  device_models?: string[];
  expires_at?: string;
  // New optional targeting and display fields
  targeting?: AnnouncementTargeting;
  display?: AnnouncementDisplay;
  content: ChangelogContent | FeatureContent | AnnouncementContent;
}

export interface UpdateAnnouncementData {
  active?: boolean;
  // Legacy fields
  app_version?: string;
  firmware_version?: string;
  device_models?: string[];
  expires_at?: string;
  // New optional targeting and display fields
  targeting?: AnnouncementTargeting;
  display?: AnnouncementDisplay;
  content?: ChangelogContent | FeatureContent | AnnouncementContent;
}

export function useAnnouncements(typeFilter?: AnnouncementType) {
  const { token, loading: tokenLoading } = useAuthToken();
  const { fetchWithAuth } = useAuthFetch();

  const url = typeFilter ? `/api/omi/announcements?type=${typeFilter}` : '/api/omi/announcements';

  const swrKey = token ? [url, token] : null;
  const { data, error, isLoading, mutate } = useSWR<Announcement[]>(swrKey, authenticatedFetcher, {
    revalidateOnFocus: false,
  });

  const createAnnouncement = async (announcementData: CreateAnnouncementData) => {
    const id = crypto.randomUUID();

    const res = await fetchWithAuth('/api/omi/announcements', {
      method: 'POST',
      body: JSON.stringify({ ...announcementData, id }),
    });

    if (!res.ok) {
      let message = `HTTP ${res.status}`;
      try {
        const j = await res.json();
        message = j?.error || j?.message || message;
      } catch {}
      throw new Error(message);
    }

    const result = await res.json();
    mutate();
    return result;
  };

  const updateAnnouncement = async (id: string, updates: UpdateAnnouncementData) => {
    const res = await fetchWithAuth(`/api/omi/announcements/${id}`, {
      method: 'PUT',
      body: JSON.stringify(updates),
    });

    if (!res.ok) {
      let message = `HTTP ${res.status}`;
      try {
        const j = await res.json();
        message = j?.error || j?.message || message;
      } catch {}
      throw new Error(message);
    }

    const result = await res.json();
    mutate();
    return result;
  };

  const deleteAnnouncement = async (id: string, hardDelete = false) => {
    const res = await fetchWithAuth(`/api/omi/announcements/${id}?hard=${hardDelete}`, {
      method: 'DELETE',
    });

    if (!res.ok) {
      let message = `HTTP ${res.status}`;
      try {
        const j = await res.json();
        message = j?.error || j?.message || message;
      } catch {}
      throw new Error(message);
    }

    mutate();
    return true;
  };

  const toggleActive = async (id: string, active: boolean) => {
    // Optimistic update - update UI immediately
    const previousData = data;
    mutate(
      data?.map((a) => (a.id === id ? { ...a, active } : a)),
      false // Don't revalidate yet
    );

    try {
      await updateAnnouncement(id, { active });
    } catch (error) {
      // Revert on error
      mutate(previousData, false);
      throw error;
    }
  };

  return {
    announcements: data || [],
    isLoading: tokenLoading || isLoading,
    error,
    mutate,
    createAnnouncement,
    updateAnnouncement,
    deleteAnnouncement,
    toggleActive,
  };
}
