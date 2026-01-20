import { MetadataRoute } from 'next';
import { getApprovedApps } from '@/lib/api/public';
import { categoryMetadata } from '@/components/marketplace/category';

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const { plugins } = await getApprovedApps();
  const categories = Object.keys(categoryMetadata);

  const now = new Date();

  // Static pages
  const staticPages: MetadataRoute.Sitemap = [
    {
      url: 'https://omi.me/apps',
      lastModified: now,
      changeFrequency: 'daily',
      priority: 1.0,
    },
  ];

  // Category pages
  const categoryPages: MetadataRoute.Sitemap = categories.map((category) => ({
    url: `https://omi.me/apps/category/${category}`,
    lastModified: now,
    changeFrequency: 'daily',
    priority: 0.8,
  }));

  // App detail pages
  const appPages: MetadataRoute.Sitemap = plugins.map((app) => ({
    url: `https://omi.me/apps/${app.id}`,
    lastModified: now,
    changeFrequency: 'weekly',
    priority: 0.7,
  }));

  return [...staticPages, ...categoryPages, ...appPages];
}
