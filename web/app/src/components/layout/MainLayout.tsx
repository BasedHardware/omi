'use client';

import { useState, useEffect } from 'react';
import { usePathname, useSearchParams } from '@tschk/moonshine-next/navigation';
import { motion } from 'framer-motion';
import dynamic from '@tschk/moonshine-next/dynamic';
import { Sidebar, MobileMenuButton } from './Sidebar';
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
        <div className="h-screen w-screen bg-bg-primary flex overflow-hidden">
          {/* Sidebar */}
          <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />

          {/* Main content area - flex row to support push/slide panels */}
          <div className="flex-1 flex min-w-0 h-full overflow-hidden">
            {/* Main content */}
            <main className="flex-1 flex flex-col min-w-0 h-full overflow-hidden pb-16 lg:pb-0">
              {/* Header - conditionally shown */}
              {!hideHeader && (
                <header
                  className={cn(
                    'flex-shrink-0',
                    'flex items-center gap-4 px-4 py-4 lg:px-8',
                    'bg-bg-primary/80 backdrop-blur-md',
                    'border-b border-bg-tertiary',
                  )}
                >
                  <MobileMenuButton onClick={() => setSidebarOpen(true)} />

                  {title && (
                    <h1 className="text-xl font-display font-semibold text-text-primary">
                      {title}
                    </h1>
                  )}
                </header>
              )}

              {/* Mobile menu button when header is hidden */}
              {hideHeader && (
                <div className="lg:hidden absolute top-4 left-4 z-30">
                  <MobileMenuButton onClick={() => setSidebarOpen(true)} />
                </div>
              )}

              {/* Content pane. Desktop insets the pane from the window edge by
                  OmiSpacing.md (12) and rounds it to OmiChrome.windowRadius
                  (26), so the shell reads as a card floating over the window
                  rather than a full-bleed page. */}
              <div className="flex-1 min-h-0 p-0 sm:p-3">
                <div
                  className={cn(
                    'h-full w-full overflow-hidden',
                    'bg-bg-pane sm:rounded-window sm:border sm:border-stroke/[0.22]',
                    'sm:shadow-[0_14px_26px_rgba(0,0,0,0.22)]',
                  )}
                >
                  {/* Keyed on the pathname so each destination fades and lifts
                      in.

                      Deliberately not wrapped in `AnimatePresence
                      initial={false}`: every route registers its own copy of
                      this layout, so navigating remounts the whole shell. That
                      makes each navigation look like a first render, and
                      `initial={false}` exists precisely to suppress the enter
                      animation on a first render — so the transition never
                      played on any page. A plain keyed `initial` animates on
                      both a remount and an in-place key change. There is no
                      exit animation for the same reason: the outgoing tree is
                      already gone by the time the new one mounts. */}
                  <motion.div
                    key={pathname}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
                    className="h-full"
                  >
                    {children}
                  </motion.div>
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
          <BottomNavigation onOpenSidebar={() => setSidebarOpen(true)} />

          {/* Recording indicator - handles its own fixed positioning and animates with panels */}
          <HeaderRecordingIndicator />
        </div>
      </NotificationProvider>
    </ChatProvider>
  );
}
