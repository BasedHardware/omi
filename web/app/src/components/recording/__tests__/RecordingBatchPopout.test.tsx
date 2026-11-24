import { act, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import TranscriptPopoutPage from '@/app/record/popout/transcript/page';
import { broadcastStateUpdate } from '@/lib/recordingBroadcast';

const doubles = vi.hoisted(() => ({
  channel: {
    onmessage: null as null | ((event: MessageEvent) => void),
    close: vi.fn(),
    postMessage: vi.fn(),
  },
}));
vi.mock('@/lib/recordingBroadcast', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/recordingBroadcast')>()),
  createRecordingChannel: () => doubles.channel,
}));
vi.mock('@/moonshine/register-client-route', () => ({ registerMoonshineRoute: vi.fn() }));

describe('batch transcript pop-out', () => {
  it('receives batch state and restores legacy copy when the field is absent', () => {
    render(<TranscriptPopoutPage />);
    broadcastStateUpdate(
      doubles.channel as unknown as BroadcastChannel,
      'recording',
      'mic-only',
      12,
      0.5,
      0,
      true,
    );
    const message = doubles.channel.postMessage.mock.calls.at(-1)?.[0];
    expect(message.isBatchSession).toBe(true);
    act(() => doubles.channel.onmessage?.({ data: message } as MessageEvent));
    expect(screen.getByRole('status')).toHaveTextContent(
      'transcript processes after you stop',
    );
    expect(screen.getByText('00:12')).toBeInTheDocument();
    act(() =>
      doubles.channel.onmessage?.({
        data: { ...message, isBatchSession: undefined },
      } as MessageEvent),
    );
    expect(screen.getByText('Listening for speech...')).toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});
