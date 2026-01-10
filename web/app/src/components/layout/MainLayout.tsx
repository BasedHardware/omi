'use client';

import { useState, useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import dynamic from 'next/dynamic';
import { Sidebar, MobileMenuButton } from './Sidebar';
import { ChatProvider, useChat as useChatContext } from '@/components/chat/ChatContext';
import { ChatBubble } from '@/components/chat/ChatBubble';
import { NotificationProvider, useNotificationContext } from '@/components/notifications/NotificationContext';
import { HeaderRecordingIndicator } from '@/components/recording';
import { getChatApps } from '@/lib/api';
import { cn } from '@/lib/utils';

// Dynamic imports for panels - not visible on initial load
const ChatPanel = dynamic(() => import('@/components/chat/ChatPanel').then(mod => ({ default: mod.ChatPanel })), {
  ssr: false,
});

const NotificationCenter = dynamic(() => import('@/components/notifications/NotificationCenter').then(mod => ({ default: mod.NotificationCenter })), {
  ssr: false,
});

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

  return (
    <ChatProvider>
      <NotificationProvider>
        {/* Handle notification routing from chatApp query param */}
        <ChatAppRouter />
        <div className="h-screen bg-bg-primary flex overflow-hidden">
          {/* Sidebar */}
          <Sidebar
            isOpen={sidebarOpen}
            onClose={() => setSidebarOpen(false)}
          />

          {/* Main content area - flex row to support push/slide panels */}
          <div className="flex-1 flex min-w-0 h-full overflow-hidden">
            {/* Main content */}
            <main className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
              {/* Header - conditionally shown */}
              {!hideHeader && (
                <header
                  className={cn(
                    'flex-shrink-0',
                    'flex items-center gap-4 px-4 py-4 lg:px-8',
                    'bg-bg-primary/80 backdrop-blur-md',
                    'border-b border-bg-tertiary'
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

              {/* Content */}
              <div className="flex-1 overflow-hidden">
                {children}
              </div>
            </main>

            {/* Chat panel - push/slide from right */}
            <ChatPanel />

            {/* Notification center - push/slide from right */}
            <NotificationCenter />
          </div>

          {/* Chat bubble - floating button */}
          <ChatBubble />

          {/* Recording indicator - handles its own fixed positioning and animates with panels */}
          <HeaderRecordingIndicator />
        </div>
      </NotificationProvider>
    </ChatProvider>
  );
}
