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
  getCategoryMetadata,
} from '../../utils/metadata';
import { ProductBanner } from '@/src/app/components/product-banner';
import { getAppsByCategory } from '@/src/lib/api/apps';

interface CategoryPageProps {
  params: {
    category: string;
  };
}

async function getCategoryData(category: string) {
  const [categoryPlugins, statsResponse] = await Promise.all([
    getAppsByCategory(category),
    fetch(
      'https://raw.githubusercontent.com/BasedHardware/omi/refs/heads/main/community-plugin-stats.json',
      {
        next: { revalidate: 3600 },
      },
    ),
  ]);

  const stats = (await statsResponse.json()) as PluginStat[];

  return { categoryPlugins, stats };
}

export async function generateMetadata({ params }: CategoryPageProps): Promise<Metadata> {
  const { category } = params;
  const { categoryPlugins } = await getCategoryData(category);
  const metadata = getCategoryMetadata(category);

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
function getNewOrRecentApps(plugins: Plugin[]): Plugin[] {
  // First try zero downloads
  const zeroDownloads = plugins.filter((plugin) => plugin.installs === 0);

  if (zeroDownloads.length >= 4) {
    // If we have enough zero download apps, shuffle and take 4
    return shuffleArray(zeroDownloads).slice(0, 4);
  } else {
    // If not enough zero downloads, get the lowest download count apps
    return shuffleArray([...plugins].sort((a, b) => a.installs - b.installs).slice(0, 4));
  }
}

export default async function CategoryPage({ params }: CategoryPageProps) {
  const { categoryPlugins, stats } = await getCategoryData(params.category);
  const newOrRecentApps = getNewOrRecentApps(categoryPlugins);
  const mostPopular =
    categoryPlugins.length > 6
      ? [...categoryPlugins].sort((a, b) => b.installs - a.installs).slice(0, 6)
      : [];
  const allApps = [...categoryPlugins].sort((a, b) => b.installs - a.installs);

  return (
    <div className="relative min-h-screen overflow-x-hidden bg-[#0B0F17]">
      {/* Fixed Header and Navigation - Optimized for mobile */}
      <div className="fixed inset-x-0 top-14 z-40 transform-gpu bg-[#0B0F17] transition-all duration-300 ease-in-out">
        {/* Breadcrumb and Category Header */}
        <div className="border-b border-white/5">
          <div className="container mx-auto px-3 py-3 sm:px-6 sm:py-4 md:px-8 md:py-5">
            <CategoryBreadcrumb category={params.category} />
            <div className="mt-2 sm:mt-3 md:mt-4">
              <CategoryHeader
                category={params.category}
                totalApps={categoryPlugins.length}
              />
            </div>
          </div>
        </div>

        {/* Product Banner and Navigation */}
        <div className="border-b border-white/5 bg-[#0B0F17]/80 backdrop-blur-sm">
          <div className="container mx-auto px-3 sm:px-6 md:px-8">
            {/* Product Banner */}
            <div className="py-2 sm:py-2.5 md:py-3">
              <ProductBanner variant="category" category={params.category} />
            </div>
            {/* Navigation Pills */}
            <div className="py-2 sm:py-2.5 md:py-3">
              <ScrollableCategoryNav currentCategory={params.category} />
            </div>
          </div>
        </div>
      </div>

      {/* Main Content - Adjusted spacing for mobile */}
      <main className="relative z-0 mt-[19.5rem] flex-grow transition-all duration-300 ease-in-out sm:mt-[21rem] md:mt-[22.5rem]">
        <div className="container mx-auto px-3 py-2 sm:px-6 sm:py-4 md:px-8 md:py-6">
          <div className="space-y-6 sm:space-y-8 md:space-y-10">
            {/* New/Recent This Week Section */}
            <section className="pt-4 sm:pt-6 md:pt-8">
              <h3 className="mb-3 text-sm font-semibold text-white sm:mb-4 sm:text-base md:mb-5 md:text-lg">
                {newOrRecentApps.some((p) => p.installs === 0)
                  ? 'New This Week'
                  : 'Recently Added'}
              </h3>
              <div className="grid grid-cols-2 gap-2.5 sm:gap-3 lg:grid-cols-4 lg:gap-4">
                {newOrRecentApps.map((plugin) => (
                  <FeaturedPluginCard
                    key={plugin.id}
                    plugin={plugin}
                    stat={stats.find((s) => s.id === plugin.id)}
                  />
                ))}
              </div>
            </section>

            {/* Most Popular Section */}
            {mostPopular.length > 0 && (
              <section>
                <h3 className="mb-3 text-sm font-semibold text-white sm:mb-4 sm:text-base md:mb-5 md:text-lg">
                  Most Popular
                </h3>
                <div className="grid grid-cols-1 gap-y-2 sm:grid-cols-2 sm:gap-3 lg:grid-cols-3 lg:gap-4">
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
              <h3 className="mb-3 text-sm font-semibold text-white sm:mb-4 sm:text-base md:mb-5 md:text-lg">
                All Apps
              </h3>
              <div className="grid grid-cols-1 gap-y-2 sm:grid-cols-2 sm:gap-3 lg:grid-cols-3 lg:gap-4">
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
      </main>
    </div>
  );
}
