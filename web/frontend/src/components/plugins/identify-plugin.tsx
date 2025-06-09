'use client';

import { getCommunityPlugin } from '@/src/actions/plugins/get-community-plugins';
import { CommunityPlugin } from '@/src/types/plugins/plugins.types';
import Image from 'next/image';
import { Fragment, useEffect, useState, memo } from 'react';
import ErrorIdentifyPlugin from './error-identify-plugin';
import IdentifyPluginLoader from './identify-plugin-loader';
import { getPluginFromCache, setPluginInCache, hasPluginInCache } from './plugin-cache';

interface IdentifyPluginProps {
  pluginId: string;
}

function IdentifyPlugin({ pluginId }: IdentifyPluginProps) {
  const [pluginCommunity, setPluginCommunity] = useState<CommunityPlugin | undefined>(
    undefined,
  );
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Check cache first
    if (hasPluginInCache(pluginId)) {
      const cachedPlugin = getPluginFromCache(pluginId);
      setPluginCommunity(cachedPlugin || undefined);
      setLoading(false);
      return;
    }

    // Fetch from API if not in cache
    setLoading(true);
    getCommunityPlugin(pluginId)
      .then((plugin) => {
        console.log(plugin);
        setPluginCommunity(plugin);
        setPluginInCache(pluginId, plugin || null);
      })
      .finally(() => setLoading(false));
  }, [pluginId]);

  if (loading) {
    return <IdentifyPluginLoader />;
  }

  if (!pluginCommunity) {
    return <ErrorIdentifyPlugin />;
  }

  return (
    <Fragment>
      <div className="sticky top-[4rem] z-[50] mb-3 flex items-center gap-2 border-b border-solid border-zinc-900 bg-bg-color bg-opacity-90 px-4 py-3 shadow-sm backdrop-blur-sm md:px-12">
        <Image
          className="grid h-9 w-9 min-w-[36px] place-items-center rounded-full bg-zinc-700"
          src={pluginCommunity?.image}
          alt={pluginCommunity?.name}
          width={50}
          height={50}
        />
        <div>
          <h3 className="text-base font-semibold md:text-base">
            {pluginCommunity?.name}
          </h3>
          <p className="line-clamp-1 text-sm text-gray-500 md:text-base">
            {pluginCommunity.description}
          </p>
        </div>
      </div>
    </Fragment>
  );
}

export default memo(IdentifyPlugin);
