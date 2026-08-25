import { getAllAppsV2, transformToPlugin } from '@/lib/api/public';
import AppList from '@/components/marketplace/AppList';
import { PromoCard } from '@/components/marketplace/PromoCard';
import { CollectionPageJsonLd } from '@/components/seo/JsonLd';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Omi App Store - Discover AI-Powered Apps',
  description: 'Explore and install AI-powered apps for Omi. Enhance your experience with productivity tools, conversation insights, and more.',
  alternates: {
    canonical: '/apps',
  },
  openGraph: {
    title: 'Omi App Store - Discover AI-Powered Apps',
    description: 'Explore and install AI-powered apps for Omi. Enhance your experience with productivity tools, conversation insights, and more.',
    url: '/apps',
    type: 'website',
    images: [
      {
        url: '/og-apps.png',
        width: 1200,
        height: 630,
        alt: 'Omi App Store',
      },
    ],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Omi App Store - Discover AI-Powered Apps',
    description: 'Explore and install AI-powered apps for Omi. Enhance your experience with productivity tools, conversation insights, and more.',
    images: ['/og-apps.png'],
  },
};

export default async function AppsMarketplacePage() {
  // Fetch ALL v2 apps by paginating through all capability groups
  // This makes multiple requests during build time but ensures all 600+ apps are available
  const allApps = await getAllAppsV2(true); // include_reviews=true to get ratings

  // Transform plugins to have Set for capabilities
  const plugins = allApps.map(transformToPlugin);

  return (
    <div className="min-h-screen bg-[#0B0F17]">
      <CollectionPageJsonLd
        name="Omi App Store"
        description="Explore and install AI-powered apps for Omi. Enhance your experience with productivity tools, conversation insights, and more."
        url="/apps"
      />
      <AppList initialPlugins={plugins} initialStats={[]} />
      <PromoCard />
    </div>
  );
}
