import envConfig from '@/src/constants/envConfig';
import { CompactPluginCard } from '../../components/plugin-card/compact';
import { CategoryNav } from '../../components/category-nav';
import type { Plugin, PluginStat } from '../../components/types';
import { getCategoryDisplay } from '../../utils/category';

interface CategoryPageProps {
  params: {
    category: string;
  };
}

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

export default async function CategoryPage({ params }: CategoryPageProps) {
  const { plugins, stats } = await getPluginsData();

  // Filter plugins for this category
  const categoryPlugins = plugins.filter((plugin) => plugin.category === params.category);

  // Sort plugins by different criteria
  const mostPopular = [...categoryPlugins]
    .sort((a, b) => b.installs - a.installs)
    .slice(0, 9);

  const highestRated = [...categoryPlugins]
    .sort((a, b) => (b.rating_avg || 0) - (a.rating_avg || 0))
    .slice(0, 9);

  // For now, use remaining plugins for "Most Recent" section
  const mostRecent = [...categoryPlugins]
    .filter((plugin) => !mostPopular.includes(plugin) && !highestRated.includes(plugin))
    .slice(0, 9);

  // Group remaining plugins by category for nav
  const groupedPlugins = plugins.reduce((acc, plugin) => {
    const category = plugin.category;
    if (!acc[category]) {
      acc[category] = [];
    }
    acc[category].push(plugin);
    return acc;
  }, {} as Record<string, Plugin[]>);

  return (
    <div className="relative bg-[#0B0F17]">
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
            {/* Category Header */}
            <div className="mb-12">
              <h2 className="text-2xl font-bold text-white">
                {getCategoryDisplay(params.category)}
                <span className="ml-2 text-base font-normal text-gray-400">
                  ({categoryPlugins.length})
                </span>
              </h2>
            </div>

            <div className="space-y-24">
              {/* Most Popular Section */}
              {mostPopular.length > 0 && (
                <section>
                  <h3 className="mb-8 text-xl font-semibold text-white">Most Popular</h3>
                  <div className="grid grid-cols-1 gap-y-4 sm:grid-cols-2 sm:gap-x-8 sm:gap-y-6 lg:grid-cols-3 lg:gap-x-12">
                    {mostPopular.map((plugin, index) => (
                      <CompactPluginCard
                        key={plugin.id}
                        plugin={plugin}
                        stat={stats.find((s) => s.id === plugin.id)}
                        index={index + 1}
                      />
                    ))}
                  </div>
                </section>
              )}

              {/* Highest Rated Section */}
              {highestRated.length > 0 && (
                <section>
                  <h3 className="mb-8 text-xl font-semibold text-white">Highest Rated</h3>
                  <div className="grid grid-cols-1 gap-y-4 sm:grid-cols-2 sm:gap-x-8 sm:gap-y-6 lg:grid-cols-3 lg:gap-x-12">
                    {highestRated.map((plugin, index) => (
                      <CompactPluginCard
                        key={plugin.id}
                        plugin={plugin}
                        stat={stats.find((s) => s.id === plugin.id)}
                        index={index + 1}
                      />
                    ))}
                  </div>
                </section>
              )}

              {/* Most Recent Section */}
              {mostRecent.length > 0 && (
                <section>
                  <h3 className="mb-8 text-xl font-semibold text-white">Most Recent</h3>
                  <div className="grid grid-cols-1 gap-y-4 sm:grid-cols-2 sm:gap-x-8 sm:gap-y-6 lg:grid-cols-3 lg:gap-x-12">
                    {mostRecent.map((plugin, index) => (
                      <CompactPluginCard
                        key={plugin.id}
                        plugin={plugin}
                        stat={stats.find((s) => s.id === plugin.id)}
                        index={index + 1}
                      />
                    ))}
                  </div>
                </section>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
