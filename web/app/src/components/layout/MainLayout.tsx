'use client';

import { useState, useEffect } from 'react';
import { usePathname, useSearchParams } from '@tschk/moonshine-next/navigation';
import dynamic from '@tschk/moonshine-next/dynamic';
import Image from '@tschk/moonshine-next/image';
import { Sidebar } from './Sidebar';
import { ChatProvider, useChat as useChatContext } from '@/components/chat/ChatContext';
import { BottomNavigation } from './BottomNavigation';
import {
  NotificationProvider,
  useNotificationContext,
} from '@/components/notifications/NotificationContext';
import { HeaderRecordingIndicator } from '@/components/recording';
import { getChatApps } from '@/lib/api';
import { cn } from '@/lib/utils';
import { MemoriesPrefetcher } from '@/components/memories/MemoriesPrefetcher';
import { ChatBubble } from '@/components/chat/ChatBubble';

// Dynamic imports for panels - not visible on initial load
const ChatPanel = dynamic(
  () => import('@/components/chat/ChatPanel').then((mod) => ({ default: mod.ChatPanel })),
  {
    ssr: false,
  },
);

const NotificationCenter = dynamic(
  () =>
    import('@/components/notifications/NotificationCenter').then((mod) => ({
      default: mod.NotificationCenter,
    })),
  {
    ssr: false,
  },
);

/**
 * Handles routing from notification clicks to the appropriate panel.
 * When a notification with /chat/{app_id} is clicked:
 * - If app has 'chat' capability: open ChatPanel with that app
 * - If app only has 'notification' capability: open NotificationCenter
 */
function ChatAppRouter() {
  const searchParams = useSearchParams();
  const { openChatWithApp } = useChatContext();
  const { openNotificationCenter } = useNotificationContext();

  useEffect(() => {
    const chatAppId = searchParams.get('chatApp');
    if (!chatAppId) return;

    // Route based on app capability
    async function routeToApp() {
      try {
        // Get apps with chat capability
        const chatApps = await getChatApps();
        const hasChatCapability = chatApps.some((app) => app.id === chatAppId);

        if (hasChatCapability) {
          // App supports chat - open chat panel with this app
          openChatWithApp(chatAppId!);
        } else {
          // App is notification-only (like Bitcoin) - open notification center
          openNotificationCenter();
        }
      } catch (error) {
        console.error('Failed to route chat app notification:', error);
        // Fallback to notification center on error
        openNotificationCenter();
      }

      // Clean up URL - remove the chatApp param
      const url = new URL(window.location.href);
      url.searchParams.delete('chatApp');
      window.history.replaceState({}, '', url.pathname + url.search);
    }

    routeToApp();
  }, [searchParams, openChatWithApp, openNotificationCenter]);

  return null;
}

interface MainLayoutProps {
  children: React.ReactNode;
  title?: string;
  /** Hide header for full-height layouts like split view */
  hideHeader?: boolean;
}

export function MainLayout({ children, title, hideHeader = false }: MainLayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const pathname = usePathname();

  return (
    <ChatProvider>
      <NotificationProvider>
        {/* Handle notification routing from chatApp query param */}
        <ChatAppRouter />
        {/* Prefetch memories in background for instant page load */}
        <MemoriesPrefetcher />
        <div className="flex h-screen w-screen overflow-hidden bg-bg-primary">
          {/* Sidebar */}
          <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />

          {/* Main content area - flex row to support push/slide panels */}
          <div className="flex h-full min-w-0 flex-1 overflow-hidden">
            {/* Main content */}
            <main className="flex h-full min-w-0 flex-1 flex-col overflow-hidden pb-[76px] lg:pb-0">
              {/* Header - conditionally shown */}
              {!hideHeader && (
                <header
                  className={cn(
                    'flex-shrink-0',
                    'flex items-center gap-3 px-4 py-3.5 lg:gap-4 lg:px-8 lg:py-4',
                    'bg-bg-primary/80 backdrop-blur-md',
                    'border-b border-bg-tertiary',
                  )}
                >
                  {/* No burger here on purpose: on mobile the bottom bar's
                      Profile button is the single entry point to the sidebar,
                      so navigation has one source of truth per surface. */}

                  {/* Logo on mobile */}
                  <Image
                    src="/omi-white.webp"
                    alt="Omi"
                    width={48}
                    height={19}
                    className="object-contain lg:hidden"
                  />

                  {title && (
                    <h1 className="truncate font-display text-xl font-semibold text-text-primary">
                      {title}
                    </h1>
                  )}
                </header>
              )}

              {/* Content pane. Desktop insets the pane from the window edge by
                  OmiSpacing.md (12) and rounds it to OmiChrome.windowRadius
                  (26), so the shell reads as a card floating over the window
                  rather than a full-bleed page. */}
              <div className="min-h-0 flex-1 p-0 sm:p-3">
                <div
                  className={cn(
                    'h-full w-full overflow-hidden',
                    'bg-bg-pane sm:rounded-window sm:border sm:border-stroke/[0.22]',
                    'sm:shadow-[0_14px_26px_rgba(0,0,0,0.22)]',
                  )}
                >
                  {/* Deliberately NOT keyed by pathname and NOT animated:
                      keying remounts the whole shell on every navigation,
                      which reads as a page refresh and resets scroll and
                      in-progress state. React reconciles the swapped route
                      subtree in place instead. No AnimatePresence wrapper for
                      the same reason — navigating should not replay an enter
                      animation. */}
                  <div className="h-full">{children}</div>
                </div>
              </div>
            </main>

            {/* Chat panel - push/slide from right */}
            <ChatPanel />

            {/* Notification center - push/slide from right */}
            <NotificationCenter />
            {pathname !== '/home' && <ChatBubble />}
          </div>

          {/* Bottom navigation - mobile only */}
          <BottomNavigation onOpenMenu={() => setSidebarOpen(true)} />

          {/* Recording indicator - handles its own fixed positioning and animates with panels */}
          <HeaderRecordingIndicator />
        </div>
      </NotificationProvider>
    </ChatProvider>
  );
}
