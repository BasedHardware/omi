'use client';

import { usePathname, useRouter } from '@tschk/moonshine-next/navigation';
import Link from '@tschk/moonshine-next/link';
import { motion } from 'framer-motion';
import { GanttChartSquare, House, Mic, CheckSquare, Menu } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useRecordingContext } from '@/components/recording/RecordingContext';

interface BottomNavigationProps {
  onOpenSidebar: () => void;
}

// Core navigation items (excluding More). Labels match the rail, so the same
// destination is not named two different things on one device.
const navItems = [
  { label: 'Home', href: '/home', icon: House },
  { label: 'Conversations', href: '/conversations', icon: GanttChartSquare },
  { label: 'Record', href: '/record', icon: Mic },
  { label: 'Tasks', href: '/tasks', icon: CheckSquare },
];

/**
 * A tab is a labelled icon with a pill behind the icon rather than a filled
 * block: the white square the active tab used to be read as a button sitting on
 * top of the bar, and an unlabelled row of glyphs left the destinations to be
 * guessed at.
 */
function tabClasses(isActive: boolean): string {
  return cn(
    'group flex min-w-0 flex-1 flex-col items-center gap-1 rounded-2xl px-1 pt-2 pb-1',
    'transition-colors duration-150',
    isActive ? 'text-text-primary' : 'text-text-tertiary hover:text-text-secondary',
  );
}

function tabIconClasses(isActive: boolean): string {
  return cn(
    'relative flex h-8 w-12 items-center justify-center rounded-xl',
    'transition-colors duration-150',
    isActive ? 'bg-white/[0.14]' : 'group-hover:bg-white/[0.06]',
  );
}

export function BottomNavigation({ onOpenSidebar }: BottomNavigationProps) {
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
      transition={{ duration: 0.2, ease: 'easeOut' }}
      className={cn(
        'fixed bottom-0 inset-x-0 z-40',
        'lg:hidden', // Only show on mobile
        'bg-bg-secondary/90 backdrop-blur-xl',
        'border-t border-white/[0.06]',
        'pb-safe' // Safe area inset for devices with home indicators
      )}
      aria-label="Primary navigation"
    >
      <div className="flex items-stretch justify-around gap-0.5 px-2">
        {navItems.map((item) => {
          const isActive =
            pathname === item.href ||
            (item.href === '/conversations' && pathname?.startsWith('/conversations')) ||
            (item.href === '/tasks' && pathname?.startsWith('/tasks'));
          const showRecordingBadge = item.href === '/record' && isRecording;
          const isConversations = item.href === '/conversations';

          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={isConversations ? handleConversationsClick : undefined}
              className={tabClasses(isActive)}
              aria-label={item.label}
              aria-current={isActive ? 'page' : undefined}
            >
              <span className={tabIconClasses(isActive)}>
                <item.icon
                  className="h-[18px] w-[18px]"
                  strokeWidth={isActive ? 2.2 : 1.8}
                  aria-hidden="true"
                />
                {showRecordingBadge && (
                  <span className="absolute -top-0.5 -right-0.5 flex h-3 w-3">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75" />
                    <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500" />
                  </span>
                )}
              </span>
              <span className="text-[10px] font-medium leading-none">{item.label}</span>
            </Link>
          );
        })}

        {/* More button - opens sidebar */}
        <button
          onClick={onOpenSidebar}
          className={tabClasses(false)}
          aria-label="More options"
        >
          <span className={tabIconClasses(false)}>
            <Menu className="h-[18px] w-[18px]" strokeWidth={1.8} aria-hidden="true" />
          </span>
          <span className="text-[10px] font-medium leading-none">More</span>
        </button>
      </div>
    </motion.nav>
  );
}
