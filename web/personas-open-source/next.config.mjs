/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  images: {
    domains: ['pbs.twimg.com', 'firebasestorage.googleapis.com'],
    formats: ['image/webp'],
  },
};

export default nextConfig;
