import { CommunityPlugin } from '@/src/types/plugins/plugins.types';

// Simple in-memory cache for plugins
const pluginCache = new Map<string, CommunityPlugin | null>();

export const getPluginFromCache = (pluginId: string): CommunityPlugin | null | undefined => {
  return pluginCache.get(pluginId);
};

export const setPluginInCache = (pluginId: string, plugin: CommunityPlugin | null): void => {
  pluginCache.set(pluginId, plugin);
};

export const hasPluginInCache = (pluginId: string): boolean => {
  return pluginCache.has(pluginId);
}; 