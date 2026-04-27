const envConfig = {
  API_URL: process.env.API_URL,
  NODE_ENV: process.env.NEXT_PUBLIC_NODE_ENV,
  IS_DEVELOPMENT: process.env.NEXT_PUBLIC_NODE_ENV === 'development',
  WEB_URL: process.env.WEB_URL ?? 'https://h.omi.me',
  GLEAP_API_KEY: process.env.NEXT_PUBLIC_GLEAP_API_KEY,
  ALGOLIA_APP_ID: process.env.NEXT_PUBLIC_ALGOLIA_APP_ID ?? '',
  ALGOLIA_SEARCH_API_KEY: process.env.NEXT_PUBLIC_ALGOLIA_API_KEY ?? '',
  ALGOLIA_INDEX_NAME: process.env.NEXT_PUBLIC_ALGOLIA_INDEX_NAME ?? 'memories',
  ADMIN_KEY: process.env.ADMIN_KEY,
  OPENAI_API_KEY: process.env.OPENAI_API_KEY,
  // Server-side only — used by web/frontend/src/lib/firestore/encryption.ts to
  // derive per-user AES-GCM keys for BYOK encryption-at-rest. Must be 32+ bytes
  // of cryptographic randomness, base64-encoded. Never set as NEXT_PUBLIC_*.
  // See desktop/docs/M4-decisions.md § Decision 1 for rationale.
  BYOK_MASTER_PEPPER: process.env.BYOK_MASTER_PEPPER,
};

export default envConfig;
