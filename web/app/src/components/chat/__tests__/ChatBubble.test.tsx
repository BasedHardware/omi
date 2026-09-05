import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const state = vi.hoisted(() => ({
  isOpen: false,
  unreadCount: 2,
  reduceMotion: false,
  toggleChat: vi.fn(),
  toggleNotificationCenter: vi.fn(),
}));

vi.mock('liquid-gooey', () => {
  function Item({
    children,
    x,
    y,
  }: {
    children: React.ReactNode;
    x?: number;
    y?: number;
  }) {
    return (
      <div data-testid="liquid-item" data-x={x ?? 0} data-y={y ?? 0}>
        {children}
      </div>
    );
  }
  function Liquid({ children }: { children: React.ReactNode }) {
    return <div data-testid="liquid">{children}</div>;
  }
  Liquid.Item = Item;
  return { Liquid };
});

vi.mock('framer-motion', async (importOriginal) => ({
  ...(await importOriginal<typeof import('framer-motion')>()),
  useReducedMotion: () => state.reduceMotion,
}));

vi.mock('@/components/chat/ChatContext', () => ({
  useChat: () => ({
    isOpen: state.isOpen,
    toggleChat: state.toggleChat,
  }),
}));

vi.mock('@/components/notifications/NotificationContext', () => ({
  useNotificationContext: () => ({
    toggleNotificationCenter: state.toggleNotificationCenter,
    unreadCount: state.unreadCount,
  }),
}));

import { ChatBubble } from '@/components/chat/ChatBubble';

describe('ChatBubble', () => {
  beforeEach(() => {
    state.isOpen = false;
    state.unreadCount = 2;
    state.reduceMotion = false;
    state.toggleChat.mockClear();
    state.toggleNotificationCenter.mockClear();
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
        onchange: null,
      })),
    });
  });

  it('fans the notifications control out of the chat FAB', () => {
    const { container } = render(<ChatBubble />);
    expect(screen.getByRole('button', { name: 'Open chat' })).toBeInTheDocument();
    expect(container.querySelector('[data-testid="liquid"]')).not.toBeNull();

    const items = screen.getAllByTestId('liquid-item');
    expect(items[0]).toHaveAttribute('data-y', '0');
    expect(screen.queryByRole('button', { name: 'Notifications' })).toBeNull();

    fireEvent.mouseEnter(container.firstChild as HTMLElement);
    expect(screen.getAllByTestId('liquid-item')[0]).toHaveAttribute('data-y', '-72');
    expect(screen.getByRole('button', { name: 'Notifications' })).toBeInTheDocument();
    expect(container.querySelector('.t-badge')).toHaveAttribute('data-open', 'true');
  });

  it('blurs the notifications control when the fan collapses', () => {
    const { container } = render(<ChatBubble />);
    fireEvent.mouseEnter(container.firstChild as HTMLElement);
    const notify = screen.getByRole('button', { name: 'Notifications' });
    notify.focus();
    expect(document.activeElement).toBe(notify);

    fireEvent.mouseLeave(container.firstChild as HTMLElement);
    expect(document.activeElement).not.toBe(notify);
  });

  it('skips the gooey fan when reduced motion is requested', () => {
    state.reduceMotion = true;
    render(<ChatBubble />);
    expect(screen.queryByTestId('liquid')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Open chat' }));
    expect(state.toggleChat).toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Notifications' }));
    expect(state.toggleNotificationCenter).toHaveBeenCalled();
  });
});
