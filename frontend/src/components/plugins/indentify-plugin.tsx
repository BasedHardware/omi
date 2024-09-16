'use client';

import { getCommunityPlugin } from '@/src/actions/plugins/get-community-plugins';
import { CommunityPlugin } from '@/src/types/plugins/plugins.types';
import Image from 'next/image';
import { Fragment, useEffect, useState } from 'react';
import ErrorIdentifyPlugin from './error-identify-plugin';
import IdentifyPluginLoader from './identify-plugin-loader';

interface IndentifyPluginProps {
  pluginId: string;
}

export default function IndentifyPlugin({ pluginId }: IndentifyPluginProps) {
  const [pluginCommunity, setPluginCommunity] = useState<CommunityPlugin | undefined>(
    undefined,
  );
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getCommunityPlugin(pluginId)
      .then((plugin) => {
        setPluginCommunity(plugin);
      })
      .finally(() => setLoading(false));
  }, []);

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
          src={`https://raw.githubusercontent.com/BasedHardware/Friend/main/${pluginCommunity?.image}`}
          alt={''}
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
