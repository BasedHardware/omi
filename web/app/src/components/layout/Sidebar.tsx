'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import Image from '@tschk/moonshine-next/image';
import Link from '@tschk/moonshine-next/link';
import { usePathname } from '@tschk/moonshine-next/navigation';
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';
import confetti from 'canvas-confetti';
import {
  GanttChartSquare,
  House,
  LayoutGrid,
  ListChecks,
  CalendarDays,
  Brain,
  LogOut,
  Menu,
  X,
  PanelLeftClose,
  PanelLeft,
  Puzzle,
  Code,
  Settings,
  Shield,
  LifeBuoy,
  Bell,
  Download,
  Mic,
  MessageSquare,
  Smartphone,
  type LucideIcon,
} from 'lucide-react';

// Apple logo SVG component
function AppleLogo({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.8-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z" />
    </svg>
  );
}

// Discord icon SVG component
function DiscordIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028 14.09 14.09 0 0 0 1.226-1.994.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z" />
    </svg>
  );
}
import { useAuth } from '@/components/auth/AuthProvider';
import { useNotificationContext } from '@/components/notifications/NotificationContext';
import { cn } from '@/lib/utils';
import { SETTINGS_SECTIONS, type SettingsSectionId } from '@/lib/settingsSections';
import { PROFILE_MENU_MAX_HEIGHT } from '@/lib/profileMenu';
import { ConfettiBurst } from '@/components/ui/ConfettiBurst';
import { OpenSurface } from '@/components/ui/OpenSurface';

/** How long the banner takes to swell and pop, and the burst to clear it. */
const BANNER_BURST_MS = 420;
const BANNER_CONFETTI_COLORS = ['#FFFFFF', '#E5E5E5', '#B0B0B0', '#888888'];

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

// Order mirrors the desktop rail (`SidebarNavItem.mainItems`): Home, then
// Conversations, Memories, Tasks, then the surfaces web adds on top. Chat has
// no row of its own on either client — it is what Home opens into.
const navItems: NavItem[] = [
  {
    label: 'Home',
    href: '/home',
    icon: <House className="w-5 h-5" />,
  },
  {
    label: 'Conversations',
    href: '/conversations',
    icon: <GanttChartSquare className="w-5 h-5" />,
  },
  {
    label: 'Memories',
    href: '/memories',
    icon: <Brain className="w-5 h-5" />,
  },
  {
    label: 'Tasks',
    href: '/tasks',
    icon: <ListChecks className="w-5 h-5" />,
  },
];

// Settings menu items for user dropdown.
// The icon map is total over SettingsSectionId, so adding a settings section
// without giving it a nav entry fails to compile.
const SETTINGS_SECTION_ICONS: Record<SettingsSectionId, LucideIcon> = {
  privacy: Shield,
  developer: Code,
  account: Settings,
};

const settingsMenuItems = SETTINGS_SECTIONS.map((section) => ({
  ...section,
  icon: SETTINGS_SECTION_ICONS[section.id],
}));

/**
 * One row of the profile menu. Every row carries its own radius and sits
 * inside the container's padding, so the menu reads as a stack of chips rather
 * than as full-bleed bands butting against the surface edge.
 */
function MenuRow({
  href,
  icon: Icon,
  label,
  external = false,
  onNavigate,
}: {
  href: string;
  icon: LucideIcon | ((props: { className?: string }) => React.ReactNode);
  label: string;
  external?: boolean;
  onNavigate: () => void;
}) {
  const className = cn(
    'group flex items-center gap-3 rounded-card px-3 py-2',
    'text-text-tertiary hover:bg-bg-tertiary hover:text-text-primary',
    'transition-colors',
  );
  const content = (
    <>
      <Icon className="w-4 h-4 flex-shrink-0" />
      <span className="whitespace-nowrap text-sm">{label}</span>
    </>
  );

  if (external) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        onClick={onNavigate}
        className={className}
      >
        {content}
      </a>
    );
  }

  return (
    <Link href={href} onClick={onNavigate} className={className}>
      {content}
    </Link>
  );
}

/**
 * The profile menu's contents, shared by both of its presentations: grown
 * inside the profile surface when the rail is expanded, and floated beside the
 * rail when it is collapsed. One list, so the two cannot drift apart.
 */
function ProfileMenuRows({
  onNavigate,
  onSignOut,
}: {
  onNavigate: () => void;
  onSignOut: () => void;
}) {
  return (
    <>
      <div className="p-2 space-y-0.5">
        <MenuRow
          href="/connectors"
          icon={Puzzle}
          label="Connectors"
          onNavigate={onNavigate}
        />
        {settingsMenuItems.map((item) => (
          <MenuRow
            key={item.id}
            href={`/settings?section=${item.id}`}
            icon={item.icon}
            label={item.label}
            onNavigate={onNavigate}
          />
        ))}
      </div>

      <div className="border-t border-stroke/60 p-2 space-y-0.5">
        <MenuRow
          href="https://omi.me/download"
          icon={Download}
          label="Download"
          external
          onNavigate={onNavigate}
        />
        <MenuRow href="/help" icon={LifeBuoy} label="Help" onNavigate={onNavigate} />
        <MenuRow
          href="https://feedback.omi.me"
          icon={MessageSquare}
          label="Feedback"
          external
          onNavigate={onNavigate}
        />
        <MenuRow
          href="http://discord.omi.me"
          icon={DiscordIcon}
          label="Discord"
          external
          onNavigate={onNavigate}
        />
        <button
          onClick={onSignOut}
          className={cn(
            'w-full flex items-center gap-3 rounded-card px-3 py-2',
            'text-red-400/80 hover:text-red-400 hover:bg-red-500/[0.08]',
            'transition-colors',
          )}
        >
          <LogOut className="w-4 h-4 flex-shrink-0" />
          <span className="whitespace-nowrap text-sm">Sign Out</span>
        </button>
      </div>
    </>
  );
}

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

export function Sidebar({ isOpen, onClose }: SidebarProps) {
  const pathname = usePathname();
  const { user, signOut } = useAuth();
  const { toggleNotificationCenter, unreadCount } = useNotificationContext();
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [mobileAppDismissed, setMobileAppDismissed] = useState(false);
  // Dismissal runs in two beats: the burst fires over the still-present banner,
  // then the banner pops out. Collapsing them into one state would unmount the
  // banner — and the burst anchored to it — on the same frame.
  const [bannerBursting, setBannerBursting] = useState(false);
  const shouldReduceMotion = useReducedMotion();
  const isDesktop = useIsDesktop();
  const sidebarRef = useRef<HTMLElement>(null);
  const userMenuRef = useRef<HTMLDivElement>(null);

  // Load expanded state from localStorage on mount
  useEffect(() => {
    const saved = localStorage.getItem('sidebar-expanded');
    if (saved === 'true') {
      setIsExpanded(true);
    }
    if (localStorage.getItem('mobile-app-banner-dismissed') === 'true') {
      setMobileAppDismissed(true);
    }
  }, []);

  // Click outside handler to close menu and collapse if temporary
  useEffect(() => {
    if (!showUserMenu) return;

    const handleClickOutside = (e: MouseEvent) => {
      if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) {
        setShowUserMenu(false);
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
  }, [showUserMenu]);

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
  }, []);

  const closeUserMenu = useCallback(() => {
    setShowUserMenu(false);
    if (!isDesktop) onClose();
  }, [isDesktop, onClose]);

  const handleSignOut = useCallback(async () => {
    await signOut();
    onClose();
  }, [signOut, onClose]);

  const handleDismissMobileApp = useCallback(
    (event: React.MouseEvent<HTMLButtonElement>) => {
      event.preventDefault();
      event.stopPropagation();

      const reduceMotionNow =
        shouldReduceMotion ||
        window.matchMedia('(prefers-reduced-motion: reduce)').matches;

      if (!reduceMotionNow) {
        const rect = event.currentTarget.getBoundingClientRect();
        confetti({
          particleCount: 48,
          spread: 360,
          startVelocity: 28,
          decay: 0.9,
          gravity: 0.65,
          scalar: 0.72,
          ticks: 90,
          origin: {
            x: (rect.left + rect.width / 2) / window.innerWidth,
            y: (rect.top + rect.height / 2) / window.innerHeight,
          },
          colors: BANNER_CONFETTI_COLORS,
          disableForReducedMotion: true,
          zIndex: 10000,
        });
      }

      setBannerBursting(true);
      localStorage.setItem('mobile-app-banner-dismissed', 'true');
      window.setTimeout(() => setMobileAppDismissed(true), BANNER_BURST_MS);
    },
    [shouldReduceMotion],
  );

  // Collapsed width (icon only) vs expanded width
  const sidebarWidth = isExpanded ? 280 : 72;

  // On mobile, sidebar should always show text (behave as expanded)
  const showText = !isDesktop || isExpanded;

  const menuOpen = showUserMenu;

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
        style={{
          // Mobile: slide in/out
          transform: !isDesktop ? `translateX(${isOpen ? 0 : -280}px)` : undefined,
          // Desktop: set width directly
          width: isDesktop ? sidebarWidth : 280,
          willChange: !isDesktop ? 'transform' : undefined,
        }}
        className={cn(
          // The rail sits on the raw window; the inset content pane is the
          // only card, so it carries no fill or divider of its own on desktop.
          'bg-bg-secondary lg:bg-transparent',
          'flex flex-col flex-shrink-0',
          // Mobile: fixed overlay with slide transition
          'fixed top-0 left-0 bottom-0 z-50',
          // Desktop animates its width to match the macOS rail
          // (.omiAnimation(.easeInOut(duration: 0.2))); mobile slides instead.
          // Deliberately NOT overflow-hidden: the collapsed profile menu opens
          // beside the rail, and clipping the rail clips the menu out of
          // existence. Label clipping belongs to the rows that have labels.
          'transition-transform duration-150 ease-out',
          'lg:transition-[width] lg:duration-200 lg:ease-in-out',
          // Desktop: relative in flow
          'lg:relative lg:z-auto',
        )}
      >
        {/* Header: the mark, then the two controls that act on the shell
            itself. They share the nav's horizontal padding so they read as one
            column of icons with the destinations below, rather than as a
            separate toolbar. */}
        <div className="overflow-hidden px-2 pt-6 pb-3">
          {/* Expanded, the mark and the two shell controls share one line.
              Collapsed there is not room for both — two 36px controls do not
              fit in a 56px column — so they stack under the mark. */}
          <div
            className={cn(
              'flex gap-2',
              showText ? 'flex-row items-center justify-between' : 'flex-col',
            )}
          >
            <Link
              href="/conversations"
              className="flex h-6 items-center gap-2 px-2"
              aria-label="Omi"
            >
              <Image
                src="/omi-white.webp"
                alt="Omi"
                width={60}
                height={24}
                className="h-[18px] w-auto flex-shrink-0 object-contain"
              />
              <span
                className={cn(
                  'whitespace-nowrap rounded-full bg-white/[0.10] px-1.5 py-0.5',
                  'text-[10px] font-medium text-text-secondary',
                  'transition-opacity duration-150',
                  showText ? 'opacity-100 delay-75' : 'opacity-0',
                )}
              >
                Beta
              </span>
            </Link>

            {/* Collapsed, these stack: two 36px controls side by side overflow
                a 56px column, so a row would clip the second one. */}
            <div
              className={cn(
                'flex gap-1',
                showText ? 'flex-row items-center' : 'flex-col items-center',
              )}
            >
              <button
                onClick={toggleNotificationCenter}
                className={cn(
                  'flex items-center justify-center p-2 rounded-element transition-colors',
                  'text-text-tertiary hover:bg-bg-tertiary hover:text-text-primary',
                )}
                title="Notifications"
                aria-label="Notifications"
              >
                <div className="relative">
                  <Bell className="w-5 h-5" />
                  <span className="t-badge" data-open={unreadCount > 0 ? 'true' : 'false'}>
                    <span
                      className={cn(
                        't-badge-dot',
                        'min-w-[18px] h-[18px] px-1',
                        'flex items-center justify-center',
                        'bg-red-500 text-white text-[10px] font-bold',
                        'rounded-full',
                      )}
                    >
                      {unreadCount > 99 ? '99+' : unreadCount}
                    </span>
                  </span>
                </div>
              </button>

              {/* Collapse sits beside the bell and stays visible. Revealing it
                  on hover meant it could not be found without already knowing
                  it was there. */}
              {isDesktop && (
                <button
                  onClick={handleToggleExpand}
                  className={cn(
                    'flex items-center justify-center p-2 rounded-element transition-colors',
                    'text-text-tertiary hover:bg-bg-tertiary hover:text-text-primary',
                  )}
                  title={isExpanded ? 'Collapse sidebar' : 'Expand sidebar'}
                  aria-label={isExpanded ? 'Collapse sidebar' : 'Expand sidebar'}
                >
                  <span className="t-icon-swap" data-state={isExpanded ? 'a' : 'b'}>
                    <span className="t-icon" data-icon="a">
                      <PanelLeftClose className="w-5 h-5" />
                    </span>
                    <span className="t-icon" data-icon="b">
                      <PanelLeft className="w-5 h-5" />
                    </span>
                  </span>
                </button>
              )}

              {/* Mobile close button */}
              {!isDesktop && (
                <button
                  onClick={onClose}
                  className="p-2 rounded-element hover:bg-bg-tertiary transition-colors"
                  aria-label="Close menu"
                >
                  <X className="w-5 h-5 text-text-secondary" />
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Scrollable middle section */}
        <div className="flex-1 min-h-0 overflow-x-hidden overflow-y-auto">
          <nav className="space-y-1 px-2 py-2">
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
                  title={!showText ? item.label : undefined}
                  className={cn(
                    // One layout for both states. Swapping between a centred
                    // icon and an icon-plus-label row makes the icon jump at
                    // the moment the width starts moving; holding the row
                    // still and letting the label fade out under the clip is
                    // what makes the collapse read as one motion.
                    'relative flex items-center gap-3 rounded-chip px-[18px] py-3',
                    'transition-colors duration-150',
                    isActive
                      ? 'text-bg-primary'
                      : 'text-text-secondary hover:bg-bg-tertiary hover:text-text-primary',
                  )}
                >
                  {/* One shared pill for the whole nav: framer-motion matches it
                      across rows by layoutId, so selecting a page slides the
                      fill rather than cross-fading two of them. */}
                  {isActive && (
                    <motion.span
                      layoutId="sidebar-active-pill"
                      transition={{ type: 'spring', stiffness: 520, damping: 42 }}
                      className="absolute inset-0 rounded-chip bg-text-primary"
                    />
                  )}
                  <span className="flex-shrink-0 relative z-10">{item.icon}</span>
                  <span
                    className={cn(
                      'relative z-10 whitespace-nowrap font-medium',
                      'transition-opacity duration-150',
                      showText ? 'opacity-100 delay-75' : 'opacity-0',
                    )}
                  >
                    {item.label}
                  </span>
                </Link>
              );
            })}
          </nav>
        </div>

        {/* Platform-aware app download banner */}
        <AnimatePresence>
          {!mobileAppDismissed &&
            (() => {
              const isMac =
                typeof navigator !== 'undefined' && /Mac/.test(navigator.userAgent);
              const bannerHref = isMac
                ? 'https://macos.omi.me/'
                : 'https://onelink.to/rbsrxc';
              const bannerTitle = isMac
                ? 'Omi is 10X better on macOS'
                : 'Take Omi with you';
              const bannerSubtitle = isMac ? 'Try Omi on macOS' : 'Try Omi on your phone';
              return (
                <motion.div
                  // Dismissing is the one moment this banner is the thing you are
                  // looking at, so it swells, bursts and pops out of existence
                  // rather than blinking out.
                  initial={false}
                  animate={
                    bannerBursting
                      ? shouldReduceMotion
                        ? { opacity: 0 }
                        : {
                            transform: ['scale(1)', 'scale(1.06)', 'scale(0.96)'],
                            opacity: [1, 1, 0],
                          }
                      : { transform: 'scale(1)', opacity: 1 }
                  }
                  exit={
                    shouldReduceMotion
                      ? { opacity: 0 }
                      : { transform: 'scale(0.96)', opacity: 0 }
                  }
                  transition={
                    bannerBursting
                      ? {
                          duration: shouldReduceMotion ? 0.15 : BANNER_BURST_MS / 1000,
                          times: [0, 0.35, 1],
                          ease: [0.23, 1, 0.32, 1],
                        }
                      : { type: 'spring', stiffness: 520, damping: 26 }
                  }
                  className={cn('relative px-3 pt-2 pb-2', !showText && 'px-2')}
                >
                  {bannerBursting && <ConfettiBurst />}
                  <div className="relative">
                    <a
                      href={bannerHref}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={cn(
                        'relative flex items-center gap-3 rounded-xl bg-bg-tertiary/50 transition-colors hover:bg-bg-tertiary',
                        showText ? 'p-3 pr-9' : 'justify-center p-3',
                      )}
                    >
                      <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-white/[0.08]">
                        {isMac ? (
                          <AppleLogo className="w-4 h-4 text-text-tertiary" />
                        ) : (
                          <Smartphone className="w-4 h-4 text-text-tertiary" />
                        )}
                      </div>
                      {showText && (
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-text-primary">
                            {bannerTitle}
                          </p>
                          <p className="text-xs text-text-quaternary">{bannerSubtitle}</p>
                        </div>
                      )}
                    </a>
                    {showText && (
                      <button
                        onClick={handleDismissMobileApp}
                        className="absolute right-2 top-1/2 -translate-y-1/2 rounded-full p-1 text-text-quaternary transition-colors hover:bg-white/[0.08] hover:text-text-tertiary"
                        aria-label="Dismiss"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                </motion.div>
              );
            })()}
        </AnimatePresence>

        {/* Footer: the profile at rest and the whole menu when open.

            Expanded, the menu grows upward inside the same surface, so the row
            you clicked stays put and becomes the base of what opened — no
            second copy of your name and avatar. Collapsed there is no surface
            to grow, so it opens beside the rail instead of forcing the rail
            open: widening the whole sidebar to show a menu moves every other
            thing on screen to answer a question about one of them. */}
        <div
          ref={userMenuRef}
          className={cn(
            // flex-shrink-0: the rail is a flex column whose nav takes the
            // slack, so without this the footer is the item that gives way and
            // the opened menu is silently squeezed back to the profile row.
            'relative flex-shrink-0',
            showText ? 'm-3' : 'mx-2 mb-3 mt-3',
            // Collapsed, the avatar is the whole control and stands on the raw
            // window; the card would be chrome drawn around a single circle.
            showText && 'overflow-hidden rounded-card border border-stroke bg-bg-raised',
          )}
        >
          {/* Opened by max-height, not by height:auto and not by a 0fr->1fr grid
              track. Animating to auto needs a measured target and the measure
              never ran through this runtime; the grid track collapses because
              `overflow-hidden` sets the item's automatic minimum size to zero,
              so `1fr` resolves against zero free space. A max-height ceiling
              needs neither, and the menu is a fixed set of rows so a ceiling is
              safe — it is checked by a test rather than left to drift. */}
          {showText && (
            <div
              className={cn(
                'overflow-hidden',
                'transition-[max-height,opacity] duration-300',
                // Overshooting ease: the panel arrives slightly past its mark
                // and settles, which reads as the surface lifting rather than
                // as a box being resized.
                '[transition-timing-function:cubic-bezier(0.34,1.4,0.5,1)]',
                menuOpen ? 'opacity-100' : 'opacity-0 duration-200',
              )}
              style={{ maxHeight: menuOpen ? PROFILE_MENU_MAX_HEIGHT : 0 }}
              aria-hidden={!menuOpen}
            >
              <div
                inert={!menuOpen}
                className={cn(
                  'transition-transform duration-300',
                  '[transition-timing-function:cubic-bezier(0.34,1.4,0.5,1)]',
                  // Held down a little while closed so the rows slide up out of
                  // the profile row rather than appearing already in place.
                  menuOpen ? 'translate-y-0' : 'translate-y-3',
                )}
              >
                <ProfileMenuRows onNavigate={closeUserMenu} onSignOut={handleSignOut} />
              </div>
            </div>
          )}

          <button
            onClick={() => setShowUserMenu(!showUserMenu)}
            className={cn(
              'flex w-full items-center gap-3 overflow-hidden transition-colors',
              showText ? 'p-3' : 'h-12 justify-center p-0',
              showText && 'hover:bg-bg-tertiary/60',
            )}
            title={!showText ? 'Settings' : undefined}
          >
            {/* Avatar */}
            <div
              className={cn(
                'h-9 w-9 flex-shrink-0 overflow-hidden rounded-full',
                showText && 'bg-bg-tertiary ring-2 ring-bg-tertiary',
              )}
            >
              {user?.photoURL ? (
                <Image
                  src={user.photoURL}
                  alt={user.displayName || 'User'}
                  width={36}
                  height={36}
                  className="object-cover"
                />
              ) : (
                <div className="flex h-full w-full items-center justify-center text-sm font-medium text-text-tertiary">
                  {user?.displayName?.charAt(0) || 'U'}
                </div>
              )}
            </div>

            <div
              className={cn(
                'flex min-w-0 flex-1 items-center gap-3',
                'transition-opacity duration-150',
                showText ? 'opacity-100 delay-75' : 'opacity-0',
              )}
              aria-hidden={!showText}
            >
              <>
                {/* Name & email */}
                <div className="flex-1 min-w-0 text-left">
                  <p className="truncate whitespace-nowrap text-sm font-medium text-text-primary">
                    {user?.displayName || 'User'}
                  </p>
                  <p className="truncate whitespace-nowrap text-xs text-text-quaternary">
                    {user?.email}
                  </p>
                </div>

                {/* Dropdown indicator */}
                <svg
                  className={cn(
                    'h-4 w-4 flex-shrink-0 text-text-quaternary transition-transform',
                    showUserMenu && 'rotate-180',
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
            </div>
          </button>

          {/* Collapsed: the menu is a popover beside the rail. */}
          {!showText && (
            <OpenSurface
              open={menuOpen}
              data-origin="bottom-left"
              className={cn(
                't-dropdown',
                'absolute bottom-0 left-full z-[60] ml-2 w-64 origin-bottom-left',
                'overflow-hidden rounded-card border border-stroke bg-bg-raised',
                'shadow-[0_18px_40px_-12px_rgba(0,0,0,0.6)]',
              )}
            >
              <ProfileMenuRows onNavigate={closeUserMenu} onSignOut={handleSignOut} />
            </OpenSurface>
          )}
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
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-white/40',
      )}
    >
      <Menu className="w-6 h-6 text-text-secondary" />
    </button>
  );
}
