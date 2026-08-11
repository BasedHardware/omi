import type { Metadata } from 'next';
import envConfig from '@/src/constants/envConfig';

const SITE_NAME = 'OMI';
const OG_IMAGE = '/omi-app.png';

export interface PlatformPageMeta {
  title: string;
  description: string;
  path: string;
  keywords?: string[];
  noIndex?: boolean;
}

export function buildPlatformMetadata(meta: PlatformPageMeta): Metadata {
  const url = `${envConfig.WEB_URL}${meta.path}`;
  return {
    title: meta.title,
    description: meta.description,
    metadataBase: new URL(envConfig.WEB_URL),
    keywords: (
      meta.keywords ?? [
        'Omi memory platform',
        'memory API',
        'MCP server',
        'embeddable memory widget',
        'agent memory',
      ]
    ).join(', '),
    alternates: { canonical: url },
    robots: meta.noIndex
      ? { index: false, follow: false }
      : {
          index: true,
          follow: true,
          googleBot: { index: true, follow: true, 'max-image-preview': 'large' },
        },
    openGraph: {
      title: meta.title,
      description: meta.description,
      url,
      siteName: SITE_NAME,
      images: [
        {
          url: `${envConfig.WEB_URL}${OG_IMAGE}`,
          width: 1200,
          height: 630,
          alt: meta.title,
        },
      ],
      locale: 'en_US',
      type: 'website',
    },
    twitter: {
      card: 'summary_large_image',
      title: meta.title,
      description: meta.description,
      images: [`${envConfig.WEB_URL}${OG_IMAGE}`],
    },
  };
}

export function generateSoftwareApplicationSchema() {
  return {
    '@context': 'https://schema.org',
    '@type': 'SoftwareApplication',
    name: 'Omi Memory Platform',
    applicationCategory: 'DeveloperApplication',
    operatingSystem: 'Web',
    url: `${envConfig.WEB_URL}/memory-platform`,
    description:
      'Backend-authoritative memory for APIs, MCP agents, local replicas, and embedded products.',
    offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
    publisher: { '@type': 'Organization', name: SITE_NAME, url: envConfig.WEB_URL },
  };
}

export function generateBreadcrumbSchema(trail: { name: string; path: string }[]) {
  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: trail.map((item, index) => ({
      '@type': 'ListItem',
      position: index + 1,
      name: item.name,
      item: `${envConfig.WEB_URL}${item.path}`,
    })),
  };
}
