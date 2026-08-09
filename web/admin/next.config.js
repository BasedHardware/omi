// Self-hosted Grafana behind admin.omi.me/grafana (Cloud Run, us-central1).
const GRAFANA_ORIGIN =
  process.env.GRAFANA_ORIGIN ?? 'https://omi-grafana-208440318997.us-central1.run.app';

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
  async rewrites() {
    // /dashboard embeds the self-hosted Grafana (Cloud Run) same-origin.
    // Grafana serves itself under the /grafana sub-path (serve_from_sub_path).
    return [
      { source: '/grafana', destination: `${GRAFANA_ORIGIN}/grafana` },
      { source: '/grafana/:path*', destination: `${GRAFANA_ORIGIN}/grafana/:path*` },
    ];
  },
  async headers() {
    // Prevent clickjacking: disallow embedding any page (incl. /login) in a frame.
    // Exception: the proxied Grafana may be framed by the dashboard page itself.
    return [
      {
        source: '/(.*)?',
        headers: [
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'Content-Security-Policy', value: "frame-ancestors 'none'" },
        ],
      },
      {
        source: '/grafana/:path*',
        headers: [
          { key: 'X-Frame-Options', value: 'SAMEORIGIN' },
          { key: 'Content-Security-Policy', value: "frame-ancestors 'self'" },
        ],
      },
    ];
  },
};

module.exports = nextConfig;
