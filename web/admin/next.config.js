/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  // Pin the file-tracing root to this app dir. Next 15+ otherwise infers the
  // workspace root from sibling lockfiles (monorepo) and nests the standalone
  // output under that path, which breaks the Dockerfile's
  // `COPY .next/standalone ./` + `CMD ["node","server.js"]`.
  outputFileTracingRoot: __dirname,
  images: { unoptimized: true },
  async redirects() {
    return [
      // Analytics moved to be the default Dashboard. Keep old bookmarks alive.
      { source: '/dashboard/analytics', destination: '/dashboard', permanent: false },
    ];
  },
};

module.exports = nextConfig;
