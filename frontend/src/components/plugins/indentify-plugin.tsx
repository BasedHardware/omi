import { getCommunityPlugin } from '@/src/actions/plugins/get-community-plugins';
import Image from 'next/image';

interface IndentifyPluginProps {
  pluginId: string;
}

export default async function IndentifyPlugin({ pluginId }: IndentifyPluginProps) {
  const pluginCommunity = await getCommunityPlugin(pluginId);
  if (!pluginCommunity) throw new Error('Plugin not found');

  return (
    <div className="sticky top-[4rem] z-[50] mb-3 flex items-center gap-2 border-b border-solid border-zinc-900 bg-[#0f0f0f] bg-opacity-90 px-4 py-3 shadow-sm backdrop-blur-sm md:px-12">
      <Image
        className="grid h-9 w-9 min-w-[36px] place-items-center rounded-full bg-zinc-700"
        src={`https://raw.githubusercontent.com/BasedHardware/Friend/main/${pluginCommunity.image}`}
        alt={''}
        width={50}
        height={50}
      />
      <div>
        <h3 className="text-base font-semibold md:text-base">{pluginCommunity.name}</h3>
        <p className="line-clamp-1 text-sm text-gray-500 md:text-base">
          {pluginCommunity.description}
        </p>
      </div>
    </div>
  );
}
