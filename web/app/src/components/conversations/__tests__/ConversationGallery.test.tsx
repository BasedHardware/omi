import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ConversationGallery } from '@/components/conversations/ConversationGallery';
import type { TimelineDayGroup } from '@/lib/conversationTimeline';
import type { Conversation } from '@/types/conversation';

function conversation(id: string): Conversation {
  return {
    id,
    created_at: '2026-01-01T00:00:00Z',
    started_at: '2026-01-01T00:00:00Z',
    structured: { title: id, overview: '', emoji: '', category: 'other' },
  } as unknown as Conversation;
}

function groupsOf(ids: string[]): TimelineDayGroup[] {
  return [
    {
      key: '2026-01-01',
      label: 'Today',
      dayStart: 0,
      items: ids.map((id) => ({
        kind: 'conversation' as const,
        id,
        sortTime: 0,
        conversation: conversation(id),
      })),
    },
  ];
}

/** Puts the scroller inside the load-more threshold and fires one scroll. */
function scrollToBottom(scroller: HTMLElement) {
  Object.defineProperty(scroller, 'scrollHeight', { value: 1000, configurable: true });
  Object.defineProperty(scroller, 'clientHeight', { value: 500, configurable: true });
  Object.defineProperty(scroller, 'scrollTop', { value: 500, configurable: true });
  fireEvent.scroll(scroller);
}

/** The gallery's own scroll container is its root element. */
function scroller(container: HTMLElement): HTMLElement {
  return container.firstElementChild as HTMLElement;
}

describe('ConversationGallery responsive layout', () => {
  it('uses the gallery width to collapse tiles without clipping them', () => {
    render(
      <ConversationGallery
        groups={groupsOf(['a', 'b'])}
        selectedId={null}
        onConversationClick={vi.fn()}
        onRecapClick={vi.fn()}
      />,
    );

    expect(screen.getByTestId('conversation-gallery-grid')).toHaveStyle({
      gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 16rem), 1fr))',
    });
  });

  it('fades the scroll edge into the page background', () => {
    render(
      <ConversationGallery
        groups={groupsOf(['a'])}
        selectedId={null}
        onConversationClick={vi.fn()}
        onRecapClick={vi.fn()}
      />,
    );

    const galleryScroller = screen.getByTestId('conversation-gallery-scroller');
    expect(galleryScroller).toHaveStyle({
      maskImage:
        'linear-gradient(to bottom, black 0, black calc(100% - 8rem), transparent 100%)',
    });
    expect(galleryScroller).toHaveClass('pb-32');
  });
});

describe('ConversationGallery infinite scroll', () => {
  it('requests the next page when the viewport reaches the bottom', () => {
    const onLoadMore = vi.fn();
    const { container } = render(
      <ConversationGallery
        groups={groupsOf(['a'])}
        selectedId={null}
        onConversationClick={vi.fn()}
        onRecapClick={vi.fn()}
        hasMore
        loading={false}
        onLoadMore={onLoadMore}
      />,
    );

    scrollToBottom(scroller(container));
    expect(onLoadMore).toHaveBeenCalledTimes(1);

    // One gesture must not fire a burst of pages.
    scrollToBottom(scroller(container));
    expect(onLoadMore).toHaveBeenCalledTimes(1);
  });

  // The bug: the guard was only cleared by scrolling away from the bottom, so
  // a page that failed — or came back too short to move the scroller — left
  // the guard armed forever and the rest of the list unreachable.
  it('retries after a failed page while the viewport stays at the bottom', () => {
    const onLoadMore = vi.fn();
    const props = {
      groups: groupsOf(['a']),
      selectedId: null,
      onConversationClick: vi.fn(),
      onRecapClick: vi.fn(),
      hasMore: true,
      onLoadMore,
    };

    const { container, rerender } = render(
      <ConversationGallery {...props} loading={false} />,
    );

    scrollToBottom(scroller(container));
    expect(onLoadMore).toHaveBeenCalledTimes(1);

    // The page is in flight, then fails: loading settles back to false and the
    // item count is unchanged.
    rerender(<ConversationGallery {...props} loading />);
    rerender(<ConversationGallery {...props} loading={false} />);

    scrollToBottom(scroller(container));
    expect(onLoadMore).toHaveBeenCalledTimes(2);
  });
});
