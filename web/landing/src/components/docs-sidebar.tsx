'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ChevronDown, Menu, X } from 'lucide-react';
import { docsNav } from '@/lib/docs-nav';
import { cn } from '@/lib/utils';
import { brand } from '@/lib/config';

export function DocsSidebar() {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <>
      {/* Mobile toggle */}
      <button
        onClick={() => setMobileOpen(!mobileOpen)}
        className="lg:hidden fixed top-20 left-4 z-40 w-10 h-10 rounded-xl bg-bg-secondary border border-white/10 flex items-center justify-center"
      >
        {mobileOpen ? <X size={18} /> : <Menu size={18} />}
      </button>

      {/* Sidebar */}
      <aside
        className={cn(
          'fixed top-16 left-0 bottom-0 w-64 bg-bg-primary overflow-y-auto no-scrollbar z-30 pt-8 pb-20 px-5',
          'lg:translate-x-0 transition-transform',
          mobileOpen ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <Link href="/docs" className="block px-3 mb-8">
          <span className="font-display font-bold text-base">{brand.name} Docs</span>
        </Link>

        <nav className="space-y-6">
          {docsNav.map((group) => (
            <NavGroup key={group.title} group={group} onNavigate={() => setMobileOpen(false)} />
          ))}
        </nav>
      </aside>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div className="fixed inset-0 bg-black/50 z-20 lg:hidden" onClick={() => setMobileOpen(false)} />
      )}
    </>
  );
}

function NavGroup({ group, onNavigate }: { group: (typeof docsNav)[number]; onNavigate: () => void }) {
  return (
    <div>
      <p className="px-3 text-xs font-semibold text-text-tertiary uppercase tracking-wider mb-2">{group.title}</p>
      <ul className="space-y-0.5">
        {group.items.map((item) => {
          if ('items' in item) {
            return <SubGroup key={item.title} title={item.title} items={item.items} onNavigate={onNavigate} />;
          }
          return <NavLink key={item.slug} slug={item.slug} title={item.title} onNavigate={onNavigate} />;
        })}
      </ul>
    </div>
  );
}

function SubGroup({
  title,
  items,
  onNavigate,
}: {
  title: string;
  items: { title: string; slug: string }[];
  onNavigate: () => void;
}) {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const isActive = items.some((item) => pathname === `/docs/${item.slug}`);

  return (
    <li>
      <button
        onClick={() => setOpen(!open)}
        className={cn(
          'w-full flex items-center justify-between px-3 py-1.5 text-sm rounded-lg transition-colors',
          isActive ? 'text-white' : 'text-text-tertiary hover:text-text-secondary hover:bg-white/[0.03]',
        )}
      >
        {title}
        <ChevronDown size={14} className={cn('transition-transform', (open || isActive) && 'rotate-180')} />
      </button>
      {(open || isActive) && (
        <ul className="ml-3 mt-0.5 border-l border-white/5 pl-3 space-y-0.5">
          {items.map((item) => (
            <NavLink key={item.slug} slug={item.slug} title={item.title} onNavigate={onNavigate} />
          ))}
        </ul>
      )}
    </li>
  );
}

function NavLink({ slug, title, onNavigate }: { slug: string; title: string; onNavigate: () => void }) {
  const pathname = usePathname();
  const isActive = pathname === `/docs/${slug}`;

  return (
    <li>
      <Link
        href={`/docs/${slug}`}
        onClick={onNavigate}
        className={cn(
          'block px-3 py-1.5 text-sm rounded-lg transition-colors',
          isActive
            ? 'bg-brand/10 text-brand font-medium'
            : 'text-text-tertiary hover:text-text-secondary hover:bg-white/[0.03]',
        )}
      >
        {title}
      </Link>
    </li>
  );
}
