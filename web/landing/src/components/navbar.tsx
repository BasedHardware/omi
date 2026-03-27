'use client';

import { useState } from 'react';
import { ChevronDown, Menu, X, Globe } from 'lucide-react';
import { useTranslations, useLocale } from 'next-intl';
import { Link, useRouter, usePathname } from '@/i18n/navigation';
import { brand } from '@/lib/config';
import { cn } from '@/lib/utils';
import { type Locale } from '@/i18n/routing';

const locales: { code: Locale; label: string }[] = [
  { code: 'en', label: 'English' },
  { code: 'pt-br', label: 'Portugu\u00eas' },
  { code: 'es', label: 'Espa\u00f1ol' },
];

export function Navbar() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const t = useTranslations('navbar');

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-transparent backdrop-blur-md border-b border-white/[0.02]">
      <div className="mx-auto max-w-7xl px-6 flex items-center justify-between h-16">
        {/* Logo */}
        <Link href="/" className="font-display font-bold text-2xl tracking-tight text-white">
          {brand.nameLower}
        </Link>

        {/* Desktop Nav */}
        <div className="hidden md:flex items-center gap-8">
          <NavDropdown label={t('products')}>
            <DropdownLink href="/product">{brand.name}</DropdownLink>
            <DropdownLink href="/apps">{t('appStore')}</DropdownLink>
            <DropdownLink href="/download">{t('download')}</DropdownLink>
          </NavDropdown>
          <NavDropdown label={t('resources')}>
            <DropdownLink href="/docs">{t('docs')}</DropdownLink>
            <DropdownLink href="/faq">FAQ</DropdownLink>
            <DropdownLink href="/privacy">{t('privacy')}</DropdownLink>
          </NavDropdown>
          <LanguageSwitcher />
          <Link
            href="/download"
            className="bg-brand hover:bg-brand-dark text-white text-sm font-medium px-5 py-2 rounded-full transition-colors"
          >
            {t('getStarted')}
          </Link>
        </div>

        {/* Mobile toggle */}
        <button className="md:hidden text-white p-2" onClick={() => setMobileOpen(!mobileOpen)}>
          {mobileOpen ? <X size={24} /> : <Menu size={24} />}
        </button>
      </div>

      {/* Mobile menu */}
      {mobileOpen && (
        <div className="md:hidden bg-bg-primary border-t border-white/5 px-6 py-6 space-y-4">
          <Link href="/product" className="block text-text-secondary hover:text-white transition-colors">
            {t('products')}
          </Link>
          <Link href="/apps" className="block text-text-secondary hover:text-white transition-colors">
            {t('appStore')}
          </Link>
          <Link href="/docs" className="block text-text-secondary hover:text-white transition-colors">
            {t('docs')}
          </Link>
          <Link href="/faq" className="block text-text-secondary hover:text-white transition-colors">
            FAQ
          </Link>
          <LanguageSwitcher />
          <Link
            href="/download"
            className="inline-block bg-brand text-white text-sm font-medium px-5 py-2 rounded-full"
          >
            {t('buyNow')}
          </Link>
        </div>
      )}
    </nav>
  );
}

function LanguageSwitcher() {
  const [open, setOpen] = useState(false);
  const locale = useLocale();
  const router = useRouter();
  const pathname = usePathname();

  const currentLocale = locales.find((l) => l.code === locale) || locales[0];

  function switchLocale(newLocale: Locale) {
    router.replace(pathname, { locale: newLocale });
    setOpen(false);
  }

  return (
    <div className="relative" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button className="flex items-center gap-1.5 text-sm text-text-secondary hover:text-white transition-colors">
        <Globe size={15} />
        {currentLocale.label}
        <ChevronDown size={14} className={cn('transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <div className="absolute top-full left-0 pt-2 min-w-[140px]">
          <div className="bg-bg-secondary border border-white/10 rounded-xl p-2 shadow-2xl">
            {locales.map((l) => (
              <button
                key={l.code}
                onClick={() => switchLocale(l.code)}
                className={cn(
                  'w-full text-left block px-4 py-2 text-sm rounded-lg transition-colors',
                  l.code === locale
                    ? 'text-brand bg-brand/10'
                    : 'text-text-secondary hover:text-white hover:bg-white/5',
                )}
              >
                {l.label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function NavDropdown({ label, children }: { label: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="relative" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button className="flex items-center gap-1 text-sm text-text-secondary hover:text-white transition-colors">
        {label}
        <ChevronDown size={14} className={cn('transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <div className="absolute top-full left-0 pt-2 min-w-[180px]">
          <div className="bg-bg-secondary border border-white/10 rounded-xl p-2 shadow-2xl">
            {children}
          </div>
        </div>
      )}
    </div>
  );
}

function DropdownLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      className="block px-4 py-2 text-sm text-text-secondary hover:text-white hover:bg-white/5 rounded-lg transition-colors"
    >
      {children}
    </Link>
  );
}
