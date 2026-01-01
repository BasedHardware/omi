'use client';

import { useState, useEffect, useCallback } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import {
  MessageSquare,
  Sparkles,
  LayoutGrid,
  CheckSquare,
  Brain,
  Settings,
  LogOut,
  Menu,
  X,
  PanelLeftClose,
  PanelLeft,
} from 'lucide-react';
import { useAuth } from '@/components/auth/AuthProvider';
import { cn } from '@/lib/utils';

// Hook to detect if we're on desktop
function useIsDesktop() {
  const [isDesktop, setIsDesktop] = useState(false);

  useEffect(() => {
    const checkIsDesktop = () => setIsDesktop(window.innerWidth >= 1024);
    checkIsDesktop();
    window.addEventListener('resize', checkIsDesktop);
    return () => window.removeEventListener('resize', checkIsDesktop);
  }, []);

  return isDesktop;
}

interface NavItem {
  label: string;
  href: string;
  icon: React.ReactNode;
}

const navItems: NavItem[] = [
  {
    label: 'Conversations',
    href: '/conversations',
    icon: <MessageSquare className="w-5 h-5" />,
  },
  {
    label: 'Chat',
    href: '/chat',
    icon: <Sparkles className="w-5 h-5" />,
  },
  {
    label: 'Apps',
    href: '/apps',
    icon: <LayoutGrid className="w-5 h-5" />,
  },
  {
    label: 'Tasks',
    href: '/tasks',
    icon: <CheckSquare className="w-5 h-5" />,
  },
  {
    label: 'Memories',
    href: '/memories',
    icon: <Brain className="w-5 h-5" />,
  },
];

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
  isExpanded: boolean;
  isPinned: boolean;
  onTogglePin: () => void;
  onHoverChange: (hovered: boolean) => void;
}

export function Sidebar({
  isOpen,
  onClose,
  isExpanded,
  isPinned,
  onTogglePin,
  onHoverChange,
}: SidebarProps) {
  const pathname = usePathname();
  const { user, signOut } = useAuth();
  const [showUserMenu, setShowUserMenu] = useState(false);
  const isDesktop = useIsDesktop();

  const handleSignOut = async () => {
    await signOut();
    onClose();
  };

  // Handle mouse enter/leave for desktop hover
  const handleMouseEnter = useCallback(() => {
    if (isDesktop && !isPinned) {
      onHoverChange(true);
    }
  }, [isDesktop, isPinned, onHoverChange]);

  const handleMouseLeave = useCallback(() => {
    if (isDesktop && !isPinned) {
      onHoverChange(false);
      setShowUserMenu(false);
    }
  }, [isDesktop, isPinned, onHoverChange]);

  // Collapsed width (icon only) vs expanded width
  const sidebarWidth = isExpanded ? 280 : 72;

  return (
    <>
      {/* Mobile overlay */}
      <AnimatePresence>
        {isOpen && !isDesktop && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 bg-black/50 z-40 lg:hidden"
            onClick={onClose}
          />
        )}
      </AnimatePresence>

      {/* Sidebar - Mobile: slide in/out, Desktop: always visible but collapses */}
      <motion.aside
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        initial={false}
        animate={{
          width: isDesktop ? sidebarWidth : 280,
          x: !isDesktop && !isOpen ? -280 : 0
        }}
        transition={{ type: 'spring', damping: 25, stiffness: 300 }}
        className={cn(
          'bg-bg-secondary border-r border-bg-tertiary',
          'flex flex-col flex-shrink-0',
          // Mobile: fixed overlay
          'fixed top-0 left-0 bottom-0 z-50',
          // Desktop: relative in flow
          'lg:relative lg:z-auto'
        )}
      >
        {/* Header */}
        <div className={cn(
          'flex items-center p-4 border-b border-bg-tertiary',
          isExpanded ? 'justify-between' : 'justify-center'
        )}>
          <Link
            href="/conversations"
            className={cn(
              'flex items-center gap-3',
              !isExpanded && 'justify-center'
            )}
          >
            <div className="w-10 h-10 relative flex-shrink-0">
              <Image
                src="/logo.png"
                alt="Omi"
                fill
                className="object-contain"
              />
            </div>
            {isExpanded && (
              <motion.span
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="font-display font-semibold text-lg text-text-primary"
              >
                Omi
              </motion.span>
            )}
          </Link>

          {/* Pin button (desktop, expanded) / Close button (mobile) */}
          {isDesktop ? (
            isExpanded && (
              <motion.button
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                onClick={onTogglePin}
                className={cn(
                  'p-2 rounded-lg transition-colors',
                  isPinned
                    ? 'bg-purple-primary/10 text-purple-primary hover:bg-purple-primary/20'
                    : 'text-text-tertiary hover:bg-bg-tertiary hover:text-text-secondary'
                )}
                title={isPinned ? 'Collapse sidebar' : 'Keep sidebar expanded'}
              >
                {isPinned ? (
                  <PanelLeftClose className="w-4 h-4" />
                ) : (
                  <PanelLeft className="w-4 h-4" />
                )}
              </motion.button>
            )
          ) : (
            <button
              onClick={onClose}
              className="p-2 rounded-lg hover:bg-bg-tertiary transition-colors"
            >
              <X className="w-5 h-5 text-text-secondary" />
            </button>
          )}
        </div>

        {/* Navigation */}
        <nav className={cn(
          'py-2 space-y-1',
          isExpanded ? 'px-3' : 'px-2'
        )}>
          {navItems.map((item) => {
            const isActive =
              pathname === item.href ||
              (item.href === '/conversations' &&
                pathname?.startsWith('/conversations'));

            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => {
                  if (!isDesktop) onClose();
                }}
                title={!isExpanded ? item.label : undefined}
                className={cn(
                  'flex items-center rounded-xl',
                  'transition-all duration-150',
                  isExpanded ? 'gap-3 px-4 py-3' : 'justify-center p-3',
                  isActive
                    ? 'bg-purple-primary/10 text-purple-primary border-l-[3px] border-purple-primary'
                    : 'text-text-secondary hover:bg-bg-tertiary hover:text-text-primary'
                )}
              >
                <span className="flex-shrink-0">{item.icon}</span>
                {isExpanded && (
                  <motion.span
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="font-medium"
                  >
                    {item.label}
                  </motion.span>
                )}
              </Link>
            );
          })}
        </nav>

        {/* Spacer to push footer to bottom */}
        <div className="flex-1" />

        {/* Footer - Settings & User at bottom */}
        <div>
          <div className="border-t border-bg-tertiary">
            <Link
              href="/settings"
              title={!isExpanded ? 'Settings' : undefined}
              className={cn(
                'flex items-center',
                'text-text-secondary hover:bg-bg-tertiary hover:text-text-primary',
                'transition-colors',
                isExpanded ? 'gap-3 px-7 py-3' : 'justify-center p-3'
              )}
            >
              <Settings className="w-5 h-5 flex-shrink-0" />
              {isExpanded && (
                <motion.span
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="font-medium"
                >
                  Settings
                </motion.span>
              )}
            </Link>
          </div>

          {/* User Section - Visually distinct */}
          <div className="border-t border-bg-tertiary bg-bg-primary/50">
            <div className="relative">
              <button
                onClick={() => isExpanded && setShowUserMenu(!showUserMenu)}
                className={cn(
                  'w-full flex items-center',
                  'hover:bg-bg-tertiary/50 transition-colors',
                  isExpanded ? 'gap-3 p-4' : 'justify-center p-3'
                )}
                title={!isExpanded ? user?.displayName || 'User' : undefined}
              >
                {/* Avatar */}
                <div className="w-9 h-9 rounded-full overflow-hidden bg-bg-tertiary flex-shrink-0 ring-2 ring-bg-tertiary">
                  {user?.photoURL ? (
                    <Image
                      src={user.photoURL}
                      alt={user.displayName || 'User'}
                      width={36}
                      height={36}
                      className="object-cover"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-text-tertiary text-sm font-medium">
                      {user?.displayName?.charAt(0) || 'U'}
                    </div>
                  )}
                </div>

                {isExpanded && (
                  <>
                    {/* Name & email */}
                    <motion.div
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      className="flex-1 min-w-0 text-left"
                    >
                      <p className="text-sm font-medium text-text-primary truncate">
                        {user?.displayName || 'User'}
                      </p>
                      <p className="text-xs text-text-quaternary truncate">
                        {user?.email}
                      </p>
                    </motion.div>

                    {/* Dropdown indicator */}
                    <svg
                      className={cn(
                        'w-4 h-4 text-text-quaternary transition-transform',
                        showUserMenu && 'rotate-180'
                      )}
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M5 15l7-7 7 7"
                      />
                    </svg>
                  </>
                )}
              </button>

              {/* User menu dropdown */}
              <AnimatePresence>
                {showUserMenu && isExpanded && (
                  <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: 10 }}
                    transition={{ duration: 0.15 }}
                    className={cn(
                      'absolute bottom-full left-3 right-3 mb-2',
                      'bg-bg-tertiary rounded-xl shadow-strong',
                      'border border-bg-quaternary overflow-hidden'
                    )}
                  >
                    <button
                      onClick={handleSignOut}
                      className={cn(
                        'w-full flex items-center gap-3 px-4 py-3',
                        'text-error hover:bg-error/10 transition-colors'
                      )}
                    >
                      <LogOut className="w-5 h-5" />
                      <span className="font-medium">Sign Out</span>
                    </button>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        </div>
      </motion.aside>
    </>
  );
}

// Mobile menu button component
export function MobileMenuButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'lg:hidden p-2 rounded-lg',
        'hover:bg-bg-tertiary transition-colors',
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/50'
      )}
    >
      <Menu className="w-6 h-6 text-text-secondary" />
    </button>
  );
}
