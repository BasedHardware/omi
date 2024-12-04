import AppList from './components/app-list';
import { Metadata } from 'next';
import {
  getBaseMetadata,
  generateProductSchema,
  generateCollectionPageSchema,
  generateOrganizationSchema,
  generateBreadcrumbSchema,
} from './utils/metadata';
import envConfig from '@/src/constants/envConfig';
import { Plugin } from './components/types';
import { ProductBanner } from '../components/product-banner';

async function getAppsCount() {
  const response = await fetch(
    `${envConfig.API_URL}/v1/approved-apps?include_reviews=true`,
    { next: { revalidate: 3600 } },
  );
  const plugins = (await response.json()) as Plugin[];
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
        <div className="fixed bottom-[1.5rem] left-0 right-0 z-50">
          <ProductBanner variant="floating" />
        </div>
      </div>
    </main>
  );
}
