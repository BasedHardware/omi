import { fileURLToPath } from 'node:url';
import { dirname } from 'node:path';

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  staticPageGenerationTimeout: 60 * 20,
  // Bypass 2MB fetch cache limit by using file system cache directly
  cacheHandler: fileURLToPath(import.meta.resolve('./cache-handler.cjs')),
  // Pin the file-tracing root to this app dir. Next 15+ otherwise infers the
  // workspace root from sibling lockfiles (monorepo) and nests the standalone
  // output under that path, which breaks the Dockerfile's
  // `COPY .../web/frontend/.next/standalone ./` + `CMD ["node","server.js"]`.
  outputFileTracingRoot: dirname(fileURLToPath(import.meta.url)),
  typescript: {
    ignoreBuildErrors: true,
  },
  output: 'standalone',
  experimental: {
    serverActions: {
      bodySizeLimit: '10mb',
    },
  },
  async redirects() {
    return [
      {
        source: '/memories/:path*',
        destination: '/conversations/:path*',
        permanent: true,
      },
    ];
  },
  async rewrites() {
    return [
      {
        source: '/conversations/:path*',
        destination: '/memories/:path*',
      },
    ];
  },
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'raw.githubusercontent.com',
      },
      {
        protocol: 'https',
        hostname: 'storage.googleapis.com',
      },
      {
        protocol: 'https',
        hostname: 'pbs.twimg.com',
      },
      {
        protocol: 'https',
        hostname: 'abs.twimg.com',
      },
      {
        protocol: 'https',
        hostname: 'static.vecteezy.com',
      },
    ],
  },
  async headers() {
    return [
      {
        source: '/(.*)?', // Matches all pages
        headers: [
          {
            key: 'X-Frame-Options',
            value: 'DENY',
          },
        ],
      },
      {
        source: '/.well-known/apple-app-site-association',
        headers: [{ key: 'content-type', value: 'application/json' }],
      },
    ];
  },
};

export default nextConfig;
