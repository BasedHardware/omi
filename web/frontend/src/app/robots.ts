import { MetadataRoute } from 'next';

import envConfig from '@/src/constants/envConfig';

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: '*',
      allow: ['/'],
    },
    sitemap: `${envConfig.WEB_URL}/sitemap.xml`,
  };
}
