'use client';

import { useState, useCallback } from 'react';
import { Sidebar, MobileMenuButton } from './Sidebar';
import { ChatProvider } from '@/components/chat/ChatContext';
import { ChatBubble } from '@/components/chat/ChatBubble';
import { ChatPanel } from '@/components/chat/ChatPanel';
import { RecordingProvider } from '@/components/recording/RecordingContext';
import { RecordingController } from '@/components/recording/RecordingController';
import { RecordingWidget } from '@/components/recording/RecordingWidget';
import { useLocalStorage } from '@/hooks/useLocalStorage';
import { cn } from '@/lib/utils';

interface MainLayoutProps {
  children: React.ReactNode;
  title?: string;
  /** Hide header for full-height layouts like split view */
  hideHeader?: boolean;
}

export function MainLayout({ children, title, hideHeader = false }: MainLayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [isPinned, setIsPinned] = useLocalStorage('sidebar-pinned', false);
  const [isHovered, setIsHovered] = useState(false);

  const handleTogglePin = useCallback(() => {
    setIsPinned((prev) => !prev);
  }, [setIsPinned]);

  const handleHoverChange = useCallback((hovered: boolean) => {
    setIsHovered(hovered);
  }, []);

  // Sidebar is expanded if pinned OR hovered
  const isExpanded = isPinned || isHovered;

  return (
    <RecordingProvider>
      <ChatProvider>
        <div className="h-screen bg-bg-primary flex overflow-hidden">
          {/* Recording controller - initializes recording hooks */}
          <RecordingController />

          {/* Sidebar */}
          <Sidebar
            isOpen={sidebarOpen}
            onClose={() => setSidebarOpen(false)}
            isExpanded={isExpanded}
            isPinned={isPinned}
            onTogglePin={handleTogglePin}
            onHoverChange={handleHoverChange}
          />

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

          {/* Chat bubble + panel */}
          <ChatBubble />
          <ChatPanel />

          {/* Recording widget */}
          <RecordingWidget />
        </div>
      </ChatProvider>
    </RecordingProvider>
  );
}
