import { MetadataRoute } from 'next';
import envConfig from './src/constants/envConfig';
import getPublicMemoriesPrerender from './src/actions/memories/get-public-memories-prerender';

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  if (envConfig.IS_DEVELOPMENT) return [];

  const urls = [{ path: 'memories', priority: 0.7 }];

  const memories = await getPublicMemoriesPrerender(20000);
  const memoriesUrls = memories.map((memory) => ({
    path: 'memories/' + memory.id,
    priority: 0.9,
  }));
  urls.push(...memoriesUrls);

  return urls.map((item) => {
    return {
      url: `${envConfig.API_URL}/${item.path}`,
      priority: item.priority,
    };
  });
}
