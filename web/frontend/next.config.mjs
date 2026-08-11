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
        // Every page except the embeddable widget. The negative lookahead is
        // load-bearing: `X-Frame-Options: DENY` cannot be relaxed per-route by a
        // later rule, so the widget must be excluded here rather than overridden.
        source: '/((?!memory-platform/widget).*)',
        headers: [
          {
            key: 'X-Frame-Options',
            value: 'DENY',
          },
        ],
      },
      {
        // The memory widget exists to be embedded in a host product's page, so
        // it is the one route that must be framable. It is safe to frame from
        // any origin because it carries no ambient authority: the published
        // embed sandboxes it without `allow-same-origin`, giving it an opaque
        // origin with no cookies and no durable storage, so it holds no session
        // a framing page could exercise. It is inert until the host explicitly
        // hands it a short-lived token over postMessage. Hosts still restrict
        // who may frame *their* page with their own frame-ancestors policy.
        source: '/memory-platform/widget',
        headers: [
          {
            key: 'Content-Security-Policy',
            value: 'frame-ancestors *',
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
