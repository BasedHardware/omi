import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LiveTranscript, LiveTranscriptCompact } from '../LiveTranscript';
import { RecordingController } from '@/components/recording/RecordingController';
import {
  RecordingProvider,
  useRecordingContext,
} from '@/components/recording/RecordingContext';

const doubles = vi.hoisted(() => ({
  channel: {
    onmessage: null as null | ((event: MessageEvent) => void),
    postMessage: vi.fn(),
    close: vi.fn(),
  },
  capture: {
    start: vi.fn().mockResolvedValue(undefined),
    stop: vi.fn(),
    pause: vi.fn(),
    resume: vi.fn(),
  },
  socket: {
    connect: vi.fn().mockResolvedValue(undefined),
    sendAudio: vi.fn(),
    disconnect: vi.fn(),
  },
  captureOptions: null as null | {
    onAudioData: (data: Int16Array) => void;
  },
  socketOptions: null as null | {
    onServerBatch: (isBatch: boolean) => void;
    onConversationSession: (id: string) => void;
    onSegment: (segment: {
      id: string;
      text: string;
      speaker: number;
      isUser: boolean;
      timestamp: number;
    }) => void;
  },
  finalizeConversationById: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('@/lib/recordingBroadcast', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/recordingBroadcast')>()),
  createRecordingChannel: () => doubles.channel,
}));

vi.mock('@/lib/audioCapture', () => ({
  isAudioCaptureSupported: () => true,
  createAudioCapture: vi.fn((options) => {
    doubles.captureOptions = options;
    return doubles.capture;
  }),
}));

vi.mock('@/lib/transcriptionSocket', () => ({
  createTranscriptionSocket: vi.fn((options) => {
    doubles.socketOptions = options;
    return doubles.socket;
  }),
}));

vi.mock('@/lib/api', () => ({
  getTranscriptionPreferences: vi.fn().mockResolvedValue({ language: 'en' }),
  processInProgressConversation: vi.fn().mockResolvedValue(undefined),
  finalizeConversationById: doubles.finalizeConversationById,
}));

function RecordingHarness() {
  const { state, segments, isBatchSession, startRecording, stopRecording } =
    useRecordingContext();

  return (
    <>
      <p>{state}</p>
      <p>{isBatchSession ? 'batch' : 'live'}</p>
      <LiveTranscript segments={[]} isBatchSession={isBatchSession} />
      <LiveTranscriptCompact segments={[]} isBatchSession={isBatchSession} />
      {segments.map((segment) => (
        <p key={segment.id}>{segment.text}</p>
      ))}
      <button type="button" onClick={() => void startRecording()}>
        Start
      </button>
      <button type="button" onClick={() => void stopRecording()}>
        Stop
      </button>
    </>
  );
}

describe('RecordingController realtime flow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    doubles.capture.start.mockResolvedValue(undefined);
    doubles.socket.connect.mockResolvedValue(undefined);
    doubles.finalizeConversationById.mockResolvedValue(undefined);
    doubles.captureOptions = null;
    doubles.socketOptions = null;
  });

  it('forwards audio, applies live segments, and stops the active recording', async () => {
    render(
      <RecordingProvider>
        <RecordingController />
        <RecordingHarness />
      </RecordingProvider>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Start' }));

    await waitFor(() => expect(screen.getByText('recording')).toBeInTheDocument());
    expect(doubles.socket.connect).toHaveBeenCalledOnce();
    expect(doubles.capture.start).toHaveBeenCalledOnce();

    const audio = new Int16Array([1, 2, 3]);
    act(() => doubles.captureOptions?.onAudioData(audio));
    expect(doubles.socket.sendAudio).toHaveBeenCalledWith(audio);

    act(() =>
      doubles.socketOptions?.onSegment({
        id: 'live-segment',
        text: 'Live words',
        speaker: 0,
        isUser: true,
        timestamp: 1,
      }),
    );
    expect(screen.getByText('Live words')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Stop' }));

    await waitFor(() => expect(screen.getByText('idle')).toBeInTheDocument());
    expect(doubles.capture.stop).toHaveBeenCalledOnce();
    expect(doubles.socket.disconnect).toHaveBeenCalledOnce();
    expect(doubles.finalizeConversationById).toHaveBeenCalledOnce();
  });
});

describe('RecordingController server batch flow', () => {
  it('shows processing copy, keeps forwarding audio, finalizes by id, and rejects stale mode callbacks', async () => {
    render(
      <RecordingProvider>
        <RecordingController />
        <RecordingHarness />
      </RecordingProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Start' }));
    await waitFor(() => expect(screen.getByText('recording')).toBeInTheDocument());
    expect(screen.getByText('live')).toBeInTheDocument();
    const oldOptions = doubles.socketOptions;
    act(() => {
      oldOptions?.onServerBatch(true);
      oldOptions?.onConversationSession('server-web-conversation');
    });
    expect(screen.getByText('batch')).toBeInTheDocument();
    // A pop-out opened after ready must receive the current mode on request.
    doubles.channel.postMessage.mockClear();
    act(() =>
      doubles.channel.onmessage?.({ data: { type: 'request-state' } } as MessageEvent),
    );
    expect(doubles.channel.postMessage).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'state-update', isBatchSession: true }),
    );
    expect(screen.getAllByRole('status')).toHaveLength(2);
    expect(
      screen.getAllByText('Recording — transcript processes after you stop.'),
    ).toHaveLength(2);
    expect(screen.queryByText('Waiting for speech...')).not.toBeInTheDocument();
    const audio = new Int16Array([4, 5]);
    act(() => doubles.captureOptions?.onAudioData(audio));
    expect(doubles.socket.sendAudio).toHaveBeenLastCalledWith(audio);
    // A new live ready (e.g. reconnect) restores the legacy transcript surface.
    act(() => oldOptions?.onServerBatch(false));
    expect(screen.getByText('Waiting for speech...')).toBeInTheDocument();
    act(() => oldOptions?.onServerBatch(true));
    fireEvent.click(screen.getByRole('button', { name: 'Stop' }));
    await waitFor(() => expect(screen.getByText('idle')).toBeInTheDocument());
    expect(screen.getByText('live')).toBeInTheDocument();
    expect(doubles.finalizeConversationById).toHaveBeenLastCalledWith(
      'server-web-conversation',
    );
    fireEvent.click(screen.getByRole('button', { name: 'Start' }));
    await waitFor(() => expect(screen.getByText('recording')).toBeInTheDocument());
    act(() => oldOptions?.onServerBatch(true));
    expect(screen.getByText('live')).toBeInTheDocument();
    act(() => doubles.socketOptions?.onServerBatch(true));
    fireEvent(window, new Event('pagehide'));
    expect(screen.getByText('live')).toBeInTheDocument();
    expect(screen.getByText('idle')).toBeInTheDocument();
  });
});
