import envConfig from '@/src/constants/envConfig';
import { PluginCard } from './components/plugin-card';
import { CategoryNav } from './components/category-nav';
import { CategoryHeader } from './components/category-header';
import type { Plugin, PluginStat } from './components/types';

export default async function SleekPluginList() {
  const response = await fetch(
    `${envConfig.API_URL}/v1/approved-apps?include_reviews=true`,
  );

  const plugins = (await response.json()) as Plugin[];

  const statsResponse = await fetch(
    'https://raw.githubusercontent.com/BasedHardware/omi/refs/heads/main/community-plugin-stats.json',
  );
  const stats = (await statsResponse.json()) as PluginStat[];

  // Group plugins by category
  const groupedPlugins = plugins.reduce((acc, plugin) => {
    const category = plugin.category;
    if (!acc[category]) {
      acc[category] = [];
    }
    acc[category].push(plugin);
    return acc;
  }, {} as Record<string, Plugin[]>);

  // Sort categories by number of plugins (most first)
  const sortedCategories = Object.entries(groupedPlugins)
    .sort(([, a], [, b]) => b.length - a.length)
    .reduce((acc, [category, plugins]) => {
      acc[category] = plugins.sort((a, b) => b.installs - a.installs);
      return acc;
    }, {} as Record<string, Plugin[]>);

  return (
    <div className="min-h-screen bg-[#0B0F17] px-6 py-8">
      <div className="container mx-auto">
        <div className="mb-12 mt-10">
          <h1 className="text-4xl font-bold text-[#6C8EEF]">Omi App Store</h1>
          <p className="mt-3 text-gray-400">
            Discover our most popular AI-powered applications
          </p>
        </div>

        <CategoryNav
          categories={Object.entries(sortedCategories).map(([name, plugins]) => ({
            name,
            count: plugins.length,
          }))}
        />
        <div className="space-y-16">
          {Object.entries(sortedCategories).map(([category, categoryPlugins]) => (
            <section key={category} id={category} className="scroll-m-20">
              <CategoryHeader category={category} pluginCount={categoryPlugins.length} />
              <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                {categoryPlugins.map((plugin) => (
                  <PluginCard
                    key={plugin.id}
                    plugin={plugin}
                    stat={stats.find((s) => s.id === plugin.id)}
                  />
                ))}
              </div>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
