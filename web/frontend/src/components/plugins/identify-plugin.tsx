'use client';

import { getCommunityPlugin } from '@/src/actions/plugins/get-community-plugins';
import { CommunityPlugin } from '@/src/types/plugins/plugins.types';
import Image from 'next/image';
import { Fragment, useEffect, useState, memo } from 'react';
import { NavArrowRight } from 'iconoir-react';
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

  const isPublic = !pluginCommunity.private;
  const pluginUrl = `https://h.omi.me/apps/${pluginId}`;

  const content = (
    <>
      <Image
        className="h-8 w-8 min-w-[32px] rounded-lg object-cover"
        src={pluginCommunity?.image}
        alt={pluginCommunity?.name}
        width={32}
        height={32}
      />
      <div className="flex-1">
        <h3 className="text-base font-semibold text-white">
          {pluginCommunity?.name}
        </h3>
        <p className="line-clamp-1 text-xs text-zinc-400">
          {pluginCommunity.description}
        </p>
      </div>
      {isPublic && <NavArrowRight className="h-4 w-4 text-zinc-500" />}
    </>
  );

  return (
    <Fragment>
      {isPublic ? (
        <a
          href={pluginUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="mb-4 flex items-center gap-3 transition-opacity hover:opacity-80"
        >
          {content}
        </a>
      ) : (
        <div className="mb-4 flex items-center gap-3">
          {content}
        </div>
      )}
    </Fragment>
  );
}

export default memo(IdentifyPlugin);
