import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { HomePage } from '@/components/home/HomePage';
import type { MessageFile } from '@/types/conversation';

const sendMessage = vi.fn(async () => undefined);
const loadHistory = vi.fn(async () => undefined);
const appendRealtimeExchange = vi.fn(async () => undefined);
const startLive = vi.fn(async () => undefined);

vi.mock('@tschk/moonshine-next/image', () => ({
  default: ({ alt }: React.ComponentProps<'img'>) => <img alt={alt} />,
}));
vi.mock('@/components/auth/AuthProvider', () => ({
  useAuth: () => ({ user: { displayName: 'Ada Lovelace' } }),
}));
vi.mock('@/components/chat/ChatContext', () => ({
  useChat: () => ({
    selectedAppId: null,
    selectedChatSessionId: null,
    chat: {
      messages: [
        {
          id: 'human-1',
          sender: 'human',
          text: 'Earlier question',
          created_at: '2026-08-11T00:00:00Z',
        },
        {
          id: 'ai-1',
          sender: 'ai',
          text: 'Earlier answer',
          created_at: '2026-08-11T00:00:01Z',
        },
      ],
      isLoading: false,
      isStreaming: false,
      streamingText: '',
      currentThinking: '',
      error: null,
      sendMessage,
      loadHistory,
      appendRealtimeExchange,
    },
  }),
}));
vi.mock('@/hooks/useGeminiLive', () => ({
  useGeminiLive: () => ({
    state: 'idle',
    segments: [],
    duration: 0,
    level: 0,
    error: null,
    start: startLive,
    pause: vi.fn(),
    resume: vi.fn(),
    stop: vi.fn(),
  }),
}));
vi.mock('@/hooks/useGoals', () => ({
  useGoals: () => ({
    goals: [{ id: 'goal-1', title: 'Keep the Home layout readable' }],
    loading: false,
    error: null,
    addGoal: vi.fn(),
    editGoal: vi.fn(),
    setProgress: vi.fn(),
    removeGoal: vi.fn(),
  }),
}));
vi.mock('@/components/home/GoalCard', () => ({
  GoalCard: ({ goal }: { goal: { title: string } }) => <li>{goal.title}</li>,
}));
vi.mock('@/hooks/useHomeTasks', () => ({
  useHomeTasks: () => ({
    items: [{ id: 'task-1', description: 'Review the launch plan' }],
    loading: false,
    error: null,
    complete: vi.fn(),
  }),
}));
vi.mock('@/hooks/useScrollEdges', () => ({
  useScrollEdges: () => ({
    ref: { current: null },
    edges: { atTop: true, atBottom: true },
  }),
}));
vi.mock('@/components/chat/ChatTranscript', () => ({
  ChatTranscript: ({ messages }: { messages: Array<{ id: string }> }) => (
    <div>
      {messages.map((message) => (
        <span key={message.id}>{message.id}</span>
      ))}
    </div>
  ),
}));
vi.mock('@/components/chat/ChatComposer', () => ({
  ChatComposer: ({
    onSend,
    recording,
  }: {
    onSend: (text: string, files: MessageFile[]) => void;
    recording: { onStart: () => void };
  }) => (
    <>
      <button type="button" onClick={() => onSend('New question', [])}>
        Send test
      </button>
      <button type="button" onClick={recording.onStart}>
        Start live test
      </button>
    </>
  ),
}));
vi.mock('@/components/home/GoalComposer', () => ({ GoalComposer: () => null }));
vi.mock('@/components/home/GoalDetailSheet', () => ({ GoalDetailSheet: () => null }));
vi.mock('@/components/chat/RecordingStage', () => ({ RecordingStage: () => null }));

beforeEach(() => {
  vi.clearAllMocks();
  loadHistory.mockReset();
  loadHistory.mockResolvedValue(undefined);
  Element.prototype.scrollIntoView = vi.fn();
  window.requestAnimationFrame = (callback) => {
    callback(0);
    return 1;
  };
});

describe('Home Currents ordering', () => {
  it('keeps prior history above Currents and opens the live exchange below it', async () => {
    render(<HomePage />);

    await waitFor(() => expect(loadHistory).toHaveBeenCalledTimes(1));
    const history = screen.getByRole('region', { name: 'Chat history' });
    const currents = screen.getByRole('region', { name: 'Currents' });
    const goals = screen.getByText('Keep the Home layout readable').closest('ul');

    expect(
      history.compareDocumentPosition(currents) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(currents).toHaveClass('scroll-mt-56', 'min-h-[calc(100%-14rem)]');
    expect(goals).toHaveClass('grid');
    expect(goals).not.toHaveClass('sm:grid-cols-2');
    expect(
      screen.queryByRole('region', { name: 'Current chat' }),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Send test' }));

    const currentChat = screen.getByRole('region', { name: 'Current chat' });
    expect(
      currents.compareDocumentPosition(currentChat) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(sendMessage).toHaveBeenCalledWith('New question', [], undefined, []);
  });

  it('routes the composer live control through Gemini Live', () => {
    render(<HomePage />);

    fireEvent.click(screen.getByRole('button', { name: 'Start live test' }));

    expect(startLive).toHaveBeenCalledTimes(1);
  });

  it('places Currents in view after history loads', async () => {
    render(<HomePage />);

    await waitFor(() => expect(loadHistory).toHaveBeenCalledTimes(1));
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
  });

  it('does not snap Currents back into view after the reader scrolls history', async () => {
    let resolveHistory!: (value: undefined) => void;
    loadHistory.mockImplementation(
      () =>
        new Promise<undefined>((resolve) => {
          resolveHistory = resolve;
        }),
    );

    render(<HomePage />);
    const history = await screen.findByRole('region', { name: 'Chat history' });
    fireEvent.wheel(history);

    const scrollIntoView = Element.prototype.scrollIntoView as ReturnType<typeof vi.fn>;
    scrollIntoView.mockClear();
    resolveHistory(undefined);

    await waitFor(() => expect(loadHistory).toHaveBeenCalledTimes(1));
    expect(scrollIntoView).not.toHaveBeenCalled();
  });
});
