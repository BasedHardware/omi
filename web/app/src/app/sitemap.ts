import { getApprovedApps } from '@/lib/api/public';
import { categoryMetadata } from '@/components/marketplace/category';

type SitemapEntry = {
  url: string;
  lastModified: Date;
  changeFrequency: 'daily' | 'weekly';
  priority: number;
};

export default async function sitemap(): Promise<SitemapEntry[]> {
  const { plugins } = await getApprovedApps();
  const categories = Object.keys(categoryMetadata);

  const now = new Date();

  // Static pages
  const staticPages: SitemapEntry[] = [
    {
      url: 'https://omi.me/apps',
      lastModified: now,
      changeFrequency: 'daily',
      priority: 1.0,
    },
  ];

  // Category pages
  const categoryPages: SitemapEntry[] = categories.map((category) => ({
    url: `https://omi.me/apps/category/${category}`,
    lastModified: now,
    changeFrequency: 'daily',
    priority: 0.8,
  }));

  // App detail pages
  const appPages: SitemapEntry[] = plugins.map((app) => ({
    url: `https://omi.me/apps/${app.id}`,
    lastModified: now,
    changeFrequency: 'weekly',
    priority: 0.7,
  }));

  return [...staticPages, ...categoryPages, ...appPages];
}
