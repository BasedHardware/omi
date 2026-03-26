'use client';

import { useState } from 'react';
import Link from 'next/link';
import { ChevronDown, Menu, X } from 'lucide-react';
import { brand } from '@/lib/config';
import { cn } from '@/lib/utils';

export function Navbar() {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-bg-primary/80 backdrop-blur-xl border-b border-white/5">
      <div className="mx-auto max-w-7xl px-6 flex items-center justify-between h-16">
        {/* Logo */}
        <Link href="/" className="font-display font-bold text-2xl tracking-tight text-white">
          {brand.nameLower}
        </Link>

        {/* Desktop Nav */}
        <div className="hidden md:flex items-center gap-8">
          <NavDropdown label="Products">
            <DropdownLink href={brand.links.product}>{brand.name}</DropdownLink>
            <DropdownLink href={brand.links.glass}>{brand.name} Glass</DropdownLink>
          </NavDropdown>
          <NavDropdown label="Use Cases">
            <DropdownLink href="#">Meetings</DropdownLink>
            <DropdownLink href="#">Note Taking</DropdownLink>
            <DropdownLink href="#">Voice Memos</DropdownLink>
          </NavDropdown>
          <Link href={brand.links.manifesto} className="text-sm text-text-secondary hover:text-white transition-colors">
            Manifesto
          </Link>
          <Link
            href={brand.links.order}
            className="bg-brand hover:bg-brand-dark text-white text-sm font-medium px-5 py-2 rounded-full transition-colors"
          >
            Buy now
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
          <Link href={brand.links.product} className="block text-text-secondary hover:text-white transition-colors">
            Products
          </Link>
          <Link href="#" className="block text-text-secondary hover:text-white transition-colors">
            Use Cases
          </Link>
          <Link href={brand.links.manifesto} className="block text-text-secondary hover:text-white transition-colors">
            Manifesto
          </Link>
          <Link
            href={brand.links.order}
            className="inline-block bg-brand text-white text-sm font-medium px-5 py-2 rounded-full"
          >
            Buy now
          </Link>
        </div>
      )}
    </nav>
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
        <div className="absolute top-full left-0 mt-2 bg-bg-secondary border border-white/10 rounded-xl p-2 min-w-[180px] shadow-2xl">
          {children}
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
