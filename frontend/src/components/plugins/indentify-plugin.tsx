import { getCommunityPlugin } from '@/src/actions/plugins/get-community-plugins';
import { Puzzle } from 'iconoir-react';

interface IndentifyPluginProps {
  pluginId: string;
}

export default async function IndentifyPlugin({ pluginId }: IndentifyPluginProps) {
  const pluginCommunity = await getCommunityPlugin(pluginId);

  if (!pluginCommunity) return null;

  return (
    <div className="sticky top-[4rem] mb-3 z-[50] flex items-center gap-2 border-b border-solid border-zinc-900 bg-[#0f0f0f] bg-opacity-90 px-4 py-3 shadow-sm backdrop-blur-sm md:px-12">
      {/* <Image src={`${envConfig.API_URL}${pluginCommunity.image}`} alt={pluginCommunity.name} width={50} height={50}/> */}
      <div className="grid min-w-[36px] h-9 w-9 place-items-center rounded-full bg-zinc-700">
        <Puzzle className="text-xs" />
      </div>
      <div>
        <h3 className="text-base font-semibold md:text-base">{pluginCommunity.name}</h3>
        <p className="line-clamp-1 text-sm text-gray-500 md:-mt-1 md:text-base">
          {pluginCommunity.description}
        </p>
      </div>
    </div>
  );
}
