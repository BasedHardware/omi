import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ChatComposer } from '@/components/chat/ChatComposer';
import { ChatPanel } from '@/components/chat/ChatPanel';
import { InlineVoiceRecorder } from '@/components/chat/VoiceRecorder';

vi.mock('@/lib/api', () => ({
  uploadChatFiles: vi.fn(async () => []),
  transcribeVoiceMessage: vi.fn(),
  getChatApps: vi.fn(async () => []),
}));

vi.mock('@/lib/analytics/mixpanel', () => ({
  MixpanelManager: { track: vi.fn() },
}));

const panelChat = vi.hoisted(() => ({ isStreaming: false }));

vi.mock('@/components/chat/ChatContext', () => ({
  useChat: () => ({
    isOpen: true,
    closeChat: vi.fn(),
    currentContext: undefined,
    selectedAppId: null,
    clearAppContext: vi.fn(),
    chat: {
      messages: [],
      isLoading: false,
      isStreaming: panelChat.isStreaming,
      streamingText: '',
      currentThinking: '',
      error: null,
      sendMessage: vi.fn(async () => undefined),
      clearHistory: vi.fn(async () => undefined),
      loadHistory: vi.fn(async () => undefined),
    },
  }),
}));

const { transcribeVoiceMessage } = await import('@/lib/api');

// The alignment contract: one shell governs every composer action control —
// fixed square box on both breakpoint tiers, circular shape, flex-centered
// glyph, row containment. jsdom performs no layout, so the assertions target
// the class-token contract; pixel truth is covered by the manual visual pass.
const SHELL_TOKENS = [
  'flex',
  'items-center',
  'justify-center',
  'rounded-full',
  'h-10',
  'w-10',
  'sm:h-9',
  'sm:w-9',
  'flex-shrink-0',
];
const BOX_TOKENS = ['h-10', 'w-10', 'sm:h-9', 'sm:w-9'];
const GLYPH_TOKENS = ['h-[18px]', 'w-[18px]'];

const classTokens = (el: Element): string[] =>
  (el.getAttribute('class') ?? '').split(/\s+/);

const boxTokens = (el: Element): string[] =>
  BOX_TOKENS.filter((token) => classTokens(el).includes(token));

const glyphTokens = (el: Element): string[] => {
  const svg = el.querySelector('svg');
  if (!svg) return [];
  return GLYPH_TOKENS.filter((token) => classTokens(svg).includes(token));
};

const expectShell = (button: Element) => {
  const tokens = classTokens(button);
  for (const token of SHELL_TOKENS) {
    expect(
      tokens,
      `expected "${token}" on ${
        button.getAttribute('aria-label') ?? button.getAttribute('title') ?? 'button'
      }`,
    ).toContain(token);
  }
};

// Hermetic capture stubs so InlineVoiceRecorder renders outside a browser.
// No real capture, network, or timers are involved.
class FakeMediaRecorder {
  static isTypeSupported = vi.fn(() => true);
  state = 'inactive';
  mimeType = 'audio/webm';
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  start() {
    this.state = 'recording';
  }
  stop() {
    this.state = 'inactive';
    this.ondataavailable?.({ data: new Blob(['audio'], { type: 'audio/webm' }) });
    this.onstop?.();
  }
}

const installCaptureStubs = () => {
  vi.stubGlobal('MediaRecorder', FakeMediaRecorder);
  Object.defineProperty(navigator, 'mediaDevices', {
    value: { getUserMedia: vi.fn(async () => ({ getTracks: () => [] })) },
    configurable: true,
  });
};

beforeEach(() => {
  installCaptureStubs();
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
  vi.unstubAllGlobals();
  delete (navigator as unknown as { mediaDevices?: MediaDevices }).mediaDevices;
  vi.clearAllMocks();
});

describe('main composer control alignment', () => {
  it('gives attach, voice, and send one fixed circular flex-centered contract', () => {
    render(<ChatComposer onSend={vi.fn(async () => {})} isStreaming={false} />);

    const attach = screen.getByRole('button', { name: 'Attach file' });
    const mic = screen.getByTitle('Click to start recording');
    const send = screen.getByRole('button', { name: 'Send message' });

    expectShell(attach);
    expectShell(mic);
    expectShell(send);
    expect(boxTokens(attach)).toEqual(boxTokens(mic));
    expect(boxTokens(mic)).toEqual(boxTokens(send));
  });

  it('keeps one glyph size family across the controls row', () => {
    render(<ChatComposer onSend={vi.fn(async () => {})} isStreaming={false} />);

    const attach = screen.getByRole('button', { name: 'Attach file' });
    const mic = screen.getByTitle('Click to start recording');
    const send = screen.getByRole('button', { name: 'Send message' });

    expect(glyphTokens(attach)).toEqual(GLYPH_TOKENS);
    expect(glyphTokens(mic)).toEqual(GLYPH_TOKENS);
    expect(glyphTokens(send)).toEqual(GLYPH_TOKENS);
  });

  it('holds the geometry invariant while streaming disables the controls', () => {
    render(<ChatComposer onSend={vi.fn(async () => {})} isStreaming={true} />);

    const attach = screen.getByRole('button', { name: 'Attach file' });
    const mic = screen.getByTitle('Click to start recording');
    const send = screen.getByRole('button', { name: 'Send message' });

    expect(attach).toBeDisabled();
    expect(mic).toBeDisabled();
    expect(send).toBeDisabled();
    expectShell(attach);
    expectShell(mic);
    expectShell(send);
    expect(boxTokens(attach)).toEqual(boxTokens(mic));
    expect(boxTokens(mic)).toEqual(boxTokens(send));
  });
});

describe('panel composer control alignment', () => {
  it('gives attach, voice, and send one fixed circular flex-centered contract', () => {
    render(<ChatPanel />);

    const attach = screen.getByRole('button', { name: 'Attach file' });
    const mic = screen.getByTitle('Click to start recording');
    const send = screen.getByRole('button', { name: 'Send message' });

    expectShell(attach);
    expectShell(mic);
    expectShell(send);
    expect(boxTokens(attach)).toEqual(boxTokens(mic));
    expect(boxTokens(mic)).toEqual(boxTokens(send));
  });

  it('keeps one glyph size family across the controls row', () => {
    render(<ChatPanel />);

    const attach = screen.getByRole('button', { name: 'Attach file' });
    const mic = screen.getByTitle('Click to start recording');
    const send = screen.getByRole('button', { name: 'Send message' });

    expect(glyphTokens(attach)).toEqual(GLYPH_TOKENS);
    expect(glyphTokens(mic)).toEqual(GLYPH_TOKENS);
    expect(glyphTokens(send)).toEqual(GLYPH_TOKENS);
  });

  it('preserves the accessible names on the panel controls', () => {
    render(<ChatPanel />);

    expect(screen.getByRole('button', { name: 'Attach file' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Send message' })).toBeInTheDocument();
    expect(screen.getByTitle('Click to start recording')).toBeInTheDocument();
  });
});

describe('voice control state invariance', () => {
  it('keeps the box geometry through idle, recording, transcribing, and back', async () => {
    const onTranscript = vi.fn();
    vi.mocked(transcribeVoiceMessage).mockReturnValue(new Promise(() => {}));
    render(<InlineVoiceRecorder onTranscript={onTranscript} />);

    const mic = () => screen.getByTitle('Click to start recording');
    const idleBox = boxTokens(mic());
    expectShell(mic());

    fireEvent.click(mic());
    const recordingButton = await screen.findByTitle('Click to stop and transcribe');
    expect(classTokens(recordingButton)).toContain('bg-error');
    expect(classTokens(recordingButton)).toContain('animate-pulse');
    expect(boxTokens(recordingButton)).toEqual(idleBox);
    expectShell(recordingButton);

    fireEvent.click(recordingButton);
    const transcribingButton = await screen.findByTitle('Transcribing...');
    expect(transcribingButton).toBeDisabled();
    expect(classTokens(transcribingButton)).toContain('cursor-not-allowed');
    expect(transcribingButton.querySelector('svg')).toHaveAttribute(
      'class',
      expect.stringContaining('animate-spin'),
    );
    expect(boxTokens(transcribingButton)).toEqual(idleBox);
    expectShell(transcribingButton);
  });

  it('returns to the idle geometry after transcription settles', async () => {
    vi.mocked(transcribeVoiceMessage).mockResolvedValue('hello');
    const onTranscript = vi.fn();
    render(<InlineVoiceRecorder onTranscript={onTranscript} />);

    const mic = () => screen.getByTitle('Click to start recording');
    const idleBox = boxTokens(mic());

    fireEvent.click(mic());
    const recordingButton = await screen.findByTitle('Click to stop and transcribe');
    fireEvent.click(recordingButton);

    await waitFor(() => expect(onTranscript).toHaveBeenCalledWith('hello'));
    await waitFor(() =>
      expect(screen.getByTitle('Click to start recording')).toBeInTheDocument(),
    );
    expect(boxTokens(mic())).toEqual(idleBox);
    expectShell(mic());
  });
});
