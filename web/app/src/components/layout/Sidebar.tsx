'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import {
  GanttChartSquare,
  MessageCircle,
  LayoutGrid,
  ListChecks,
  CalendarDays,
  Brain,
  LogOut,
  Menu,
  X,
  PanelLeftClose,
  PanelLeft,
  User,
  Puzzle,
  Code,
  Settings,
  Bell,
} from 'lucide-react';
import { useAuth } from '@/components/auth/AuthProvider';
import { useNotificationContext } from '@/components/notifications/NotificationContext';
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
    icon: <GanttChartSquare className="w-5 h-5" />,
  },
  {
    label: 'Recaps',
    href: '/recaps',
    icon: <CalendarDays className="w-5 h-5" />,
  },
  {
    label: 'Chat',
    href: '/chat',
    icon: <MessageCircle className="w-5 h-5" />,
  },
  {
    label: 'Apps',
    href: '/apps',
    icon: <LayoutGrid className="w-5 h-5" />,
  },
  {
    label: 'Tasks',
    href: '/tasks',
    icon: <ListChecks className="w-5 h-5" />,
  },
  {
    label: 'Memories',
    href: '/memories',
    icon: <Brain className="w-5 h-5" />,
  },
];

// Settings menu items for user dropdown
const settingsMenuItems = [
  { id: 'profile', label: 'Profile', icon: User },
  { id: 'integrations', label: 'Integrations', icon: Puzzle },
  { id: 'developer', label: 'Developer', icon: Code },
  { id: 'account', label: 'Account', icon: Settings },
];

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

export function Sidebar({
  isOpen,
  onClose,
}: SidebarProps) {
  const pathname = usePathname();
  const { user, signOut } = useAuth();
  const { toggleNotificationCenter, unreadCount } = useNotificationContext();
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [isHeaderHovered, setIsHeaderHovered] = useState(false);
  const [isTemporaryExpand, setIsTemporaryExpand] = useState(false);
  const isDesktop = useIsDesktop();
  const sidebarRef = useRef<HTMLElement>(null);
  const userMenuRef = useRef<HTMLDivElement>(null);

  // Load expanded state from localStorage on mount
  useEffect(() => {
    const saved = localStorage.getItem('sidebar-expanded');
    if (saved === 'true') {
      setIsExpanded(true);
    }
  }, []);

  // Click outside handler to close menu and collapse if temporary
  useEffect(() => {
    if (!showUserMenu || !isTemporaryExpand) return;

    const handleClickOutside = (e: MouseEvent) => {
      if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) {
        setShowUserMenu(false);
        setIsExpanded(false);
        setIsTemporaryExpand(false);
      }
    };

    // Delay adding listener to avoid immediate trigger
    const timer = setTimeout(() => {
      document.addEventListener('mousedown', handleClickOutside);
    }, 0);

    return () => {
      clearTimeout(timer);
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [showUserMenu, isTemporaryExpand]);

  // Toggle expand/collapse
  const handleToggleExpand = useCallback(() => {
    setIsExpanded((prev) => {
      const newValue = !prev;
      localStorage.setItem('sidebar-expanded', String(newValue));
      if (!newValue) {
        setShowUserMenu(false);
      }
      return newValue;
    });
    setIsTemporaryExpand(false); // Manual toggle makes it permanent
  }, []);

  const handleSignOut = async () => {
    await signOut();
    onClose();
  };

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

      {/* Sidebar - Mobile: slide in/out, Desktop: CSS transition for width */}
      <aside
        ref={sidebarRef}
        onMouseEnter={() => isDesktop && setIsHeaderHovered(true)}
        onMouseLeave={() => isDesktop && setIsHeaderHovered(false)}
        style={{
          // Mobile: slide in/out
          transform: !isDesktop ? `translateX(${isOpen ? 0 : -280}px)` : undefined,
          // Desktop: set width directly
          width: isDesktop ? sidebarWidth : 280,
        }}
        className={cn(
          'bg-bg-secondary border-r border-white/[0.04]',
          'flex flex-col flex-shrink-0',
          // Mobile: fixed overlay with slide transition
          'fixed top-0 left-0 bottom-0 z-50',
          'transition-[transform,width] duration-150 ease-out',
          // Desktop: relative in flow
          'lg:relative lg:z-auto'
        )}
      >
        {/* Header */}
        <div className="border-b border-white/[0.04]">
          {/* Logo row - fixed layout */}
          <div
            className={cn(
              'flex items-center pt-7 px-4 pb-4',
              isExpanded ? 'justify-between' : 'justify-center'
            )}
          >
            <Link
              href="/conversations"
              className="flex items-center gap-2"
            >
              <Image
                src="/omi-white.webp"
                alt="Omi"
                width={isExpanded ? 60 : 32}
                height={isExpanded ? 24 : 13}
                className="object-contain"
              />
              <span className="text-[10px] bg-purple-primary/20 text-purple-primary px-1.5 py-0.5 rounded-full font-medium">
                Beta
              </span>
            </Link>

            {/* Mobile close button */}
            {!isDesktop && (
              <button
                onClick={onClose}
                className="p-2 rounded-lg hover:bg-bg-tertiary transition-colors"
              >
                <X className="w-5 h-5 text-text-secondary" />
              </button>
            )}
          </div>

          {/* Toggle button row (desktop only) - appears on sidebar hover */}
          {isDesktop && (
            <div
              className={cn(
                'px-4 pb-3',
                isExpanded ? 'flex justify-end' : 'flex justify-center'
              )}
            >
              <button
                onClick={handleToggleExpand}
                className={cn(
                  'p-2 rounded-lg transition-all duration-200',
                  'text-text-tertiary hover:bg-bg-tertiary hover:text-text-secondary',
                  isHeaderHovered ? 'opacity-100' : 'opacity-0'
                )}
                title={isExpanded ? 'Collapse sidebar' : 'Expand sidebar'}
              >
                {isExpanded ? (
                  <PanelLeftClose className="w-4 h-4" />
                ) : (
                  <PanelLeft className="w-4 h-4" />
                )}
              </button>
            </div>
          )}

          {/* Notification bell */}
          <div
            className={cn(
              'px-4 pb-3',
              isExpanded ? 'flex justify-start' : 'flex justify-center'
            )}
          >
            <button
              onClick={toggleNotificationCenter}
              className={cn(
                'flex items-center rounded-lg transition-colors',
                'text-text-tertiary hover:bg-bg-tertiary hover:text-text-secondary',
                isExpanded ? 'px-2 py-2' : 'p-2'
              )}
              title="Notifications"
            >
              <div className="relative">
                <Bell className="w-5 h-5" />
                {unreadCount > 0 && (
                  <span
                    className={cn(
                      'absolute -top-2.5 -right-2.5',
                      'min-w-[18px] h-[18px] px-1',
                      'flex items-center justify-center',
                      'bg-red-500 text-white text-[10px] font-bold',
                      'rounded-full'
                    )}
                  >
                    {unreadCount > 99 ? '99+' : unreadCount}
                  </span>
                )}
              </div>
              {isExpanded && (
                <span className="ml-3 text-sm text-text-secondary">
                  Notifications
                </span>
              )}
            </button>
          </div>
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
                  <span className="font-medium">{item.label}</span>
                )}
              </Link>
            );
          })}
        </nav>

        {/* Spacer to push footer to bottom */}
        <div className="flex-1" />

        {/* Footer - User Section with Settings Menu */}
        <div className="border-t border-white/[0.04]">
          <div className="bg-bg-primary/30">
            <div className="relative" ref={userMenuRef}>
              <button
                onClick={() => {
                  if (isExpanded) {
                    setShowUserMenu(!showUserMenu);
                  } else {
                    // In collapsed mode, temporarily expand sidebar and show user menu
                    setIsExpanded(true);
                    setIsTemporaryExpand(true);
                    setShowUserMenu(true);
                  }
                }}
                className={cn(
                  'w-full flex items-center',
                  'hover:bg-bg-tertiary/50 transition-colors',
                  isExpanded ? 'gap-3 p-4' : 'justify-center p-3'
                )}
                title={!isExpanded ? 'Settings' : undefined}
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
                    <div className="flex-1 min-w-0 text-left">
                      <p className="text-sm font-medium text-text-primary truncate">
                        {user?.displayName || 'User'}
                      </p>
                      <p className="text-xs text-text-quaternary truncate">
                        {user?.email}
                      </p>
                    </div>

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

              {/* User menu dropdown with settings */}
              <AnimatePresence>
                {showUserMenu && isExpanded && (
                  <motion.div
                    initial={{ opacity: 0, y: 8, scale: 0.96 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: 8, scale: 0.96 }}
                    transition={{ duration: 0.15 }}
                    className={cn(
                      'absolute bottom-full left-2 right-2 mb-3',
                      'bg-[#1a1a1f]/95 backdrop-blur-xl',
                      'rounded-2xl overflow-hidden',
                      'shadow-[0_0_0_1px_rgba(255,255,255,0.06),0_-20px_40px_-10px_rgba(139,92,246,0.15),0_10px_30px_-5px_rgba(0,0,0,0.5)]'
                    )}
                  >
                    {/* User info header */}
                    <div className="p-4 border-b border-white/[0.04]">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-500/20 to-purple-600/10 flex items-center justify-center ring-1 ring-white/[0.08] overflow-hidden">
                          {user?.photoURL ? (
                            <Image
                              src={user.photoURL}
                              alt={user.displayName || 'User'}
                              width={40}
                              height={40}
                              className="object-cover"
                            />
                          ) : (
                            <span className="text-white/70 text-sm font-medium">
                              {user?.displayName?.charAt(0) || 'U'}
                            </span>
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-white/90 truncate">
                            {user?.displayName || 'User'}
                          </p>
                          <p className="text-xs text-white/40 truncate">
                            {user?.email}
                          </p>
                        </div>
                      </div>
                    </div>

                    {/* Settings list - single column */}
                    <div className="py-1.5">
                      {settingsMenuItems.map((item) => (
                        <Link
                          key={item.id}
                          href={`/settings?section=${item.id}`}
                          onClick={() => {
                            setShowUserMenu(false);
                            if (isTemporaryExpand) {
                              setIsExpanded(false);
                              setIsTemporaryExpand(false);
                            }
                            if (!isDesktop) onClose();
                          }}
                          className={cn(
                            'group flex items-center gap-3 px-4 py-2.5',
                            'transition-all duration-150',
                            'hover:bg-white/[0.04]'
                          )}
                        >
                          <item.icon className="w-4 h-4 text-white/40 group-hover:text-purple-400 transition-colors flex-shrink-0" />
                          <span className="text-sm text-white/70 group-hover:text-white/90">
                            {item.label}
                          </span>
                        </Link>
                      ))}
                    </div>

                    {/* Sign out - separated */}
                    <div className="p-2 pt-0 border-t border-white/[0.04] mt-1">
                      <button
                        onClick={handleSignOut}
                        className={cn(
                          'w-full flex items-center gap-2.5 p-2.5 rounded-xl',
                          'text-red-400/70 hover:text-red-400',
                          'hover:bg-red-500/[0.08] transition-all'
                        )}
                      >
                        <LogOut className="w-4 h-4" />
                        <span className="text-sm">Sign Out</span>
                      </button>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        </div>
      </aside>
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
