import envConfig from '@/src/constants/envConfig';
import { FeaturedPluginCard } from '../components/plugin-card/featured';
import { CategoryNav } from '../components/category-nav';
import type { Plugin, PluginStat } from '../components/types';

async function getPluginsData() {
  const [pluginsResponse, statsResponse] = await Promise.all([
    fetch(`${envConfig.API_URL}/v1/approved-apps?include_reviews=true`, {
      cache: 'no-store',
    }),
    fetch(
      'https://raw.githubusercontent.com/BasedHardware/omi/refs/heads/main/community-plugin-stats.json',
      {
        cache: 'no-store',
      },
    ),
  ]);

  const plugins = (await pluginsResponse.json()) as Plugin[];
  const stats = (await statsResponse.json()) as PluginStat[];

  return { plugins, stats };
}

export default async function PopularPage() {
  const { plugins, stats } = await getPluginsData();

  // Sort all plugins by installs
  const sortedPlugins = [...plugins].sort((a, b) => b.installs - a.installs);

  // Group plugins by category for nav
  const groupedPlugins = plugins.reduce((acc, plugin) => {
    const category = plugin.category;
    if (!acc[category]) {
      acc[category] = [];
    }
    acc[category].push(plugin);
    return acc;
  }, {} as Record<string, Plugin[]>);

  return (
    <div className="relative">
      {/* Fixed Header and Navigation */}
      <div className="fixed inset-x-0 top-16 z-40 bg-[#0B0F17]">
        <div className="px-6 py-8">
          <div className="container mx-auto">
            <h1 className="text-4xl font-bold text-[#6C8EEF]">Omi App Store</h1>
            <p className="mt-3 text-gray-400">
              Discover our most popular AI-powered applications
            </p>
          </div>
        </div>

        <div className="border-b border-white/5 shadow-lg shadow-black/5">
          <div className="px-6">
            <div className="container mx-auto py-5">
              <CategoryNav
                categories={Object.entries(groupedPlugins).map(([name, plugins]) => ({
                  name,
                  count: plugins.length,
                }))}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <main className="relative z-0 mt-[280px]">
        <div className="px-6 pt-8">
          <div className="container mx-auto">
            {/* Header */}
            <div className="mb-8">
              <h2 className="text-2xl font-bold text-white">
                Most Popular
                <span className="ml-2 text-base font-normal text-gray-400">
                  ({sortedPlugins.length})
                </span>
              </h2>
            </div>

            {/* Grid of Featured Cards */}
            <div className="grid grid-cols-4 gap-6">
              {sortedPlugins.map((plugin) => (
                <FeaturedPluginCard
                  key={plugin.id}
                  plugin={plugin}
                  stat={stats.find((s) => s.id === plugin.id)}
                />
              ))}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
