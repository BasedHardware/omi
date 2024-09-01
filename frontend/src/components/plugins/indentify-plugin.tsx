import { getCommunityPlugin } from '@/src/actions/plugins/get-community-plugins';

interface IndentifyPluginProps {
  pluginId: string;
}

export default async function IndentifyPlugin({ pluginId }: IndentifyPluginProps) {
  const pluginCommunity = await getCommunityPlugin(pluginId);
  return (
    <div className="mt-10">
      <h3 className="text-xl font-semibold md:text-2xl">{pluginCommunity.name}</h3>
      <p className="text-white">{pluginCommunity.description}</p>
    </div>
  );
}
