import { CompactPluginCard } from '@/components/marketplace/plugin-card/CompactPluginCard';
import { FeaturedPluginCard } from '@/components/marketplace/plugin-card/FeaturedPluginCard';
import { ScrollableCategoryNav } from '@/components/marketplace/ScrollableCategoryNav';
import { CategoryBreadcrumb } from '@/components/marketplace/CategoryBreadcrumb';
import { CategoryHeader } from '@/components/marketplace/CategoryHeader';
import { getAllAppsV2, transformToPlugin } from '@/lib/api/public';
import { getCategoryMetadata, categoryMetadata } from '@/components/marketplace/category';
import { BreadcrumbJsonLd, CollectionPageJsonLd } from '@/components/seo/JsonLd';
import type { Metadata } from 'next';

type Props = {
  params: Promise<{ category: string }>;
};

// ISR configuration
export const revalidate = 300; // Revalidate every 5 minutes
export const dynamicParams = true; // Allow non-pre-rendered categories

// Pre-generate top categories from v2 (by app count)
export async function generateStaticParams() {
  const topCategories = [
    'conversation-analysis',        // 22 apps
    'utilities-and-tools',           // 18 apps
    'productivity-and-organization', // 14 apps
    'entertainment-and-fun',         // 7 apps
    'communication-improvement',     // 5 apps
    'education-and-learning'         // 3 apps
  ];
  return topCategories.map((category) => ({ category }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { category } = await params;
  const metadata = getCategoryMetadata(category);
  const title = `${metadata.displayName} Apps - Omi App Store`;
  const description = `${metadata.description} Browse ${metadata.displayName} apps for your Omi.`;

  return {
    title,
    description,
    alternates: {
      canonical: `/apps/category/${category}`,
    },
    openGraph: {
      title,
      description,
      url: `/apps/category/${category}`,
      type: 'website',
      images: [
        {
          url: '/og-apps.png',
          width: 1200,
          height: 630,
          alt: `${metadata.displayName} Apps`,
        },
      ],
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description,
      images: ['/og-apps.png'],
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

export default async function CategoryPage({ params }: Props) {
  const { category } = await params;
  const categoryMeta = getCategoryMetadata(category);

  // Fetch ALL v2 apps by paginating through all capability groups
  // This makes multiple requests during build time but ensures all 600+ apps are available
  const rawApps = await getAllAppsV2(true); // include_reviews=true to get ratings

  const allPlugins = rawApps.map(transformToPlugin);

  // Filter plugins by category
  const categoryPlugins = allPlugins.filter((p) => p.category === category);

  // Get new or recent apps (lowest download count)
  const newOrRecentApps = shuffleArray(
    [...categoryPlugins].sort((a, b) => a.installs - b.installs).slice(0, 4)
  );

  // Get most popular
  const mostPopular =
    categoryPlugins.length > 6
      ? [...categoryPlugins].sort((a, b) => b.installs - a.installs).slice(0, 6)
      : [];

  // All apps sorted by installs
  const allApps = [...categoryPlugins].sort((a, b) => b.installs - a.installs);

  return (
    <div className="relative min-h-screen overflow-x-hidden bg-[#0B0F17]">
      <BreadcrumbJsonLd
        items={[
          { name: 'Apps', url: '/apps' },
          { name: categoryMeta.displayName, url: `/apps/category/${category}` },
        ]}
      />
      <CollectionPageJsonLd
        name={`${categoryMeta.displayName} Apps`}
        description={`${categoryMeta.description} Browse ${categoryMeta.displayName} apps for your Omi.`}
        url={`/apps/category/${category}`}
      />
      {/* Fixed Header and Navigation */}
      <div className="fixed inset-x-0 top-12 z-40 bg-[#0B0F17]">
        {/* Breadcrumb and Category Header */}
        <div className="border-b border-white/5">
          <div className="container mx-auto px-3 py-3 sm:px-6 sm:py-4 md:px-8 md:py-5">
            <CategoryBreadcrumb category={category} />
            <div className="mt-2 sm:mt-3 md:mt-4">
              <CategoryHeader category={category} totalApps={categoryPlugins.length} />
            </div>
          </div>
        </div>

        {/* Navigation Pills */}
        <div className="border-b border-white/5 bg-[#0B0F17]/80 backdrop-blur-sm">
          <div className="container mx-auto px-3 sm:px-6 md:px-8">
            <div className="py-2 sm:py-2.5 md:py-3">
              <ScrollableCategoryNav currentCategory={category} />
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <main className="relative z-0 mt-[14rem] flex-grow transition-all duration-300 ease-in-out sm:mt-[15rem] md:mt-[16rem]">
        <div className="container mx-auto px-3 py-2 sm:px-6 sm:py-4 md:px-8 md:py-6">
          <div className="space-y-6 sm:space-y-8 md:space-y-10">
            {/* New/Recent This Week Section */}
            {newOrRecentApps.length > 0 && (
              <section className="pt-4 sm:pt-6 md:pt-8">
                <h3 className="mb-3 text-sm font-semibold text-white sm:mb-4 sm:text-base md:mb-5 md:text-lg">
                  {newOrRecentApps.some((p) => p.installs === 0)
                    ? 'New This Week'
                    : 'Recently Added'}
                </h3>
                <div className="grid grid-cols-2 gap-2.5 sm:gap-3 lg:grid-cols-4 lg:gap-4">
                  {newOrRecentApps.map((plugin) => (
                    <FeaturedPluginCard key={plugin.id} plugin={plugin} />
                  ))}
                </div>
              </section>
            )}

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
