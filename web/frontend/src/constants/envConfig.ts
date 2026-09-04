import { shareBaseUrl } from '@/src/lib/share-base-url.mjs';

const envConfig = {
  API_URL: process.env.API_URL,
  NODE_ENV: process.env.NEXT_PUBLIC_NODE_ENV,
  IS_DEVELOPMENT: process.env.NEXT_PUBLIC_NODE_ENV === 'development',
  WEB_URL: shareBaseUrl(process.env.WEB_URL),
  GLEAP_API_KEY: process.env.NEXT_PUBLIC_GLEAP_API_KEY,
  ALGOLIA_APP_ID: process.env.NEXT_PUBLIC_ALGOLIA_APP_ID ?? '',
  ALGOLIA_SEARCH_API_KEY: process.env.NEXT_PUBLIC_ALGOLIA_API_KEY ?? '',
  ALGOLIA_INDEX_NAME: process.env.NEXT_PUBLIC_ALGOLIA_INDEX_NAME ?? 'memories',
};

export default envConfig;
