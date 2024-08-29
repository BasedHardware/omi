import { MetadataRoute } from 'next';

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: '*',
      disallow: ['/memories/'],
    },
    // sitemap: 'https://app.basehardhare.com/sitemap.xml',
  };
}
