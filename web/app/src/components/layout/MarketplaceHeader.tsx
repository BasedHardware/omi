'use client';

import Link from '@tschk/moonshine-next/link';
import Image from '@tschk/moonshine-next/image';
import { useAuth } from '@/components/auth/AuthProvider';
import { cn } from '@/lib/utils';

export function MarketplaceHeader() {
  const { user, loading, openLoginPanel } = useAuth();

  return (
    <header className="fixed left-0 right-0 top-0 z-50 h-12 border-b border-white/5 bg-[#0B0F17]">
      <div className="container mx-auto h-full px-3 sm:px-6 md:px-8">
        <div className="flex h-full items-center justify-between">
          {/* Logo - links to main apps page */}
          <Link href="/apps" className="flex items-center gap-2">
            <Image
              src="/omi-white.webp"
              alt="Omi"
              width={80}
              height={32}
              className="h-6 w-auto"
            />
          </Link>

          {/* Right side actions */}
          <div className="flex items-center gap-3">
            {loading ? (
              <div className="h-8 w-20 animate-pulse rounded-full bg-white/10" />
            ) : user ? (
              <>
                <Link
                  href="/conversations"
                  className={cn(
                    'rounded-full px-4 py-1.5 text-sm font-medium',
                    'bg-text-primary text-bg-primary',
                    'transition-colors hover:bg-text-primary/90',
                  )}
                >
                  Dashboard
                </Link>
              </>
            ) : (
              <button
                onClick={openLoginPanel}
                className={cn(
                  'rounded-full px-4 py-1.5 text-sm font-medium',
                  'bg-white text-gray-900',
                  'transition-colors hover:bg-gray-100',
                )}
              >
                Sign In
              </button>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
