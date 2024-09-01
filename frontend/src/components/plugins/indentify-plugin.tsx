import { getCommunityPlugin } from '@/src/actions/plugins/get-community-plugins';

interface IndentifyPluginProps {
  pluginId: string;
}

export default async function IndentifyPlugin({ pluginId }: IndentifyPluginProps) {
  const pluginCommunity = await getCommunityPlugin(pluginId);

  if(!pluginCommunity) return null;

  return (
    <div className="flex gap-2 items-center">
      {/* <Image src={`${envConfig.API_URL}${pluginCommunity.image}`} alt={pluginCommunity.name} width={50} height={50}/> */}
      <div>
        <h3 className="text-base font-semibold md:text-lg">{pluginCommunity.name}</h3>
        <p className="text-gray-500 -mt-1 line-clamp-1">{pluginCommunity.description}</p>
      </div>
    </div>
  );
}
