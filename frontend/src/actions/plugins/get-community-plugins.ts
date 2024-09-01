'use server';

import { CommunityPlugin } from '@/src/types/plugins/plugins.types';

export default async function getCummunityPlugins() {
  const response = await fetch(
    'https://raw.githubusercontent.com/BasedHardware/Omi/main/community-plugins.json',
    {
      next: { revalidate: 24 * 60 * 60 },
    },
  );
  return (await response.json()) as CommunityPlugin[];
}

export async function getCommunityPlugin(pluginId: string) {
  const plugins = await getCummunityPlugins();

  const plugin = plugins.find((plugin) => plugin.id === pluginId);

  if (!plugin) return undefined;

  return plugins.find((plugin) => plugin.id === pluginId);
}
