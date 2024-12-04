import { Metadata } from 'next';

export interface CategoryMetadata {
  title: string;
  description: string;
  keywords: string[];
}

export const categoryMetadata: Record<string, CategoryMetadata> = {
  productivity: {
    title: 'Productivity Apps for OMI Necklace',
    description:
      'Enhance your daily workflow with OMI productivity apps. From voice-controlled task management to AI-powered note-taking, transform how you work with hands-free efficiency.',
    keywords: [
      'productivity apps',
      'task management',
      'note-taking',
      'voice control',
      'AI assistant',
    ],
  },
  entertainment: {
    title: 'Entertainment Apps for OMI Necklace',
    description:
      'Discover entertainment apps for your OMI Necklace. Enjoy music, games, and interactive experiences designed for voice control and ambient computing.',
    keywords: [
      'entertainment apps',
      'music',
      'games',
      'interactive experiences',
      'voice control',
    ],
  },
  health: {
    title: 'Health & Wellness Apps for OMI Necklace',
    description:
      'Take control of your wellness journey with OMI health apps. Track fitness, monitor health metrics, and get AI-powered wellness insights through your wearable companion.',
    keywords: [
      'health apps',
      'wellness tracking',
      'fitness monitoring',
      'health metrics',
      'AI wellness',
      'wearable health',
      'OMI apps',
      'digital health companion',
    ],
  },
  social: {
    title: 'Social Apps for OMI Necklace',
    description:
      'Stay connected with OMI social apps. Experience new ways to communicate, share, and interact with friends and family through your AI-powered necklace.',
    keywords: [
      'social apps',
      'communication',
      'sharing',
      'social interaction',
      'voice messaging',
    ],
  },
  integration: {
    title: 'Integration Apps for OMI Necklace',
    description:
      'Connect your digital world with OMI integration apps. Seamlessly control smart home devices, sync with your favorite services, and automate your life.',
    keywords: [
      'integration apps',
      'smart home',
      'automation',
      'device control',
      'service integration',
    ],
  },
};

const productInfo = {
  name: 'OMI Necklace',
  description: 'AI-powered wearable necklace. Real-time AI voice assistant.',
  price: '69.99',
  currency: 'USD',
  url: 'https://www.omi.me/products/friend-dev-kit-2',
};

const appStoreInfo = {
  ios: 'https://apps.apple.com/us/app/friend-ai-wearable/id6502156163',
  android: 'https://play.google.com/store/apps/details?id=com.friend.ios',
};

export function generateBreadcrumbSchema(category?: string) {
  const breadcrumbList = {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: [
      {
        '@type': 'ListItem',
        position: 1,
        name: 'Home',
        item: 'https://omi.me',
      },
      {
        '@type': 'ListItem',
        position: 2,
        name: 'Apps',
        item: 'https://omi.me/apps',
      },
    ],
  };

  if (category) {
    breadcrumbList.itemListElement.push({
      '@type': 'ListItem',
      position: 3,
      name: categoryMetadata[category]?.title || category,
      item: `https://omi.me/apps/category/${category}`,
    });
  }

  return breadcrumbList;
}

export function generateProductSchema() {
  return {
    '@context': 'https://schema.org',
    '@type': 'Product',
    name: productInfo.name,
    description: productInfo.description,
    brand: {
      '@type': 'Brand',
      name: 'OMI',
    },
    offers: {
      '@type': 'Offer',
      price: productInfo.price,
      priceCurrency: productInfo.currency,
      availability: 'https://schema.org/InStock',
      url: productInfo.url,
    },
    additionalProperty: [
      {
        '@type': 'PropertyValue',
        name: 'App Store',
        value: appStoreInfo.ios,
      },
      {
        '@type': 'PropertyValue',
        name: 'Play Store',
        value: appStoreInfo.android,
      },
    ],
  };
}

export function generateCollectionPageSchema(
  title: string,
  description: string,
  url: string,
) {
  return {
    '@context': 'https://schema.org',
    '@type': 'CollectionPage',
    name: title,
    description: description,
    url: url,
    isPartOf: {
      '@type': 'WebSite',
      name: 'OMI Apps Marketplace',
      url: 'https://omi.me/apps',
    },
  };
}

export function generateOrganizationSchema() {
  return {
    '@context': 'https://schema.org',
    '@type': 'Organization',
    name: 'OMI',
    url: 'https://omi.me',
    sameAs: [appStoreInfo.ios, appStoreInfo.android],
  };
}

export function generateAppListSchema(apps: any[]) {
  return {
    '@context': 'https://schema.org',
    '@type': 'ItemList',
    itemListElement: apps.map((app, index) => ({
      '@type': 'ListItem',
      position: index + 1,
      item: {
        '@type': 'SoftwareApplication',
        name: app.name,
        description: app.description,
        applicationCategory: app.category,
        operatingSystem: 'iOS, Android',
        offers: {
          '@type': 'Offer',
          price: '0',
          priceCurrency: 'USD',
        },
      },
    })),
  };
}

export function getBaseMetadata(title: string, description: string): Metadata {
  return {
    title,
    description,
    metadataBase: new URL('https://omi.me'),
    openGraph: {
      title,
      description,
      type: 'website',
      siteName: 'OMI Apps Marketplace',
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description,
      creator: '@omi',
      site: '@omi',
    },
    other: {
      'apple-itunes-app': `app-id=6502156163`,
      'google-play-app': `app-id=com.friend.ios`,
    },
  };
}
