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
import envConfig from '@/src/constants/envConfig';

async function getAppsCount() {
  const plugins = await getApprovedApps();
  return plugins.length;
}

async function getPluginsData() {
  const rawPlugins = await getApprovedApps();
  const plugins = rawPlugins.map((plugin: any) => {
    const { created_at, capabilities, ...rest } = plugin;
    return {
      ...rest,
      created_at,
      capabilities: new Set(capabilities),
    };
  });

  return { plugins, stats: [] };
}

export async function generateMetadata(): Promise<Metadata> {
  const appsCount = await getAppsCount();
  const title = 'OMI Apps Marketplace - AI-Powered Apps for Your OMI Necklace';
  const description = `Discover and install ${appsCount}+ AI-powered apps for your OMI Necklace. Browse apps across productivity, entertainment, health, and more. Transform your OMI experience with voice-controlled applications.`;

  return {
    title,
    description,
    metadataBase: new URL(envConfig.WEB_URL),
    keywords:
      'OMI apps, AI apps, voice control apps, wearable apps, productivity apps, health apps, entertainment apps',
    alternates: {
      canonical: `${envConfig.WEB_URL}/apps`,
    },
    openGraph: {
      title,
      description,
      url: `${envConfig.WEB_URL}/apps`,
      siteName: 'OMI',
      images: [
        {
          url: `${envConfig.WEB_URL}/omi-app.png`,
          width: 1200,
          height: 630,
          alt: 'OMI Apps Marketplace',
        },
      ],
      locale: 'en_US',
      type: 'website',
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description,
      images: [`${envConfig.WEB_URL}/omi-app.png`],
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
    other: {
      'structured-data': JSON.stringify([
        generateCollectionPageSchema(title, description, `${envConfig.WEB_URL}/apps`),
        generateProductSchema(),
        generateOrganizationSchema(),
        generateBreadcrumbSchema(),
      ]),
    },
  };
}

export default async function AppsPage() {
  const { plugins, stats } = await getPluginsData();

  return (
    <main className="min-h-screen bg-[#0B0F17]">
      <div className="relative">
        <AppList initialPlugins={plugins} initialStats={stats} />
        <ProductBanner variant="floating" />
      </div>
    </main>
  );
}
