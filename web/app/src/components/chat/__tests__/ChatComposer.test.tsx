import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ChatComposer } from '@/components/chat/ChatComposer';
import type { MessageFile } from '@/types/conversation';

const reducedMotion = vi.hoisted(() => ({ value: false }));

vi.mock('framer-motion', async (importOriginal) => ({
  ...(await importOriginal<typeof import('framer-motion')>()),
  useReducedMotion: () => reducedMotion.value,
}));

vi.mock('@/lib/api', () => ({
  transcribeVoiceMessage: vi.fn(),
  uploadChatFiles: vi.fn(),
}));

const { uploadChatFiles } = await import('@/lib/api');

type Deferred<T> = { promise: Promise<T>; resolve: (value: T) => void };

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

function uploadedFile(id: string, name: string): MessageFile {
  return {
    id,
    name,
    created_at: '2026-08-11T00:00:00Z',
    mime_type: 'text/plain',
    openai_file_id: `openai-${id}`,
  };
}

const makeMediaQuery = (matches: boolean): MediaQueryList =>
  ({
    matches,
    media: '(prefers-reduced-motion: reduce)',
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }) as unknown as MediaQueryList;

const geometry = (circles: SVGCircleElement[]) =>
  circles.map((circle) => [
    circle.getAttribute('cx'),
    circle.getAttribute('cy'),
    circle.getAttribute('r'),
  ]);

describe('ChatComposer recording control', () => {
  beforeEach(() => {
    reducedMotion.value = false;
    vi.stubGlobal(
      'matchMedia',
      vi.fn(() => makeMediaQuery(false)),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('keeps one dot ring while listening and pulses without changing its geometry', () => {
    const onStart = vi.fn();
    const onStop = vi.fn();
    const { rerender } = render(
      <ChatComposer
        onSend={vi.fn(async () => {})}
        isStreaming={false}
        recording={{ isActive: false, level: 0, onStart, onStop }}
      />,
    );

    const idleButton = screen.getByRole('button', { name: 'Start a live conversation' });
    const idleOrb = within(idleButton).getByRole('img', { name: 'Omi' });
    const idleCircles = Array.from(idleOrb.querySelectorAll('circle'));
    const idleGeometry = geometry(idleCircles);

    expect(idleCircles).toHaveLength(8);
    expect(screen.getByTestId('composer-live-mark')).toHaveAttribute(
      'data-pulse-min',
      '1',
    );

    rerender(
      <ChatComposer
        onSend={vi.fn(async () => {})}
        isStreaming={false}
        recording={{ isActive: true, level: 1, onStart, onStop }}
      />,
    );

    const listeningButton = screen.getByRole('button', { name: 'Stop conversation' });
    const listeningOrb = within(listeningButton).getByRole('img', { name: 'Omi' });
    const listeningCircles = Array.from(listeningOrb.querySelectorAll('circle'));

    expect(geometry(listeningCircles)).toEqual(idleGeometry);
    expect(screen.getByTestId('composer-live-mark')).toHaveAttribute(
      'data-pulse-min',
      '0.94',
    );
    expect(screen.getByTestId('composer-live-mark')).toHaveAttribute(
      'data-pulse-max',
      '1.035',
    );
  });

  it('does not schedule listening movement when reduced motion is enabled', () => {
    reducedMotion.value = true;
    vi.stubGlobal(
      'matchMedia',
      vi.fn(() => makeMediaQuery(true)),
    );

    render(
      <ChatComposer
        onSend={vi.fn(async () => {})}
        isStreaming={false}
        recording={{
          isActive: true,
          level: 1,
          onStart: vi.fn(),
          onStop: vi.fn(),
        }}
      />,
    );

    const button = screen.getByRole('button', { name: 'Stop conversation' });
    expect(
      within(button).getByRole('img', { name: 'Omi' }).querySelectorAll('circle'),
    ).toHaveLength(8);
    expect(screen.getByTestId('composer-live-mark')).toHaveAttribute(
      'data-pulse-min',
      '1',
    );
    expect(screen.getByTestId('composer-live-mark')).toHaveAttribute(
      'data-pulse-max',
      '1',
    );
  });
});

describe('ChatComposer attachments', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('sends uploaded metadata for an attachment-only message', async () => {
    const attachment = uploadedFile('file-1', 'notes.txt');
    vi.mocked(uploadChatFiles).mockResolvedValue([attachment]);
    const onSend = vi.fn(async () => {});
    const { container } = render(<ChatComposer onSend={onSend} isStreaming={false} />);

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(fileInput, {
      target: { files: [new File(['notes'], 'notes.txt', { type: 'text/plain' })] },
    });

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Send message' })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }));

    await waitFor(() => expect(onSend).toHaveBeenCalledWith('', [attachment]));
  });

  it('blocks Enter while an attachment upload is pending', async () => {
    const upload = deferred<MessageFile[]>();
    vi.mocked(uploadChatFiles).mockReturnValue(upload.promise);
    const onSend = vi.fn(async () => {});
    const { container } = render(<ChatComposer onSend={onSend} isStreaming={false} />);
    const textarea = screen.getByPlaceholderText('Ask anything...');
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;

    fireEvent.change(textarea, { target: { value: 'Read this' } });
    fireEvent.change(fileInput, {
      target: { files: [new File(['one'], 'one.txt', { type: 'text/plain' })] },
    });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(onSend).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Send message' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Attach file' })).toBeDisabled();

    await act(async () => {
      upload.resolve([uploadedFile('file-1', 'one.txt')]);
      await upload.promise;
    });

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Send message' })).toBeEnabled(),
    );
  });

  it('keeps send blocked until every concurrent upload batch finishes', async () => {
    const firstUpload = deferred<MessageFile[]>();
    const secondUpload = deferred<MessageFile[]>();
    vi.mocked(uploadChatFiles)
      .mockReturnValueOnce(firstUpload.promise)
      .mockReturnValueOnce(secondUpload.promise);
    const onSend = vi.fn(async () => {});
    const { container } = render(<ChatComposer onSend={onSend} isStreaming={false} />);
    const textarea = screen.getByPlaceholderText('Ask anything...');
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;

    fireEvent.change(textarea, { target: { value: 'Read both' } });
    fireEvent.change(fileInput, {
      target: { files: [new File(['one'], 'one.txt', { type: 'text/plain' })] },
    });
    fireEvent.change(fileInput, {
      target: { files: [new File(['two'], 'two.txt', { type: 'text/plain' })] },
    });
    await waitFor(() => expect(uploadChatFiles).toHaveBeenCalledTimes(2));

    await act(async () => {
      firstUpload.resolve([uploadedFile('file-1', 'one.txt')]);
      await firstUpload.promise;
    });

    fireEvent.keyDown(textarea, { key: 'Enter' });
    expect(onSend).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Send message' })).toBeDisabled();

    const secondAttachment = uploadedFile('file-2', 'two.txt');
    await act(async () => {
      secondUpload.resolve([secondAttachment]);
      await secondUpload.promise;
    });

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Send message' })).toBeEnabled(),
    );
    fireEvent.keyDown(textarea, { key: 'Enter' });

    await waitFor(() =>
      expect(onSend).toHaveBeenCalledWith('Read both', [
        uploadedFile('file-1', 'one.txt'),
        secondAttachment,
      ]),
    );
  });
});

/**
 * Enter means two different things while an IME is open.
 *
 * Typing Japanese, Chinese or Korean, the first Enter confirms the conversion
 * candidate the IME is offering; only a later Enter is meant for the composer.
 * The composer read `e.key === 'Enter' && !e.shiftKey` and sent on both, so
 * confirming a kanji conversion sent the half-written message. macOS already
 * draws the distinction — `ComposerKeyAction.resolve` reads `hasMarkedText`.
 */
describe('ChatComposer IME composition', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const typed = () => {
    const onSend = vi.fn(async () => {});
    render(<ChatComposer onSend={onSend} isStreaming={false} />);
    const textarea = screen.getByPlaceholderText('Ask anything...');
    fireEvent.change(textarea, { target: { value: '漢字' } });
    return { onSend, textarea };
  };

  it('does not send while the IME is composing', () => {
    const { onSend, textarea } = typed();
    fireEvent.keyDown(textarea, { key: 'Enter', isComposing: true });
    expect(onSend).not.toHaveBeenCalled();
  });

  it('does not send on the legacy keyCode 229 composition keydown', () => {
    // Engines without `isComposing` report every composition keydown as 229.
    const { onSend, textarea } = typed();
    fireEvent.keyDown(textarea, { key: 'Enter', keyCode: 229 });
    expect(onSend).not.toHaveBeenCalled();
  });

  it('sends on the Enter that follows a finished composition', async () => {
    const { onSend, textarea } = typed();
    fireEvent.keyDown(textarea, { key: 'Enter' });
    await waitFor(() => expect(onSend).toHaveBeenCalledWith('漢字', []));
  });
});
