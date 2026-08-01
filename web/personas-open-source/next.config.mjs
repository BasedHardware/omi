/** @type {import('next').NextConfig} */
const nextConfig = {
  /* config options */
  async headers() {
    // Prevent clickjacking: disallow embedding any page (incl. the Google
    // sign-in page) in a frame.
    return [
      {
        source: '/(.*)?',
        headers: [
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'Content-Security-Policy', value: "frame-ancestors 'none'" },
        ],
      },
    ];
  },
};

export default nextConfig;
