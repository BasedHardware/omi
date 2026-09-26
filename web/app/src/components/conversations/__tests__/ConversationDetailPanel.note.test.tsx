import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import type {
  AppResponse,
  Conversation,
  Structured,
  TranscriptSegment,
} from '@/types/conversation';

vi.mock('@/lib/utils', () => ({
  cn: (...inputs: Array<string | false | null | undefined>) =>
    inputs.filter(Boolean).join(' '),
  formatDuration: (seconds: number) => `${Math.round(seconds / 60)}m`,
  formatTime: () => '3:00 PM',
}));

vi.mock('@/lib/api', () => ({
  precacheConversationAudio: vi.fn(),
  getConversationAudioUrls: vi.fn(async () => []),
  updateSegmentText: vi.fn(),
  reprocessConversation: vi.fn(),
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
  MixpanelManager: {
    transcriptEdited: vi.fn(),
  },
}));

vi.mock('@tschk/moonshine-next/dynamic', () => ({
  __esModule: true,
  default: () => {
    const MockedComponent = () => <div>mock-map</div>;
    MockedComponent.displayName = 'MockedDynamicComponent';
    return MockedComponent;
  },
}));

vi.mock('../EditableTitle', () => ({
  EditableTitle: ({ title }: { title: string }) => <h1>{title}</h1>,
}));

vi.mock('../ConversationActionsMenu', () => ({
  ConversationActionsMenu: () => <button type="button">actions menu</button>,
}));

vi.mock('../SpeakerTagSheet', () => ({
  SpeakerTagSheet: () => null,
}));

vi.mock('../ManagePeopleModal', () => ({
  ManagePeopleModal: () => null,
}));

vi.mock('../TranscriptView', () => ({
  TranscriptView: () => <div>transcript</div>,
}));

vi.mock('../AudioPlayer', () => ({
  AudioPlayer: () => null,
}));

vi.mock('../ConversationScreenFrameBanner', () => ({
  ConversationScreenFrameBanner: () => <div>screen-frame-banner</div>,
}));

vi.mock('../ConversationScreenFrameCarousel', () => ({
  ConversationScreenFrameCarousel: () => <div>screen-frame-carousel</div>,
}));

vi.mock('../ScreenFrameLightbox', () => ({
  ScreenFrameLightbox: () => null,
}));

vi.mock('../GenerateSummaryButton', () => ({
  GenerateSummaryButton: () => <button type="button">generate summary</button>,
}));

vi.mock('../AppSummaryCard', () => ({
  AppSummaryCard: () => <div>app summary card</div>,
}));

vi.mock('react-markdown', () => ({
  __esModule: true,
  default: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
}));

import { ConversationDetailPanel } from '../ConversationDetailPanel';
import { NoteParticipants } from '../NoteParticipants';
import { ActionItemsTab, NextStepsList } from '../NoteActionItems';
import { renderSummarySections } from '@/lib/conversationSummarySelection';

function baseTranscript(): TranscriptSegment[] {
  return [
    {
      id: 'segment-1',
      text: 'Transcript line',
      speaker: 'SPEAKER_00',
      speaker_id: 0,
      is_user: false,
      start: 0,
      end: 1,
    },
  ];
}

function baseStructured(overrides: Partial<Structured> = {}): Structured {
  return {
    title: 'Weekly sync',
    overview: 'Project updates and next steps.',
    emoji: '💬',
    category: 'work',
    action_items: [],
    events: [],
    ...overrides,
  };
}

function baseConversation(overrides: Partial<Conversation> = {}): Conversation {
  return {
    id: 'conversation-1',
    created_at: '2025-10-01T15:00:00Z',
    started_at: '2025-10-01T15:00:00Z',
    finished_at: '2025-10-01T15:30:00Z',
    source: 'friend',
    language: 'en',
    structured: baseStructured(),
    transcript_segments: baseTranscript(),
    geolocation: null,
    photos: [],
    apps_results: [],
    external_data: null,
    discarded: false,
    visibility: 'private',
    status: 'completed',
    ...overrides,
  };
}

function renderPanel(conversation: Conversation) {
  return render(
    <ConversationDetailPanel
      conversationId={conversation.id}
      conversation={conversation}
      loading={false}
      onBack={vi.fn()}
      onConversationUpdate={vi.fn()}
      onDelete={vi.fn()}
    />,
  );
}

const NOTE_SECTIONS: Structured['sections'] = [
  {
    heading: 'Key takeaways',
    body_markdown: 'Shared context on the rollout.',
    source_segment_ids: ['seg-1'],
  },
  {
    heading: 'Side notes',
    kind: 'side_notes',
    body_markdown: 'Ops handoff notes.',
    source_segment_ids: [],
  },
];

function noteConversation(overrides: Partial<Conversation> = {}): Conversation {
  return baseConversation({
    structured: baseStructured({
      title: 'Quarterly partner sync',
      overview: renderSummarySections(NOTE_SECTIONS),
      sections: NOTE_SECTIONS,
      participants: [
        {
          name: 'Priya Raman',
          email: null,
          organization: null,
          role: 'Product lead',
          is_ai_agent: false,
          source: 'roster',
        },
        {
          name: 'Boardy',
          email: null,
          organization: null,
          role: 'Meeting agent',
          is_ai_agent: true,
          source: 'roster',
        },
      ],
      meeting_type: 'one_on_one',
      insights: [{ text: 'Same blocker as last week', kind: 'prior_meeting' }],
      action_items: [
        {
          description: 'Send the rollout checklist',
          completed: false,
          due_at: null,
          owner_name: 'Marco Ruiz',
          context: 'From the rollout discussion',
        },
      ],
    }),
    apps_results: [],
    ...overrides,
  });
}

describe('ConversationDetailPanel structured note', () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('renders main headings, side notes last, participants and insights', async () => {
    renderPanel(noteConversation());

    const mainHeading = await screen.findByRole('heading', {
      name: 'Key takeaways',
    });
    const sideHeading = screen.getByRole('heading', { name: 'Side notes' });
    expect(
      mainHeading.compareDocumentPosition(sideHeading) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(screen.getByText('Shared context on the rollout.')).toBeTruthy();
    expect(screen.getByText('Ops handoff notes.')).toBeTruthy();
    expect(screen.getByText('For you · only visible to you')).toBeTruthy();
    expect(screen.getByText('Same blocker as last week')).toBeTruthy();
    expect(screen.getByText('Priya Raman')).toBeTruthy();
    expect(screen.getByText('Boardy')).toBeTruthy();
    expect(screen.getByText('AI')).toBeTruthy();
    expect(screen.getByText('One-on-one')).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Next steps' })).toBeTruthy();
    expect(screen.getByText('Marco Ruiz')).toBeTruthy();
    expect(screen.getByText('Send the rollout checklist')).toBeTruthy();
  });

  it('keeps the map when structured note has geolocation', async () => {
    renderPanel(
      noteConversation({
        geolocation: {
          latitude: 40.7128,
          longitude: -74.006,
          address: 'New York, NY',
        },
      }),
    );

    expect(await screen.findByRole('heading', { name: 'Key takeaways' })).toBeTruthy();
    expect(screen.getByText('mock-map')).toBeTruthy();
    expect(screen.getByText('New York, NY')).toBeTruthy();
  });

  it('lets the app summary win selection and never leaks insights', async () => {
    const appResults: AppResponse[] = [
      {
        app_id: 'app-1',
        content: 'Recap generated by the template app',
      },
    ];

    renderPanel(noteConversation({ apps_results: appResults }));

    expect(await screen.findByText('Recap generated by the template app')).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'Key takeaways' })).toBeNull();
    expect(screen.queryByText('For you · only visible to you')).toBeNull();
    expect(screen.queryByText('Same blocker as last week')).toBeNull();
    expect(screen.queryByText('Priya Raman')).toBeNull();
    expect(screen.queryByRole('heading', { name: 'Next steps' })).toBeNull();
  });

  it('keeps overview rendering when the overview does not match the sections', async () => {
    renderPanel(
      baseConversation({
        structured: baseStructured({
          overview: 'Plain overview with sections present',
          sections: [
            {
              heading: 'Key takeaways',
              body_markdown: 'A section body the overview does not mirror.',
            },
          ],
          action_items: [
            {
              description: 'Should stay on the Actions tab only',
              completed: false,
              owner_name: 'Marco Ruiz',
            },
          ],
        }),
      }),
    );

    expect(await screen.findByText('Plain overview with sections present')).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'Key takeaways' })).toBeNull();
    expect(screen.queryByText('For you · only visible to you')).toBeNull();
    expect(screen.queryByRole('heading', { name: 'Next steps' })).toBeNull();
  });

  it('keeps the plain Markdown overview when sections are empty or missing', async () => {
    const { unmount } = renderPanel(
      baseConversation({
        structured: baseStructured({
          overview: 'Overview fallback when sections are empty',
          sections: [],
        }),
      }),
    );

    expect(
      await screen.findByText('Overview fallback when sections are empty'),
    ).toBeTruthy();
    expect(screen.queryByText('For you · only visible to you')).toBeNull();
    expect(screen.queryByRole('list', { name: 'Participants' })).toBeNull();
    unmount();

    renderPanel(
      baseConversation({
        structured: baseStructured({
          overview: 'Overview fallback when sections are missing',
          sections: undefined,
          insights: [{ text: 'Hidden insight', kind: 'goal' }],
          participants: [{ name: 'Hidden Person', source: 'roster' }],
          action_items: [{ description: 'Hidden action', completed: false }],
        }),
      }),
    );

    expect(
      await screen.findByText('Overview fallback when sections are missing'),
    ).toBeTruthy();
    expect(screen.queryByText('Hidden insight')).toBeNull();
    expect(screen.queryByText('Hidden Person')).toBeNull();
    expect(screen.queryByText('For you · only visible to you')).toBeNull();
    expect(screen.queryByRole('heading', { name: 'Next steps' })).toBeNull();
  });
});

describe('NoteParticipants', () => {
  it('sorts AI participants last and falls back to organization then Guest', () => {
    render(
      <NoteParticipants
        participants={[
          { name: 'Boardy', is_ai_agent: true, source: 'roster' },
          { name: 'Priya Raman', is_ai_agent: false, source: 'roster' },
          { name: null, organization: 'Northwind Labs', source: 'transcript' },
          { name: null, organization: null, source: 'transcript' },
        ]}
      />,
    );

    const items = screen.getAllByRole('listitem');
    expect(items).toHaveLength(4);
    expect(items[0].textContent).toContain('Priya Raman');
    expect(items[1].textContent).toContain('Northwind Labs');
    expect(items[2].textContent).toContain('Guest');
    expect(items[3].textContent).toContain('Boardy');
    expect(items[3].textContent).toContain('AI');
    expect(screen.queryByText(/@/)).toBeNull();
  });

  it('renders nothing when there are no participants', () => {
    const { container } = render(<NoteParticipants participants={[]} />);
    expect(container.firstChild).toBeNull();
  });
});

describe('NoteActionItems', () => {
  it('shows owner chip, context and completed styling', () => {
    render(
      <ActionItemsTab
        items={[
          {
            description: 'Send the recap email',
            completed: true,
            due_at: '2025-10-03T17:00:00Z',
            owner_name: 'Marco Ruiz',
            context: 'From the kickoff discussion',
          },
          {
            description: 'Book the follow-up call',
            completed: false,
          },
        ]}
      />,
    );

    const done = screen.getByText('Send the recap email');
    expect(done.className).toContain('line-through');
    expect(screen.getByText('Marco Ruiz')).toBeTruthy();
    expect(screen.getByText('From the kickoff discussion')).toBeTruthy();
    expect(screen.getByText(/Due:/)).toBeTruthy();
    expect(screen.getByText('Book the follow-up call')).toBeTruthy();
    expect(screen.getByText('1/2 completed')).toBeTruthy();
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
  });
});

describe('NextStepsList', () => {
  it('renders a semantic heading and checklist rows with hidden state text', () => {
    render(
      <NextStepsList
        items={[
          {
            description: 'Send the recap email',
            completed: true,
            due_at: '2025-10-03T17:00:00Z',
            owner_name: 'Marco Ruiz',
            context: 'From the kickoff discussion',
          },
          {
            description: 'Book the follow-up call',
            completed: false,
          },
        ]}
      />,
    );

    expect(screen.getByRole('heading', { name: 'Next steps' })).toBeTruthy();
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
    expect(screen.getByText('Completed')).toBeTruthy();
    expect(screen.getByText('Not completed')).toBeTruthy();

    const done = screen.getByText('Send the recap email');
    expect(done.className).toContain('line-through');
    expect(screen.getByText('Marco Ruiz')).toBeTruthy();
    expect(screen.getByText('MR')).toBeTruthy();
    expect(screen.getByText('From the kickoff discussion')).toBeTruthy();
    expect(screen.getByText(/Due:/)).toBeTruthy();

    const open = screen.getByText('Book the follow-up call');
    expect(open.className).not.toContain('line-through');
  });

  it('renders nothing when the action item list is empty', () => {
    const { container } = render(<NextStepsList items={[]} />);
    expect(container.firstChild).toBeNull();
  });
});
