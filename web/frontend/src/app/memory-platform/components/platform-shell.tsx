import Link from 'next/link';
import type { ReactNode } from 'react';
import { cn } from '@/src/lib/utils';

const NAV_LINKS = [
  { href: '/memory-platform', label: 'Overview' },
  { href: '/memory-platform/docs', label: 'Docs' },
  { href: '/memory-platform/embed', label: 'Embed' },
  { href: '/memory-platform/keys', label: 'Keys' },
  { href: '/memory-platform/billing', label: 'Billing' },
];

interface PlatformShellProps {
  active: string;
  children: ReactNode;
}

/**
 * Dark, hairline-bordered chrome shared by every memory-platform route. The
 * `dark` class is applied here because the app's root layout is light by
 * default and the shadcn primitives key off a `.dark` ancestor.
 */
export default function PlatformShell({ active, children }: PlatformShellProps) {
  return (
    <div className="dark min-h-screen bg-[#0a0a0a] pt-[6.5rem] text-neutral-100 antialiased md:pt-28">
      <div className="sticky top-[4.5rem] z-30 border-b border-white/10 bg-[#0a0a0a]/80 backdrop-blur md:top-20">
        <div className="mx-auto flex max-w-6xl items-center gap-6 px-5 py-4 md:px-8">
          <Link
            href="/memory-platform"
            className="flex items-center gap-2 text-sm font-semibold tracking-tight text-white"
          >
            <span className="h-2 w-2 rounded-full bg-[#b9f36b]" aria-hidden="true" />
            Memory Platform
          </Link>
          <nav
            aria-label="Memory platform"
            className="ml-auto flex items-center gap-1 overflow-x-auto text-sm"
          >
            {NAV_LINKS.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                aria-current={link.href === active ? 'page' : undefined}
                className={cn(
                  'whitespace-nowrap rounded-md px-3 py-1.5 transition-colors',
                  link.href === active
                    ? 'bg-white/10 text-white'
                    : 'text-neutral-400 hover:text-white',
                )}
              >
                {link.label}
              </Link>
            ))}
          </nav>
        </div>
      </div>

      <main className="mx-auto max-w-6xl px-5 pb-28 pt-12 md:px-8 md:pt-16">
        {children}
      </main>

      <footer className="border-t border-white/10">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-5 py-8 text-xs text-neutral-500 md:flex-row md:items-center md:justify-between md:px-8">
          <span>Omi / memory platform / v1</span>
          <span>The backend is the authority. Every other surface is a replica.</span>
        </div>
      </footer>
    </div>
  );
}
