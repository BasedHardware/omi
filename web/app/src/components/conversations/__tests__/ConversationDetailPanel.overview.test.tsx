import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { SummaryTab } from '@/components/conversations/ConversationDetailPanel';

vi.mock('@tschk/moonshine-next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));
vi.mock('@tschk/moonshine-next/dynamic', () => ({
  default: () => () => <div data-testid="map" />,
}));
vi.mock('@/hooks/usePeople', () => ({
  usePeople: () => ({ people: [] }),
}));
vi.mock('@/hooks/useScreenFrames', () => ({
  useScreenFrames: () => ({
    frameSet: null,
    loading: false,
    error: null,
    refresh: vi.fn(),
    deleteFrame: vi.fn(),
    deleteAll: vi.fn(),
    setSharingEnabled: vi.fn(),
  }),
}));
vi.mock('@/lib/analytics/mixpanel', () => ({
  MixpanelManager: { track: vi.fn() },
}));
vi.mock('@/lib/api', () => ({
  precacheConversationAudio: vi.fn(),
  getConversationAudioUrls: vi.fn(),
  updateSegmentText: vi.fn(),
  reprocessConversation: vi.fn(),
}));
vi.mock('framer-motion', () => ({
  AnimatePresence: ({ children }: { children: React.ReactNode }) => children,
  motion: {
    div: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  },
}));
vi.mock('@/components/conversations/GenerateSummaryButton', () => ({
  GenerateSummaryButton: () => null,
}));
vi.mock('@/components/conversations/AppSummaryCard', () => ({
  AppSummaryCard: () => null,
}));

const NOTES_V2_OVERVIEW = `## Key points

- Ship the notes render
- Keep action items
`;

describe('SummaryTab overview markdown', () => {
  it('renders a heading and a bullet list as elements, not literal text', () => {
    render(
      <SummaryTab
        overview={NOTES_V2_OVERVIEW}
        conversationId="conv-1"
        appResults={[]}
        suggestedAppIds={[]}
      />,
    );

    expect(screen.getByRole('heading', { name: 'Key points' })).toBeInTheDocument();
    expect(screen.getByRole('list')).toBeInTheDocument();
    const items = screen.getAllByRole('listitem');
    expect(items.map((item) => item.textContent)).toEqual([
      'Ship the notes render',
      'Keep action items',
    ]);
    expect(screen.queryByText(/## Key points/)).not.toBeInTheDocument();
  });

  it('renders the same markdown elements beside a location map', () => {
    render(
      <SummaryTab
        overview={NOTES_V2_OVERVIEW}
        conversationId="conv-1"
        appResults={[]}
        suggestedAppIds={[]}
        geolocation={{ latitude: 37.77, longitude: -122.42, address: 'San Francisco' }}
      />,
    );

    expect(screen.getByRole('heading', { name: 'Key points' })).toBeInTheDocument();
    expect(screen.getByRole('list')).toBeInTheDocument();
    expect(screen.getByTestId('map')).toBeInTheDocument();
    expect(screen.queryByText(/## Key points/)).not.toBeInTheDocument();
  });
});
