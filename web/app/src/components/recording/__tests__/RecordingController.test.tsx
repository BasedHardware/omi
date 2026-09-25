import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { RecordingController } from '@/components/recording/RecordingController';
import {
  RecordingProvider,
  useRecordingContext,
} from '@/components/recording/RecordingContext';

const doubles = vi.hoisted(() => ({
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
  const { state, segments, startRecording, stopRecording } = useRecordingContext();

  return (
    <>
      <p>{state}</p>
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
