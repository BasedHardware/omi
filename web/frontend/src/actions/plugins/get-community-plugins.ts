'use server';

import envConfig from '@/src/constants/envConfig';
import { CommunityPlugin } from '@/src/types/plugins/plugins.types';

async function getApprovedApps(): Promise<CommunityPlugin[]> {
  const apiUrl = envConfig.API_URL;
  const response = await fetch(`${apiUrl}/v1/approved-apps`, {
    next: { revalidate: 24 * 60 * 60 },
  });
  
  if (!response.ok) {
    throw new Error(`Failed to fetch approved apps: ${response.statusText}`);
  }
  
  return (await response.json()) as CommunityPlugin[];
}

export default async function getCommunityPlugins(): Promise<CommunityPlugin[]> {
  try {
    // First try to get approved apps from the API
    const approvedApps = await getApprovedApps();
    return approvedApps;
  } catch (error) {
    // Fallback to GitHub if API fails
    console.warn('Failed to fetch from approved-apps API, falling back to GitHub:', error);
    const response = await fetch(
      'https://raw.githubusercontent.com/BasedHardware/Omi/main/community-plugins.json',
      {
        next: { revalidate: 24 * 60 * 60 },
      },
    );
    return (await response.json()) as CommunityPlugin[];
  }
}

export async function getCommunityPlugin(pluginId: string): Promise<CommunityPlugin | undefined> {
  const plugins = await getCommunityPlugins();
  console.log(plugins);
  return plugins.find((plugin) => plugin.id === pluginId);
}
