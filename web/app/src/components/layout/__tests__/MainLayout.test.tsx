import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

// The shell (sidebar, bottom bar, providers) is one instance across routes.
// Navigating swaps only the page subtree; if a regression keys the shell by
// pathname again, every route change remounts the whole thing — the "page
// reload" feel this suite guards against.

let pathname = '/home';

vi.mock('@tschk/moonshine-next/navigation', () => ({
  usePathname: () => pathname,
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@tschk/moonshine-next/dynamic', () => ({
  default: () => () => null,
}));
vi.mock('@tschk/moonshine-next/image', () => ({
  default: () => null,
}));

let sidebarMounts = 0;
let bottomBarMounts = 0;

vi.mock('@/components/layout/Sidebar', () => ({
  Sidebar: () => {
    // Effects run once per mount; re-renders don't re-run them.
    const { useEffect } = require('react');
    useEffect(() => {
      sidebarMounts += 1;
    }, []);
    return <div data-testid="sidebar" />;
  },
}));
vi.mock('@/components/layout/BottomNavigation', () => ({
  BottomNavigation: () => {
    const { useEffect } = require('react');
    useEffect(() => {
      bottomBarMounts += 1;
    }, []);
    return <div data-testid="bottom-bar" />;
  },
}));

vi.mock('@/components/chat/ChatContext', () => ({
  ChatProvider: ({ children }: { children: React.ReactNode }) => children,
  useChat: () => ({ openChatWithApp: vi.fn() }),
}));
vi.mock('@/components/notifications/NotificationContext', () => ({
  NotificationProvider: ({ children }: { children: React.ReactNode }) => children,
  useNotificationContext: () => ({ openNotificationCenter: vi.fn() }),
}));
vi.mock('@/components/recording', () => ({
  HeaderRecordingIndicator: () => null,
}));
vi.mock('@/components/memories/MemoriesPrefetcher', () => ({
  MemoriesPrefetcher: () => null,
}));
vi.mock('@/components/chat/ChatBubble', () => ({
  ChatBubble: () => null,
}));
vi.mock('@/lib/api', () => ({
  getChatApps: vi.fn().mockResolvedValue([]),
}));

import { MainLayout } from '@/components/layout/MainLayout';

describe('MainLayout shell persistence', () => {
  it('does not remount the shell when the route changes', () => {
    const { rerender } = render(
      <MainLayout hideHeader>
        <div>home page</div>
      </MainLayout>,
    );

    expect(sidebarMounts).toBe(1);
    expect(bottomBarMounts).toBe(1);

    pathname = '/record';
    rerender(
      <MainLayout hideHeader>
        <div>record page</div>
      </MainLayout>,
    );

    // A pathname-keyed shell remounts here; the reconciled shell must not.
    expect(sidebarMounts).toBe(1);
    expect(bottomBarMounts).toBe(1);
  });
});
