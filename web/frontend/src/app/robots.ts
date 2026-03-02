import { MetadataRoute } from 'next';

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: '*',
      allow: ['/'],
      disallow: ['/conversations/', '/memories/'],
    },
    sitemap: 'https://h.omi.me/sitemap.xml',
  };
}
