import { getCommunityPlugin } from '@/src/actions/plugins/get-community-plugins';
import { Puzzle } from 'iconoir-react';

interface IndentifyPluginProps {
  pluginId: string;
}

export default async function IndentifyPlugin({ pluginId }: IndentifyPluginProps) {
  const pluginCommunity = await getCommunityPlugin(pluginId);

  if(!pluginCommunity) return null;

  return (
    <div className="flex gap-2 items-center sticky top-[4rem] px-4 md:px-12 bg-[#0f0f0f] backdrop-blur-sm bg-opacity-90 z-[50] py-3 shadow-sm border-b border-solid border-zinc-900">
      {/* <Image src={`${envConfig.API_URL}${pluginCommunity.image}`} alt={pluginCommunity.name} width={50} height={50}/> */}
      <div className='w-9 h-9 bg-zinc-700 rounded-full grid place-items-center'>
        <Puzzle className='text-xs'/>
      </div>
      <div>
        <h3 className="text-base font-semibold md:text-base">{pluginCommunity.name}</h3>
        <p className="text-gray-500 md:-mt-1 md:text-base text-sm line-clamp-1">{pluginCommunity.description}</p>
      </div>
    </div>
  );
}
