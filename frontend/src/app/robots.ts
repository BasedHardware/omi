import { MetadataRoute } from 'next';

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: '*',
      disallow: ['/memories/'],
    },
    sitemap: 'https://omi.me/sitemap.xml',
  };
}
