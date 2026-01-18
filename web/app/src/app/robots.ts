import { MetadataRoute } from 'next';

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: '*',
        allow: '/',
        disallow: ['/api/', '/_next/', '/auth/'],
      },
    ],
    sitemap: 'https://omi.me/sitemap.xml',
  };
}
