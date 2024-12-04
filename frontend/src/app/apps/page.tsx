import AppList from './components/app-list';
import { Metadata } from 'next';
import {
  getBaseMetadata,
  generateProductSchema,
  generateCollectionPageSchema,
  generateOrganizationSchema,
  generateBreadcrumbSchema,
} from './utils/metadata';
import { ProductBanner } from '../components/product-banner';
import { getApprovedApps } from '@/src/lib/api/apps';

async function getAppsCount() {
  const plugins = await getApprovedApps();
  return plugins.length;
}

export async function generateMetadata(): Promise<Metadata> {
  const appsCount = await getAppsCount();
  const title = 'OMI Apps Marketplace - AI-Powered Apps for Your OMI Necklace';
  const description = `Discover and install ${appsCount}+ AI-powered apps for your OMI Necklace. Browse apps across productivity, entertainment, health, and more. Transform your OMI experience with voice-controlled applications.`;
  const baseMetadata = getBaseMetadata(title, description);

  return {
    ...baseMetadata,
    keywords:
      'OMI apps, AI apps, voice control apps, wearable apps, productivity apps, health apps, entertainment apps',
    alternates: {
      canonical: 'https://omi.me/apps',
    },
    openGraph: {
      title,
      description,
      url: 'https://omi.me/apps',
      siteName: 'OMI',
      images: [
        {
          url: '/omi-app.png',
          width: 1200,
          height: 630,
          alt: 'OMI Apps Marketplace',
        }
      ],
      locale: 'en_US',
      type: 'website',
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description,
      images: ['/omi-app.png'],
      creator: '@omiHQ',
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
          generateCollectionPageSchema(title, description, 'https://omi.me/apps'),
          generateProductSchema(),
          generateOrganizationSchema(),
          generateBreadcrumbSchema(),
        ]),
      },
    },
  };
}

export default async function AppsPage() {
  return (
    <main className="min-h-screen bg-[#0B0F17]">
      <div className="relative">
        <AppList />
        <ProductBanner variant="floating" />
      </div>
    </main>
  );
}
