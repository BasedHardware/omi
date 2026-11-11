type Robots = {
  rules: Array<{
    userAgent: string;
    allow: string;
    disallow: string[];
  }>;
  sitemap: string;
};

export default function robots(): Robots {
  return {
    rules: [
      {
        userAgent: '*',
        allow: '/',
        disallow: ['/api/', '/_next/', '/auth/'],
      },
    ],
    sitemap: 'https://omi.me/sitemap.xml',
  };
}
