/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  eslint: {
    ignoreDuringBuilds: true,
  },
  images: { unoptimized: true },
  async redirects() {
    return [
      // Analytics moved to be the default Dashboard. Keep old bookmarks alive.
      { source: '/dashboard/analytics', destination: '/dashboard', permanent: false },
    ];
  },
};

module.exports = nextConfig;
