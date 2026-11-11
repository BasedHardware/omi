import { act, cleanup, render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { RecordingController } from '../RecordingController';
import { RecordingProvider, useRecordingContext } from '../RecordingContext';

const fakes = vi.hoisted(() => ({
  sockets: [] as Array<{
    connect: ReturnType<typeof vi.fn>;
    disconnect: ReturnType<typeof vi.fn>;
    sendAudio: ReturnType<typeof vi.fn>;
  }>,
  captures: [] as Array<{
    start: ReturnType<typeof vi.fn>;
    stop: ReturnType<typeof vi.fn>;
    pause: ReturnType<typeof vi.fn>;
    resume: ReturnType<typeof vi.fn>;
  }>,
  getPreferences: vi.fn(),
  connect: vi.fn(),
  startCapture: vi.fn(),
  realCapture: false,
  socketOptions: [] as Array<
    Parameters<typeof import('@/lib/transcriptionSocket').createTranscriptionSocket>[0]
  >,
  finalize: vi.fn(),
  fallbackFinalize: vi.fn(),
  processors: [] as Array<{
    onaudioprocess:
      | null
      | ((event: { inputBuffer: { getChannelData: () => Float32Array } }) => void);
  }>,
}));

vi.mock('@/lib/api', () => ({
  getTranscriptionPreferences: fakes.getPreferences,
  finalizeConversationById: fakes.finalize,
  processInProgressConversation: fakes.fallbackFinalize,
}));
vi.mock('@/lib/recordingBroadcast', () => ({
  createRecordingChannel: () => null,
  broadcastStateUpdate: vi.fn(),
  broadcastSegmentsUpdate: vi.fn(),
}));
vi.mock('@/lib/transcriptionSocket', () => ({
  createTranscriptionSocket: (
    options: Parameters<
      typeof import('@/lib/transcriptionSocket').createTranscriptionSocket
    >[0],
  ) => {
    fakes.socketOptions.push(options);
    const socket = {
      connect: vi.fn(() => fakes.connect()),
      disconnect: vi.fn(),
      sendAudio: vi.fn(),
    };
    fakes.sockets.push(socket);
    return socket;
  },
}));
vi.mock('@/lib/audioCapture', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/audioCapture')>();
  return {
    isAudioCaptureSupported: () => true,
    createAudioCapture: (
      options: Parameters<typeof import('@/lib/audioCapture').createAudioCapture>[0],
    ) => {
      if (fakes.realCapture) return actual.createAudioCapture(options);
      const capture = {
        start: vi.fn(() => fakes.startCapture()),
        stop: vi.fn(),
        pause: vi.fn(),
        resume: vi.fn(),
      };
      fakes.captures.push(capture);
      return capture;
    },
  };
});

let context: ReturnType<typeof useRecordingContext>;
function Harness() {
  context = useRecordingContext();
  return <p>{context.state}</p>;
}
function mount() {
  render(
    <RecordingProvider>
      <RecordingController />
      <Harness />
    </RecordingProvider>,
  );
}
function deferred() {
  let resolve!: () => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<void>((done, fail) => {
    resolve = done;
    reject = fail;
  });
  return { promise, resolve, reject };
}

describe('recording startup ownership', () => {
  beforeEach(() => {
    fakes.realCapture = false;
    fakes.processors.length = 0;
    fakes.socketOptions.length = 0;
    fakes.finalize.mockResolvedValue(undefined);
    fakes.fallbackFinalize.mockResolvedValue(undefined);
    fakes.sockets.length = 0;
    fakes.captures.length = 0;
    fakes.getPreferences.mockResolvedValue({ language: 'en' });
    fakes.connect.mockResolvedValue(undefined);
    fakes.startCapture.mockResolvedValue(undefined);
  });
  afterEach(() => {
    if (context.durationIntervalRef.current)
      clearInterval(context.durationIntervalRef.current);
    cleanup();
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it('control: one start followed by stop releases its socket and capture', async () => {
    mount();
    await act(async () => {
      await context.startRecording();
    });
    expect(context.state).toBe('recording');
    await act(async () => {
      await context.stopRecording();
    });
    expect(fakes.sockets[0].disconnect).toHaveBeenCalledOnce();
    expect(fakes.captures[0].stop).toHaveBeenCalledOnce();
  });

  it('two overlapping Starts leave no recording resources alive after Stop', async () => {
    const gate = deferred();
    fakes.connect.mockReturnValue(gate.promise);
    mount();
    let first!: Promise<void>;
    let second!: Promise<void>;
    act(() => {
      first = context.startRecording();
      second = context.startRecording();
    });
    await waitFor(() => expect(fakes.sockets.length).toBeGreaterThan(0));
    await act(async () => {
      gate.resolve();
      await Promise.all([first, second]);
    });
    await act(async () => {
      await context.stopRecording();
    });
    expect(context.state).toBe('idle');
    expect(
      fakes.sockets.filter((socket) => socket.disconnect.mock.calls.length === 0),
    ).toHaveLength(0);
    expect(
      fakes.captures.filter((capture) => capture.stop.mock.calls.length === 0),
    ).toHaveLength(0);
  });

  it('Stop while connecting cancels startup before microphone capture', async () => {
    const gate = deferred();
    fakes.connect.mockReturnValue(gate.promise);
    mount();
    let starting!: Promise<void>;
    act(() => {
      starting = context.startRecording();
    });
    await waitFor(() => expect(fakes.sockets).toHaveLength(1));
    await act(async () => {
      await context.stopRecording();
    });
    await act(async () => {
      gate.resolve();
      await starting;
    });
    expect(context.state).toBe('idle');
    expect(fakes.captures).toHaveLength(0);
    expect(fakes.sockets[0].disconnect).toHaveBeenCalled();
    expect(fakes.finalize).not.toHaveBeenCalled();
    expect(fakes.fallbackFinalize).not.toHaveBeenCalled();
  });

  it('pagehide while connecting prevents a late startup from acquiring the microphone', async () => {
    const gate = deferred();
    fakes.connect.mockReturnValue(gate.promise);
    mount();
    let starting!: Promise<void>;
    act(() => {
      starting = context.startRecording();
    });
    await waitFor(() => expect(fakes.sockets).toHaveLength(1));
    act(() => {
      window.dispatchEvent(new Event('pagehide'));
    });
    await act(async () => {
      gate.resolve();
      await starting;
    });
    expect(fakes.captures).toHaveLength(0);
    expect(fakes.sockets[0].disconnect).toHaveBeenCalled();
    expect(fakes.finalize).not.toHaveBeenCalled();
    expect(fakes.fallbackFinalize).not.toHaveBeenCalled();
  });
  it('real audio capture control: normal Stop ends the microphone track', async () => {
    const tracks = fakeAudioDevices();
    mount();
    await act(async () => {
      await context.startRecording();
    });
    await act(async () => {
      await context.stopRecording();
    });
    expect(tracks).toHaveLength(1);
    expect(tracks[0].stop).toHaveBeenCalledOnce();
  });
  it('real audio capture: two Starts followed by Stop leave no live microphone track', async () => {
    const tracks = fakeAudioDevices();
    mount();
    await act(async () => {
      await Promise.all([context.startRecording(), context.startRecording()]);
    });
    await act(async () => {
      await context.stopRecording();
    });
    expect(context.state).toBe('idle');
    expect
      .soft(tracks.filter((track) => track.stop.mock.calls.length === 0))
      .toHaveLength(0);
    // Only a live track can deliver another audio event after Stop.
    if (tracks[0].stop.mock.calls.length === 0) {
      fakes.processors[0].onaudioprocess?.({
        inputBuffer: { getChannelData: () => new Float32Array([0.2, 0.3, 0.4]) },
      });
    }
    expect.soft(fakes.sockets[0].sendAudio).not.toHaveBeenCalled();
  });

  it('Stop before preferences resolve acquires no recording resources', async () => {
    const gate = deferred();
    fakes.getPreferences.mockReturnValue(gate.promise.then(() => ({ language: 'en' })));
    mount();
    let starting!: Promise<void>;
    act(() => {
      starting = context.startRecording();
    });
    await act(async () => {
      await context.stopRecording();
      gate.resolve();
      await starting;
    });
    expect(context.state).toBe('idle');
    expect(fakes.sockets).toHaveLength(0);
    expect(fakes.finalize).not.toHaveBeenCalled();
  });

  it.each(['resolve', 'reject'] as const)(
    'a cancelled capture that later %ss cannot affect a replacement',
    async (outcome) => {
      const gate = deferred();
      fakes.startCapture.mockReturnValueOnce(gate.promise);
      mount();
      let first!: Promise<void>;
      act(() => {
        first = context.startRecording();
      });
      await waitFor(() => expect(fakes.captures).toHaveLength(1));
      const retiredCallbacks = fakes.socketOptions[0];
      await act(async () => {
        await context.stopRecording();
        await context.startRecording();
      });
      expect(context.state).toBe('recording');
      act(() => {
        retiredCallbacks.onConversationSession?.('old-id');
      });
      await act(async () => {
        if (outcome === 'resolve') gate.resolve();
        else gate.reject(new Error('late failure'));
        await first;
      });
      expect(context.state).toBe('recording');
      expect(context.error).toBeNull();
      expect(fakes.captures[1].stop).not.toHaveBeenCalled();
      expect(fakes.sockets[1].disconnect).not.toHaveBeenCalled();
      const newId = fakes.socketOptions[1].clientConversationId;
      await act(async () => {
        await context.stopRecording();
      });
      expect(fakes.finalize).toHaveBeenCalledWith(newId);
      expect(fakes.fallbackFinalize).not.toHaveBeenCalled();
    },
  );

  it('provider teardown retires pending startup', async () => {
    const gate = deferred();
    fakes.connect.mockReturnValue(gate.promise);
    mount();
    let starting!: Promise<void>;
    act(() => {
      starting = context.startRecording();
    });
    await waitFor(() => expect(fakes.sockets).toHaveLength(1));
    cleanup();
    await act(async () => {
      gate.resolve();
      await starting;
    });
    expect(fakes.captures).toHaveLength(0);
    expect(fakes.sockets[0].disconnect).toHaveBeenCalled();
  });
});

function fakeAudioDevices() {
  fakes.realCapture = true;
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] });
  const tracks: Array<{ stop: ReturnType<typeof vi.fn> }> = [];
  const node = () => ({
    connect: vi.fn(),
    disconnect: vi.fn(),
    fftSize: 256,
    gain: { value: 1 },
    getFloatTimeDomainData: vi.fn(),
  });
  class FakeAudioContext {
    sampleRate = 48000;
    destination = node();
    createMediaStreamSource = node;
    createAnalyser = node;
    createGain = node;
    createScriptProcessor = () => {
      const processor = {
        ...node(),
        onaudioprocess: null as
          | null
          | ((event: { inputBuffer: { getChannelData: () => Float32Array } }) => void),
      };
      fakes.processors.push(processor);
      return processor;
    };
    close = vi.fn().mockResolvedValue(undefined);
  }
  vi.stubGlobal('AudioContext', FakeAudioContext);
  vi.stubGlobal('navigator', {
    mediaDevices: {
      getUserMedia: vi.fn(async () => {
        const track = { stop: vi.fn() };
        tracks.push(track);
        return { getTracks: () => [track] };
      }),
    },
  });
  return tracks;
}
