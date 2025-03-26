import { Plugin, PluginStat } from '../components/types';
import { headers } from 'next/headers';
import { CompactPluginCard } from '../components/plugin-card/compact';
import { ScrollableCategoryNav } from '../components/scrollable-category-nav';
import { CategoryBreadcrumb } from '../components/category-breadcrumb';
import { AppStats } from '../components/app-stats';
import { AppActionButton } from '../components/app-action-button';
import { Calendar, User, FolderOpen, Puzzle } from 'lucide-react';
import { Metadata, ResolvingMetadata } from 'next';
import { ProductBanner } from '@/src/app/components/product-banner';
import { getAppById, getAppsByCategory } from '@/src/lib/api/apps';
import envConfig from '@/src/constants/envConfig';

type Props = {
  params: { id: string };
};

export async function generateMetadata(
  { params }: Props,
  parent: ResolvingMetadata,
): Promise<Metadata> {
  const plugin = await getAppById(params.id);

  if (!plugin) {
    return {
      title: 'App Not Found | Omi',
      description: 'The requested app could not be found.',
    };
  }

  const categoryName = formatCategoryName(plugin.category);
  const canonicalUrl = `${envConfig.WEB_URL}/apps/${plugin.id}`;

  return {
    title: `${plugin.name} - ${categoryName} App | Omi`,
    description: `${plugin.description} Available on Omi, the AI-powered wearable platform.`,
    metadataBase: new URL(envConfig.WEB_URL),
    alternates: {
      canonical: canonicalUrl,
    },
    openGraph: {
      title: `${plugin.name} - ${categoryName} App`,
      description: plugin.description,
      images: [
        {
          url: plugin.image,
          width: 1200,
          height: 630,
          alt: `${plugin.name} App for Omi`,
        },
      ],
      url: canonicalUrl,
      type: 'website',
      siteName: 'Omi',
    },
    twitter: {
      card: 'summary_large_image',
      title: `${plugin.name} - ${categoryName} App`,
      description: plugin.description,
      images: [plugin.image],
      creator: '@omiHQ',
      site: '@omiHQ',
    },
    other: {
      'application-name': 'Omi',
      'apple-itunes-app': `app-id=6502156163`,
      'google-play-app': `app-id=com.friend.ios`,
    },
  };
}

// Add a separate function to handle JSON-LD
export function generateStructuredData(plugin: Plugin, categoryName: string) {
  const canonicalUrl = `${envConfig.WEB_URL}/apps/${plugin.id}`;
  const appStoreUrl = 'https://apps.apple.com/us/app/friend-ai-wearable/id6502156163';
  const playStoreUrl = 'https://play.google.com/store/apps/details?id=com.friend.ios';
  const productUrl = 'https://www.omi.me/products/friend-dev-kit-2?ref=omi_marketplace&utm_source=h.omi.me&utm_campaign=omi_marketplace_floating_banner';

  return {
    __html: JSON.stringify([
      {
        '@context': 'https://schema.org',
        '@type': 'SoftwareApplication',
        name: plugin.name,
        description: plugin.description,
        applicationCategory: categoryName,
        operatingSystem: 'iOS, Android',
        author: {
          '@type': 'Person',
          name: plugin.author,
        },
        datePublished: plugin.created_at,
        aggregateRating: {
          '@type': 'AggregateRating',
          ratingValue: plugin.rating_avg?.toFixed(1) || '0',
          ratingCount: plugin.rating_count || 0,
          bestRating: '5',
          worstRating: '1',
        },
        applicationSuite: 'Omi',
        requiresSubscription: false,
        installUrl: canonicalUrl,
        interactionStatistic: {
          '@type': 'InteractionCounter',
          interactionType: 'https://schema.org/InstallAction',
          userInteractionCount: plugin.installs,
        },
      },
      {
        '@context': 'https://schema.org',
        '@type': 'Product',
        name: 'OMI Necklace',
        description: 'AI-powered wearable necklace. Real-time AI voice assistant.',
        brand: {
          '@type': 'Brand',
          name: 'OMI',
        },
        offers: {
          '@type': 'Offer',
          price: '69.99',
          priceCurrency: 'USD',
          availability: 'https://schema.org/InStock',
          url: productUrl,
          priceValidUntil: new Date(Date.now() + 365 * 24 * 60 * 60 * 1000)
            .toISOString()
            .split('T')[0], // Valid for 1 year
        },
        additionalProperty: [
          {
            '@type': 'PropertyValue',
            name: 'App Store',
            value: appStoreUrl,
          },
          {
            '@type': 'PropertyValue',
            name: 'Play Store',
            value: playStoreUrl,
          },
        ],
      },
    ]),
  };
}

// Helper function to format category name
const formatCategoryName = (category: string): string => {
  return category
    .split('-')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
};

// Helper function to determine platform and get appropriate link
function getPlatformLink(userAgent: string) {
  const isAndroid = /android/i.test(userAgent);
  const isIOS = /iphone|ipad|ipod/i.test(userAgent);

  return isAndroid
    ? 'https://play.google.com/store/apps/details?id=com.friend.ios'
    : isIOS
    ? 'https://apps.apple.com/us/app/friend-ai-wearable/id6502156163'
    : 'https://omi.me';
}

// Helper function to format date
function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}

export default async function PluginDetailView({ params }: { params: { id: string } }) {
  const plugin = await getAppById(params.id);

  if (!plugin) {
    throw new Error('App not found');
  }

  const statsResponse = await fetch(
    'https://raw.githubusercontent.com/BasedHardware/omi/refs/heads/main/community-plugin-stats.json',
  );
  const stats = (await statsResponse.json()) as PluginStat[];
  const stat = stats.find((p) => p.id === params.id);

  const userAgent = headers().get('user-agent') || '';
  const link = getPlatformLink(userAgent);

  // Get related apps based on category
  const relatedApps = (await getAppsByCategory(plugin.category))
    .filter((p) => p.id !== plugin.id)
    .slice(0, 6);

  const categoryName = formatCategoryName(plugin.category);

  return (
    <div className="relative flex min-h-screen flex-col bg-[#0B0F17]">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={generateStructuredData(plugin, categoryName)}
      />
      {/* Fixed Header and Navigation */}
      <div className="fixed inset-x-0 top-[4rem] z-50 bg-[#0B0F17]">
        <div className="border-b border-white/5 shadow-lg">
          <div className="container mx-auto px-[1.5rem] py-[2rem]">
            <CategoryBreadcrumb category={plugin.category} />
          </div>
        </div>
      </div>

      {/* Main Content */}
      <main className="relative z-0 mt-[10rem] flex-grow">
        <div className="container mx-auto px-[1.5rem] pt-[2rem]">
          {/* Hero Section */}
          <section className="grid grid-cols-1 gap-[3rem] lg:grid-cols-5">
            {/* Image Column - 3 columns */}
            <div className="lg:col-span-2">
              <div className="relative aspect-square overflow-hidden rounded-[1rem] bg-[#1A1F2E]">
                <img
                  src={plugin.image}
                  alt={plugin.name}
                  className="h-full w-full object-cover transition-transform duration-300 hover:scale-105"
                />
              </div>
            </div>
            {/* Content Column - 2 columns */}
            <div className="lg:col-span-3">
              <div className="flex h-full flex-col justify-between">
                {/* App Info Container */}
                <div>
                  <h1 className="text-4xl font-bold text-white">{plugin.name}</h1>
                  <p className="mt-[0.5rem] text-xl text-gray-400">by {plugin.author}</p>

                  {/* Stats Section */}
                  <div className="mt-[2rem] flex items-center gap-[1rem]">
                    <div className="flex items-center">
                      <span className="text-3xl font-bold text-yellow-400">
                        {plugin.rating_avg?.toFixed(1)}
                      </span>
                      <div className="ml-[0.5rem] flex flex-col">
                        <span className="text-yellow-400">★</span>
                        <span className="text-sm text-gray-400">
                          ({plugin.rating_count} reviews)
                        </span>
                      </div>
                    </div>
                    <div className="h-8 w-px bg-white/5" />
                    <div className="flex items-center">
                      <span className="text-3xl font-bold text-[#6C8EEF]">
                        {plugin.installs.toLocaleString()}
                      </span>
                      <span className="ml-2 text-sm text-gray-400">downloads</span>
                    </div>
                  </div>

                  {/* Action Button */}
                  <div className="mt-8">
                    <AppActionButton
                      link={link}
                      className="max-w-[200px] rounded-xl transition-all duration-300 hover:translate-y-[-2px]"
                    />
                    {/* Store Buttons */}
                    <div className="mt-4 flex items-center gap-4">
                      <a
                        href="https://apps.apple.com/us/app/friend-ai-wearable/id6502156163"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="transition-transform duration-300 hover:scale-105"
                      >
                        <img
                          src="/app-store-badge.svg"
                          alt="Download on the App Store"
                          className="h-[40px]"
                        />
                      </a>
                      <a
                        href="https://play.google.com/store/apps/details?id=com.friend.ios"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="transition-transform duration-300 hover:scale-105"
                      >
                        <img
                          src="/google-play-badge.png"
                          alt="Get it on Google Play"
                          className="h-[40px]"
                        />
                      </a>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </section>

          {/* Product Banner */}
          <section className="mt-12">
            <ProductBanner
              variant="detail"
              appName={plugin.name}
              category={categoryName}
            />
          </section>

          {/* About Section */}
          <section className="mt-16">
            <h2 className="text-2xl font-bold text-white">About</h2>
            <div className="mt-4">
              <p className="text-lg leading-relaxed text-gray-300">
                {plugin.description}
              </p>
            </div>
          </section>

          {/* Additional Details Section */}
          <section className="mt-16">
            <h2 className="mb-6 text-2xl font-bold text-white">Additional Details</h2>
            <div className="grid gap-8 sm:grid-cols-2">
              <div>
                <div className="flex items-center gap-2">
                  <Calendar className="h-5 w-5 text-gray-400" />
                  <div className="text-sm font-medium text-gray-400">Created</div>
                </div>
                <div className="mt-1 pl-7 text-base text-white">
                  {formatDate(plugin.created_at)}
                </div>
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <User className="h-5 w-5 text-gray-400" />
                  <div className="text-sm font-medium text-gray-400">Creator</div>
                </div>
                <div className="mt-1 pl-7 text-base text-white">{plugin.author}</div>
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <FolderOpen className="h-5 w-5 text-gray-400" />
                  <div className="text-sm font-medium text-gray-400">Category</div>
                </div>
                <div className="mt-1 pl-7 text-base text-white">{categoryName}</div>
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <Puzzle className="h-5 w-5 text-gray-400" />
                  <div className="text-sm font-medium text-gray-400">Capabilities</div>
                </div>
                <div className="mt-2 flex flex-wrap gap-2 pl-7">
                  {Array.from(plugin.capabilities).map((cap) => (
                    <span
                      key={cap}
                      className="rounded-full bg-[#1A1F2E] px-3 py-1 text-sm text-white"
                    >
                      {cap}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </section>

          {/* Related Apps Section */}
          <section className="mt-16 pb-12">
            <h2 className="mb-8 text-2xl font-bold text-white">
              More {categoryName} Apps
            </h2>
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
              {relatedApps.map((app, index) => (
                <CompactPluginCard
                  key={app.id}
                  plugin={app}
                  stat={stats.find((s) => s.id === app.id)}
                  index={index + 1}
                />
              ))}
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
