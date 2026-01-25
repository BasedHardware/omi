'use client';

import { usePathname, useRouter } from 'next/navigation';
import Link from 'next/link';
import { motion } from 'framer-motion';
import { GanttChartSquare, MessageCircle, Mic, CheckSquare, Menu } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useRecordingContext } from '@/components/recording/RecordingContext';

interface BottomNavigationProps {
  onOpenSidebar: () => void;
}

// Core navigation items (excluding More)
const navItems = [
  { label: 'Conversations', href: '/conversations', icon: GanttChartSquare },
  { label: 'Chat', href: '/chat', icon: MessageCircle },
  { label: 'Record', href: '/record', icon: Mic },
  { label: 'Tasks', href: '/tasks', icon: CheckSquare },
];

export function BottomNavigation({ onOpenSidebar }: BottomNavigationProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { state: recordingState } = useRecordingContext();
  const isRecording = recordingState === 'recording' || recordingState === 'paused';

  // Handle conversations click - always go to list view
  const handleConversationsClick = (e: React.MouseEvent) => {
    e.preventDefault();
    // Always navigate to /conversations with a timestamp to force navigation
    // This ensures the URL change is detected even if we're already on /conversations
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
        'bg-bg-secondary/80 backdrop-blur-md',
        'border-t border-bg-tertiary',
        'pb-safe' // Safe area inset for devices with home indicators
      )}
      aria-label="Primary navigation"
    >
      <div className="flex items-center justify-around h-16 px-2">
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
              className={cn(
                'flex flex-col items-center justify-center',
                'w-14 h-14 rounded-xl',
                'transition-colors duration-150',
                isActive
                  ? 'bg-purple-primary/10 text-purple-primary'
                  : 'text-text-tertiary hover:text-text-secondary'
              )}
              aria-label={item.label}
              aria-current={isActive ? 'page' : undefined}
            >
              <div className="relative">
                <item.icon className="w-6 h-6" />
                {showRecordingBadge && (
                  <span className="absolute -top-1 -right-1 flex h-3 w-3">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75" />
                    <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500" />
                  </span>
                )}
              </div>
            </Link>
          );
        })}

        {/* More button - opens sidebar */}
        <button
          onClick={onOpenSidebar}
          className={cn(
            'flex flex-col items-center justify-center',
            'w-14 h-14 rounded-xl',
            'text-text-tertiary hover:text-text-secondary',
            'transition-colors duration-150'
          )}
          aria-label="More options"
        >
          <Menu className="w-6 h-6" />
        </button>
      </div>
    </motion.nav>
  );
}
