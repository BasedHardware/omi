import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const state = vi.hoisted(() => ({
  isOpen: false,
  unreadCount: 2,
  reduceMotion: false,
  coarse: false,
  toggleChat: vi.fn(),
  toggleNotificationCenter: vi.fn(),
}));

vi.mock('liquid-gooey', () => {
  function Item({
    children,
    x,
    y,
    scale,
  }: {
    children: React.ReactNode;
    x?: number;
    y?: number;
    scale?: number;
  }) {
    return (
      <div
        data-testid="liquid-item"
        data-x={x ?? 0}
        data-y={y ?? 0}
        data-scale={scale ?? 1}
      >
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
    state.coarse = false;
    state.toggleChat.mockClear();
    state.toggleNotificationCenter.mockClear();
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: query.includes('pointer: coarse') ? state.coarse : false,
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
    expect(screen.getAllByTestId('liquid-item')[0]).toHaveAttribute('data-y', '-16');
    expect(screen.getByRole('button', { name: 'Notifications' })).toBeInTheDocument();
    expect(container.querySelector('.t-badge')).toHaveAttribute('data-open', 'true');
  });

  it('scales the collapsed notifications slot away instead of leaving a blank circle', () => {
    // The gooey layer paints one white blob per item, and it paints that blob
    // for an item that is only transparent — which left an empty white circle
    // stacked on the chat button. The collapsed item is scaled to nothing so
    // its blob goes with it, while both items stay mounted and keep the column
    // (and the chat button's corner) in place.
    const { container } = render(<ChatBubble />);

    const [notifySlot, chatSlot] = screen.getAllByTestId('liquid-item');
    expect(notifySlot).toHaveAttribute('data-scale', '0');
    expect(chatSlot).toHaveAttribute('data-scale', '1');

    const bell = container.querySelector('button[aria-label="Notifications"]');
    expect(bell).toHaveAttribute('aria-hidden', 'true');
    expect(bell).toHaveAttribute('tabindex', '-1');
    expect(bell?.className).toContain('pointer-events-none');

    fireEvent.mouseEnter(container.firstChild as HTMLElement);
    expect(screen.getAllByTestId('liquid-item')[0]).toHaveAttribute('data-scale', '1');
    expect(bell).toHaveAttribute('aria-hidden', 'false');
  });

  it('keeps one circle on a touch screen with nothing unread', () => {
    state.coarse = true;
    state.unreadCount = 0;

    render(<ChatBubble />);

    expect(screen.getByRole('button', { name: 'Open chat' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Notifications' })).toBeNull();
  });

  it('offers the notifications control on a touch screen with something unread', () => {
    state.coarse = true;
    state.unreadCount = 3;

    render(<ChatBubble />);

    expect(screen.getByRole('button', { name: 'Notifications' })).toBeInTheDocument();
  });

  it('hands focus to the chat control when the fan collapses under the pointer', () => {
    const { container } = render(<ChatBubble />);
    fireEvent.mouseEnter(container.firstChild as HTMLElement);
    const notify = screen.getByRole('button', { name: 'Notifications' });
    notify.focus();
    expect(document.activeElement).toBe(notify);

    fireEvent.mouseLeave(container.firstChild as HTMLElement);

    expect(document.activeElement).toBe(
      screen.getByRole('button', { name: 'Open chat' }),
    );
  });

  it('skips the gooey fan when reduced motion is requested', () => {
    state.reduceMotion = true;
    const { container } = render(<ChatBubble />);
    expect(screen.queryByTestId('liquid')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Notifications' })).toBeNull();

    fireEvent.mouseEnter(container.firstChild as HTMLElement);
    fireEvent.click(screen.getByRole('button', { name: 'Open chat' }));
    expect(state.toggleChat).toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Notifications' }));
    expect(state.toggleNotificationCenter).toHaveBeenCalled();
  });
});
