'use client';

import { usePathname, useRouter } from '@tschk/moonshine-next/navigation';
import Link from '@tschk/moonshine-next/link';
import { motion } from 'framer-motion';
import { Menu as MenuIcon } from 'lucide-react';
import { cn } from '@/lib/utils';
import { navItemsFor } from '@/lib/navigation';
import { useRecordingContext } from '@/components/recording/RecordingContext';

interface BottomNavigationProps {
  /** Opens the menu surface: the sidebar holds notifications, settings,
      and the account menu — the bottom bar's Menu button is its only
      mobile entry point. */
  onOpenMenu: () => void;
}

// Rendered from the shared navigation config (`src/lib/navigation.ts`), so the
// bottom bar and the desktop sidebar rail cannot drift apart.
const navItems = navItemsFor('bottom-bar');

export function BottomNavigation({ onOpenMenu }: BottomNavigationProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { state: recordingState } = useRecordingContext();
  const isRecording = recordingState === 'recording' || recordingState === 'paused';

  // Handle conversations click - always go to list view
  const handleConversationsClick = (e: React.MouseEvent) => {
    e.preventDefault();
    // Always navigate to /timeline with a timestamp to force navigation
    // This ensures the URL change is detected even if we're already on /timeline
    router.push('/conversations?v=' + Date.now(), { scroll: false });
  };

  return (
    <motion.nav
      initial={{ y: 100, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.25, ease: 'easeOut' }}
      className={cn(
        'fixed inset-x-3 bottom-3 z-40',
        'lg:hidden', // Only show on mobile
        'bg-bg-secondary/90 backdrop-blur-xl',
        'border border-stroke/[0.22]',
        'rounded-window',
        'shadow-[0_8px_32px_rgba(0,0,0,0.45)]',
        'pb-safe', // Safe area inset for devices with home indicators
      )}
      aria-label="Primary navigation"
    >
      <div className="flex h-16 items-stretch justify-around px-1.5">
        {navItems.map((item) => {
          const isActive =
            pathname === item.href ||
            (item.href === '/conversations' && pathname?.startsWith('/conversations')) ||
            (item.href === '/tasks' && pathname?.startsWith('/tasks'));
          const showRecordingBadge = item.href === '/record' && isRecording;
          const isConversations = item.href === '/conversations';
          const label = item.shortLabel ?? item.label;

          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={isConversations ? handleConversationsClick : undefined}
              className={cn(
                'relative flex flex-col items-center justify-center gap-0.5',
                'my-1.5 min-w-0 flex-1 rounded-chip',
                'transition-colors duration-150',
                isActive
                  ? 'text-text-primary'
                  : 'text-text-quaternary active:text-text-secondary',
              )}
              aria-label={item.label}
              aria-current={isActive ? 'page' : undefined}
            >
              {isActive && (
                <motion.span
                  layoutId="bottom-nav-active"
                  transition={{ type: 'spring', stiffness: 400, damping: 32 }}
                  className="absolute inset-0 rounded-chip bg-text-primary/10"
                />
              )}
              <div className="relative">
                <item.icon className="h-[22px] w-[22px]" />
                {showRecordingBadge && (
                  <span className="absolute -right-1 -top-1 flex h-3 w-3">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-400 opacity-75" />
                    <span className="relative inline-flex h-3 w-3 rounded-full bg-red-500" />
                  </span>
                )}
              </div>
              <span
                className={cn(
                  'text-[11px] leading-none',
                  isActive ? 'font-medium' : 'font-normal',
                )}
              >
                {label}
              </span>
            </Link>
          );
        })}

        {/* Menu - opens the sidebar: notifications, settings, account */}
        <button
          onClick={onOpenMenu}
          className={cn(
            'relative flex flex-col items-center justify-center gap-0.5',
            'my-1.5 min-w-0 flex-1 rounded-chip',
            'text-text-quaternary active:text-text-secondary',
            'transition-colors duration-150',
          )}
          aria-label="Menu"
        >
          <MenuIcon className="h-[22px] w-[22px]" />
          <span className="text-[11px] font-normal leading-none">Menu</span>
        </button>
      </div>
    </motion.nav>
  );
}
