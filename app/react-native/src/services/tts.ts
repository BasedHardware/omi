import { createAudioPlayer, type AudioPlayer } from 'expo-audio';

/**
 * Speech playback for agent replies.
 *
 * The previous implementation called window.speechSynthesis, which does not exist
 * in a React Native runtime -- it is a web API. So there was no voice output at
 * all, only a stub that returned false.
 *
 * Synthesis is server-side, through the omi backend, matching
 * synthesizeSpeech() in the Flutter client (v2/tts/synthesize, ElevenLabs
 * defaults). Generating audio on the phone is not an option: a TTS model that
 * fits in 3.6 GB of RAM produces noticeably worse speech than the server, and the
 * whole point of the local brain was to keep latency off the critical path, not to
 * reimplement synthesis.
 *
 * Playback is expo-audio, which is the maintained module for this on SDK 56;
 * expo-av is deprecated. It plays from a URI, so the synthesised bytes go to a
 * cache file first -- there is no data-URI playback path worth relying on.
 */
export interface SpeakOptions {
  voiceId?: string;
  modelId?: string;
  pitch?: number;
}

/** ElevenLabs "Sloane", the same default the Flutter app ships with. */
const DEFAULT_VOICE = 'BAMYoBHLZM7lJgJAmFz0';
const DEFAULT_MODEL = 'eleven_turbo_v2_5';
const OUTPUT_FORMAT = 'mp3_44100_128';

class Tts {
  private player: AudioPlayer | null = null;
  private inflight: Promise<boolean> | null = null;

  private ensurePlayer(): AudioPlayer {
    this.player ??= createAudioPlayer();
    return this.player;
  }

  /**
   * Synthesizes and plays `text`. Resolves true when playback was started.
   *
   * Concurrent calls share one synthesis: a second call while audio is already
   * speaking is far more likely to be a duplicate than a deliberate
   * interruption, and queueing both would talk over the user.
   */
  async speak(text: string, opts: SpeakOptions = {}): Promise<boolean> {
    const trimmed = text.trim();
    if (!trimmed) return false;
    if (this.inflight) return this.inflight;

    this.inflight = this.speakOnce(trimmed, opts).finally(() => {
      this.inflight = null;
    });
    return this.inflight;
  }

  private async speakOnce(text: string, opts: SpeakOptions): Promise<boolean> {
    try {
      const bytes = await synthesize(text, opts);
      if (!bytes) return false;
      const uri = await cacheAudio(bytes);
      if (!uri) return false;
      const player = this.ensurePlayer();
      player.replace({ uri });
      await player.play();
      return true;
    } catch (e) {
      console.warn('[tts] playback failed:', e);
      return false;
    }
  }

  async stop(): Promise<void> {
    try {
      this.player?.pause();
    } catch {
      // Nothing was playing.
    }
  }

  async isSpeaking(): Promise<boolean> {
    try {
      return this.player ? (await this.player.playing) === true : false;
    } catch {
      return false;
    }
  }

  release(): void {
    try {
      this.player?.remove();
    } catch {
      // Already released.
    }
    this.player = null;
  }
}

/** POSTs to the backend TTS endpoint and returns the audio bytes. */
async function synthesize(text: string, opts: SpeakOptions): Promise<Uint8Array | null> {
  const { ENV } = require('@/config/env') as typeof import('@/config/env');
  const { useAuthStore } = require('@/state/authStore') as typeof import('@/state/authStore');
  const token = useAuthStore.getState().token;

  const res = await fetch(`${ENV.apiBaseUrl}/v2/tts/synthesize`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      // A guest session has no token; the endpoint will 401 and we report that as
      // "no audio" rather than an exception the caller has to catch.
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      text,
      voice_id: opts.voiceId ?? DEFAULT_VOICE,
      model_id: opts.modelId ?? DEFAULT_MODEL,
      output_format: OUTPUT_FORMAT,
    }),
  });
  if (!res.ok) return null;
  return new Uint8Array(await res.arrayBuffer());
}

/**
 * Writes the bytes to a cache file and returns its URI.
 *
 * Required because expo-audio plays from a URI. A content:// or file:// path in
 * the cache directory is what the module expects; a base64 data URI is not
 * reliably supported and would make the size of the reply the bottleneck.
 */
async function cacheAudio(bytes: Uint8Array): Promise<string | null> {
  try {
    const { File, Paths } = require('expo-file-system') as typeof import('expo-file-system');
    const dir = new File(Paths.cache, 'tts');
    if (!dir.exists) dir.create({ intermediates: true });
    const name = `reply-${Date.now()}.mp3`;
    const file = new File(dir, name);
    file.write(bytes);
    return file.uri;
  } catch (e) {
    console.warn('[tts] could not cache audio:', e);
    return null;
  }
}

export const tts = new Tts();
export { synthesize as synthesizeSpeech };