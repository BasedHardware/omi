import Link from 'next/link';
import { brand } from '@/lib/config';
import { Twitter, Linkedin, Github, Youtube } from 'lucide-react';

const socialIcons = [
  { icon: Twitter, href: brand.social.twitter, label: 'Twitter' },
  { icon: Linkedin, href: brand.social.linkedin, label: 'LinkedIn' },
  { icon: Github, href: brand.social.github, label: 'GitHub' },
  { icon: Youtube, href: brand.social.youtube, label: 'YouTube' },
];

export function Footer() {
  return (
    <footer className="border-t border-white/5 bg-bg-primary">
      <div className="mx-auto max-w-7xl px-6 py-16">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-12">
          {/* Brand column */}
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

          {/* Link columns */}
          <FooterColumn title="Company" links={brand.footer.company} />
          <FooterColumn title="Products" links={brand.footer.products} />
          <FooterColumn title="Resources" links={brand.footer.resources} />
        </div>
      </div>

      <div className="border-t border-white/5 py-6 px-6">
        <p className="text-center text-text-tertiary text-xs">
          &copy; {new Date().getFullYear()} {brand.company}. All rights reserved.
        </p>
      </div>
    </footer>
  );
}

function FooterColumn({ title, links }: { title: string; links: ReadonlyArray<{ label: string; href: string }> }) {
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
