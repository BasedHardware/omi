'use client';

import { Twitter, Linkedin, Github, Youtube } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Link } from '@/i18n/navigation';
import { brand } from '@/lib/config';

const socialIcons = [
  { icon: Twitter, href: brand.social.twitter, label: 'Twitter' },
  { icon: Linkedin, href: brand.social.linkedin, label: 'LinkedIn' },
  { icon: Github, href: brand.social.github, label: 'GitHub' },
  { icon: Youtube, href: brand.social.youtube, label: 'YouTube' },
];

export function Footer() {
  const t = useTranslations('footer');

  const companyLinks = [
    { label: t('privacy'), href: '/privacy' },
    { label: 'FAQ', href: '/faq' },
  ];

  const productLinks = [
    { label: 'Nooto', href: '/product' },
    { label: t('download'), href: '/download' },
    { label: t('appStore'), href: '/apps' },
  ];

  const resourceLinks = [
    { label: t('docs'), href: '/docs' },
    { label: 'FAQ', href: '/faq' },
    { label: 'GitHub', href: 'https://github.com/BasedHardware/omi' },
    { label: `${brand.email}`, href: `mailto:${brand.email}` },
  ];

  return (
    <footer className="border-t border-white/5 bg-bg-primary">
      <div className="mx-auto max-w-7xl px-6 py-16">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-12">
          <div>
            <p className="font-display font-bold text-lg mb-4">{brand.tagline}</p>
            <div className="text-text-tertiary text-sm space-y-1">
              <p>{brand.company}</p>
              {brand.address && <p>{brand.address}</p>}
              <Link href={`mailto:${brand.email}`} className="hover:text-white transition-colors">
                {brand.email}
              </Link>
            </div>
            <div className="flex items-center gap-3 mt-6">
              {socialIcons.map(({ icon: Icon, href, label }) => (
                <Link
                  key={label}
                  href={href}
                  aria-label={label}
                  className="w-9 h-9 rounded-full bg-white/10 flex items-center justify-center hover:bg-white/20 transition-colors"
                >
                  <Icon size={16} />
                </Link>
              ))}
            </div>
          </div>

          <FooterColumn title={t('company')} links={companyLinks} />
          <FooterColumn title={t('products')} links={productLinks} />
          <FooterColumn title={t('resources')} links={resourceLinks} />
        </div>
      </div>

      <div className="border-t border-white/5 py-6 px-6">
        <p className="text-center text-text-tertiary text-xs">
          &copy; {new Date().getFullYear()} {brand.company}. {t('allRightsReserved')}
        </p>
      </div>
    </footer>
  );
}

function FooterColumn({ title, links }: { title: string; links: Array<{ label: string; href: string }> }) {
  return (
    <div>
      <p className="font-display font-semibold text-sm mb-4">{title}</p>
      <ul className="space-y-3">
        {links.map((link) => (
          <li key={link.label}>
            <Link href={link.href} className="text-text-tertiary text-sm hover:text-white transition-colors">
              {link.label}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
