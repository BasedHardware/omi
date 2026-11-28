/** @jest-environment node */

describe('tts cache and playback', () => {
  beforeEach(() => {
    jest.resetModules();
    jest.clearAllMocks();
  });

  it('creates a cache directory (not a file) and writes the MP3 under it', async () => {
    const dirCreate = jest.fn();
    const fileWrite = jest.fn();
    const dir = { exists: false, create: dirCreate, uri: 'file:///cache/tts' };
    const file = { write: fileWrite, uri: 'file:///cache/tts/reply-123.mp3' };
    const Directory = jest.fn().mockImplementation(() => dir);
    const File = jest.fn().mockImplementation(() => file);

    jest.doMock('expo-file-system', () => ({
      Directory,
      File,
      Paths: { cache: 'file:///cache' },
    }));
    jest.doMock('expo-audio', () => ({ createAudioPlayer: jest.fn(() => ({ play: jest.fn(), replace: jest.fn(), pause: jest.fn(), remove: jest.fn() })) }));
    jest.doMock('@/config/env', () => ({ ENV: { apiBaseUrl: 'https://api.test' } }));
    jest.doMock('@/state/authStore', () => ({ useAuthStore: { getState: () => ({ token: null }) } }));

    const { __ttsTest } = require('./tts') as typeof import('./tts');
    const uri = await __ttsTest.cacheAudio(new Uint8Array([1, 2, 3]));

    expect(Directory).toHaveBeenCalledWith('file:///cache', 'tts');
    expect(dirCreate).toHaveBeenCalledWith({ intermediates: true, idempotent: true });
    expect(File).toHaveBeenCalledWith(dir, expect.stringMatching(/^reply-\d+\.mp3$/));
    expect(fileWrite).toHaveBeenCalledWith(new Uint8Array([1, 2, 3]));
    expect(uri).toBe('file:///cache/tts/reply-123.mp3');
  });

  it('synthesizes, caches, and plays through expo-audio', async () => {
    const play = jest.fn(async () => undefined);
    const replace = jest.fn();
    const player = { play, replace, pause: jest.fn(), remove: jest.fn(), playing: false };
    jest.doMock('expo-audio', () => ({ createAudioPlayer: jest.fn(() => player) }));

    const dir = { exists: true, create: jest.fn(), uri: 'file:///cache/tts' };
    const file = { write: jest.fn(), uri: 'file:///cache/tts/reply-123.mp3' };
    jest.doMock('expo-file-system', () => ({
      Directory: jest.fn(() => dir),
      File: jest.fn(() => file),
      Paths: { cache: 'file:///cache' },
    }));
    jest.doMock('@/config/env', () => ({ ENV: { apiBaseUrl: 'https://api.test' } }));
    jest.doMock('@/state/authStore', () => ({ useAuthStore: { getState: () => ({ token: 'tok' }) } }));

    const fetchMock = jest.fn(async () => ({
      ok: true,
      arrayBuffer: async () => new Uint8Array([9, 8, 7]).buffer,
    }));
    (globalThis as any).fetch = fetchMock;

    const { tts } = require('./tts') as typeof import('./tts');
    const ok = await tts.speak('hello world');

    expect(ok).toBe(true);
    expect(fetchMock).toHaveBeenCalled();
    expect(file.write).toHaveBeenCalledWith(new Uint8Array([9, 8, 7]));
    expect(replace).toHaveBeenCalledWith({ uri: 'file:///cache/tts/reply-123.mp3' });
    expect(play).toHaveBeenCalled();
  });
});
