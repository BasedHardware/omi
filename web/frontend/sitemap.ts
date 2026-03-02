import { MetadataRoute } from 'next';
import envConfig from './src/constants/envConfig';

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  if (envConfig.IS_DEVELOPMENT) return [];

  return [
    {
      url: `${envConfig.API_URL}/memories`,
      priority: 0.7,
    },
  ];
}
