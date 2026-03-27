export const brand = {
  name: 'Nooto',
  nameLower: 'nooto',
  tagline: 'thought to action.',
  description:
    'Nooto summarizes your meetings & conversations, creates tasks, reminders & memories. Works on phone, desktop and all wearables.',
  color: '#3B82F6',
  company: 'Togo Dynamics LLC',
  address: '',
  email: 'help@togodynamics.com',
  links: {
    download: '/download',
    tryBrowser: '#',
    order: '#',
    product: '/product',
    glass: '#',
    apps: '#',
    docs: '/docs',
    manifesto: '#',
    privacy: '/privacy',
    integrations: '#',
  },
  social: {
    twitter: '#',
    linkedin: '#',
    github: 'https://github.com/BasedHardware/omi',
    discord: '#',
    youtube: '#',
  },
  footer: {
    company: [
      { label: 'Privacy', href: '/privacy' },
      { label: 'Manifesto', href: '#' },
    ],
    products: [
      { label: 'Nooto', href: '#' },
      { label: 'Nooto Glass', href: '#' },
      { label: 'Download', href: '/download' },
    ],
    resources: [
      { label: 'Help Center', href: '#' },
      { label: 'Docs', href: '/docs' },
      { label: 'App Store', href: '#' },
      { label: 'Feedback', href: '#' },
      { label: 'GitHub', href: 'https://github.com/BasedHardware/omi' },
      { label: 'Community', href: '#' },
    ],
  },
} as const;

export const trustLogos = [
  'Google',
  'Microsoft',
  'Amazon',
  'Meta',
  'Apple',
  'Salesforce',
  'Netflix',
  'Spotify',
  'Uber',
  'Airbnb',
] as const;
