/** @jest-environment node */

describe('captureStore session fencing', () => {
  beforeEach(() => {
    jest.resetModules();
  });

  it('ignores stale OMI audio/error callbacks from a previous session', async () => {
    let audioCb: ((bytes: Uint8Array) => void) | null = null;
    let errorCb: ((e: unknown) => void) | null = null;
    let onOpen: (() => void) | null = null;
    let onClose: (() => void) | null = null;
    let onError: ((e: Error) => void) | null = null;
    const sendAudio = jest.fn();
    const close = jest.fn();
    let streamCount = 0;

    class FakeStream {
      connect = jest.fn(() => {
        if (streamCount === 1) onOpen?.();
      });
      sendAudio = sendAudio;
      close = close;
      constructor(handlers: any) {
        streamCount++;
        if (streamCount === 1) {
          onOpen = handlers.onOpen;
          onClose = handlers.onClose;
          onError = handlers.onError;
        }
      }
    }

    jest.doMock('@/services/stt', () => ({ DeepgramStream: FakeStream }));
    jest.doMock('@/services/voiceprint', () => ({
      createVoiceprint: () => ({ isEnrolled: () => true, enroll: jest.fn(), labelForSpeaker: () => ({ label: 'You', isUser: true }) }),
    }));
    jest.doMock('@/services/mic', () => ({ startMic: jest.fn() }));
    jest.doMock('@/services/localConversations', () => ({ appendSegments: jest.fn(async () => undefined) }));
    jest.doMock('@/config/env', () => ({ ENV: { listenWsUrl: 'wss://api.test/listen' } }));
    jest.doMock('@/state/authStore', () => ({ useAuthStore: { getState: () => ({ token: 'tok' }) } }));
    jest.doMock('@/services/omiBle', () => ({
      sttCodecName: () => 'opus',
      omiStreamParams: () => ({ codec: 'opus', sample_rate: '16000', channels: '1', language: 'multi' }),
      omiBle: {
        stopAudio: jest.fn(),
        startAudio: jest.fn(async () => true),
        startAudioError: jest.fn(() => null),
        onAudio: jest.fn((cb: any, errCb: any) => {
          audioCb = cb;
          errorCb = errCb;
        }),
      },
    }));

    const { useCaptureStore } = require('./captureStore') as typeof import('./captureStore');
    useCaptureStore.getState().startFromOmi('opus' as any);
    await Promise.resolve();
    await Promise.resolve();

    expect(useCaptureStore.getState().recording).toBe(true);

    // Start a second session before first async callbacks settle; stop invalidates session.
    useCaptureStore.getState().stop();
    useCaptureStore.getState().startFromOmi('opus' as any);

    // Stale callbacks from session 1 must not send audio or force-stop session 2.
    audioCb?.(new Uint8Array([1, 2, 3]));
    errorCb?.(new Error('stale'));
    onClose?.();
    onError?.(new Error('stale ws'));

    expect(sendAudio).not.toHaveBeenCalled();
    // Session 2 is still connecting/managed independently (no forced stop from stale session 1).
    expect(useCaptureStore.getState().connecting || useCaptureStore.getState().recording).toBe(true);
  });
});
