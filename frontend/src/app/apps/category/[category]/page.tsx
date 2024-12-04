import envConfig from '@/src/constants/envConfig';
import { CompactPluginCard } from '../../components/plugin-card/compact';
import { FeaturedPluginCard } from '../../components/plugin-card/featured';
import { ScrollableCategoryNav } from '../../components/scrollable-category-nav';
import { CategoryBreadcrumb } from '../../components/category-breadcrumb';
import { CategoryHeader } from '../../components/category-header';
import type { Plugin, PluginStat } from '../../components/types';
import { Metadata } from 'next';
import {
  categoryMetadata,
  getBaseMetadata,
  generateProductSchema,
  generateCollectionPageSchema,
  generateBreadcrumbSchema,
  generateAppListSchema,
} from '../../utils/metadata';
import { ProductBanner } from '@/src/app/components/product-banner';

interface CategoryPageProps {
  params: {
    category: string;
  };
}

async function getCategoryData(category: string) {
  const [pluginsResponse, statsResponse] = await Promise.all([
    fetch(`${envConfig.API_URL}/v1/approved-apps?include_reviews=true`, {
      next: { revalidate: 3600 },
    }),
    fetch(
      'https://raw.githubusercontent.com/BasedHardware/omi/refs/heads/main/community-plugin-stats.json',
      {
        next: { revalidate: 3600 },
      },
    ),
  ]);

  const plugins = (await pluginsResponse.json()) as Plugin[];
  const stats = (await statsResponse.json()) as PluginStat[];

  const categoryPlugins =
    category === 'integration'
      ? plugins.filter(
          (plugin) =>
            Array.isArray(plugin.capabilities) &&
            plugin.capabilities.includes('external_integration'),
        )
      : plugins.filter((plugin) => plugin.category === category);

  return { categoryPlugins, stats };
}

export async function generateMetadata({ params }: CategoryPageProps): Promise<Metadata> {
  const { category } = params;
  const { categoryPlugins } = await getCategoryData(category);
  const metadata = categoryMetadata[category];

  if (!metadata) {
    return {
      title: 'Category Not Found - OMI Apps',
      description: 'The requested category could not be found.',
    };
  }

  const title = `${metadata.title} - OMI Apps Marketplace`;
  const description = `${metadata.description} Browse ${categoryPlugins.length}+ ${category} apps for your OMI Necklace.`;

  const baseMetadata = getBaseMetadata(title, description);
  const canonicalUrl = `https://omi.me/apps/category/${category}`;

  return {
    ...baseMetadata,
    keywords: metadata.keywords.join(', '),
    alternates: {
      canonical: canonicalUrl,
    },
    robots: {
      index: true,
      follow: true,
      googleBot: {
        index: true,
        follow: true,
      },
    },
    verification: {
      other: {
        'structured-data': JSON.stringify([
          generateCollectionPageSchema(title, description, canonicalUrl),
          generateProductSchema(),
          generateBreadcrumbSchema(category),
          generateAppListSchema(categoryPlugins),
        ]),
      },
    },
  };
}

// Helper for Fisher-Yates shuffle
function shuffleArray<T>(array: T[]): T[] {
  const newArray = [...array];
  for (let i = newArray.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [newArray[i], newArray[j]] = [newArray[j], newArray[i]];
  }
  return newArray;
}

// Get new or recent apps
function getNewOrRecentApps(apps: Plugin[]): Plugin[] {
  // First try zero downloads
  const zeroDownloads = apps.filter((plugin) => plugin.installs === 0);

  if (zeroDownloads.length >= 4) {
    // If we have enough zero download apps, shuffle and take 4
    return shuffleArray(zeroDownloads).slice(0, 4);
  } else {
    // If not enough zero downloads, get the lowest download count apps
    return shuffleArray([...apps].sort((a, b) => a.installs - b.installs).slice(0, 4));
  }
}

export default async function CategoryPage({ params }: CategoryPageProps) {
  const { categoryPlugins, stats } = await getCategoryData(params.category);

  // Get new/recent apps
  const newOrRecentApps = getNewOrRecentApps(categoryPlugins);

  // Get most popular apps (if we have enough)
  const mostPopular =
    categoryPlugins.length > 6
      ? [...categoryPlugins].sort((a, b) => b.installs - a.installs).slice(0, 6)
      : [];

  // Get all apps sorted by installs
  const allApps = [...categoryPlugins].sort((a, b) => b.installs - a.installs);

  return (
    <div className="relative flex min-h-screen flex-col bg-[#0B0F17]">
      {/* Fixed Header and Navigation */}
      <div className="fixed inset-x-0 top-16 z-40 bg-[#0B0F17]">
        <div className="px-6 py-8">
          <div className="container mx-auto">
            <CategoryBreadcrumb category={params.category} />
            <div className="mt-8">
              <CategoryHeader
                category={params.category}
                totalApps={categoryPlugins.length}
              />
            </div>
          </div>
        </div>

        <div className="border-b border-white/5 shadow-lg shadow-black/5">
          <div className="px-6">
            <div className="container mx-auto">
              <ProductBanner variant="category" category={params.category} />
              <div className="py-5">
                <ScrollableCategoryNav currentCategory={params.category} />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <main className="relative z-0 mt-[555px] flex-grow sm:mt-[475px]">
        <div className="px-4 py-6 sm:px-6 sm:py-8">
          <div className="container mx-auto">
            <div className="space-y-6 sm:space-y-12">
              {/* New/Recent This Week Section */}
              <section>
                <h3 className="text-lg font-semibold text-white sm:mb-8 sm:text-xl">
                  {newOrRecentApps.some((p) => p.installs === 0)
                    ? 'New This Week'
                    : 'Recently Added'}
                </h3>
                <div className="mt-3 grid grid-cols-2 gap-2 sm:mt-6 sm:gap-4 lg:grid-cols-4 lg:gap-6">
                  {newOrRecentApps.map((plugin) => (
                    <FeaturedPluginCard
                      key={plugin.id}
                      plugin={plugin}
                      stat={stats.find((s) => s.id === plugin.id)}
                    />
                  ))}
                </div>
              </section>

              {/* Most Popular Section - Only show if we have enough apps */}
              {mostPopular.length > 0 && (
                <section>
                  <h3 className="text-lg font-semibold text-white sm:mb-8 sm:text-xl">
                    Most Popular
                  </h3>
                  <div className="mt-3 grid grid-cols-1 gap-y-2 sm:mt-6 sm:grid-cols-2 sm:gap-x-8 sm:gap-y-4 lg:grid-cols-3 lg:gap-x-12">
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

              {/* All Apps Section */}
              <section>
                <h3 className="text-lg font-semibold text-white sm:mb-8 sm:text-xl">
                  All Apps
                </h3>
                <div className="mt-3 grid grid-cols-1 gap-y-2 sm:mt-6 sm:grid-cols-2 sm:gap-x-8 sm:gap-y-4 lg:grid-cols-3 lg:gap-x-12">
                  {allApps.map((plugin, index) => (
                    <CompactPluginCard
                      key={plugin.id}
                      plugin={plugin}
                      stat={stats.find((s) => s.id === plugin.id)}
                      index={index + 1}
                    />
                  ))}
                </div>
              </section>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
