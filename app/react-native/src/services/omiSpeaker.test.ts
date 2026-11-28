/**
 * The speaker protocol is firmware-shaped, not RFC-shaped, so the tests encode
 * what speak() in omi/firmware/devkit/src/speaker.c actually does.
 */
import {
  MAX_MONO_BYTES_PER_TRANSMISSION,
  MAX_STREAMING_MONO_BYTES_PER_TRANSMISSION,
  PACKET_SIZE,
  firmwareSupportsStreaming,
  lengthHeader,
  looksLikeMp3,
  makeTonePcm,
  padForFirmware,
  planTransmissions,
  playPcm16Mono8k,
  splitSpeechChunks,
  ulawToPcm16,
  type SpeakerIo,
} from './omiSpeaker';

describe('padForFirmware', () => {
  it('escapes the exactly-400 stall by silence', () => {
    // Old speak(): current_length > 400 consumes, < 400 plays; == 400 falls
    // between both branches and the clip never plays.
    const exact = new Uint8Array(PACKET_SIZE);
    const padded = padForFirmware(exact);
    expect(padded.length).toBe(PACKET_SIZE + 8);
    expect(padded.length % PACKET_SIZE).not.toBe(0);
  });

  it('escapes the 4-byte tail that speak() would re-read as a length header', () => {
    const tail = new Uint8Array(PACKET_SIZE + 4);
    const padded = padForFirmware(tail);
    expect(padded.length % PACKET_SIZE).not.toBe(4);
    expect(padded.length % PACKET_SIZE).toBe(6);
  });

  it('does not touch unambiguous lengths', () => {
    const ok = new Uint8Array(1000); // 1000 % 400 == 200
    expect(padForFirmware(ok)).toBe(ok);
  });
});

describe('planTransmissions', () => {
  it('caps each transmission under the pre-2.0.11 5,000-byte buffer', () => {
    const pcm = new Uint8Array(MAX_MONO_BYTES_PER_TRANSMISSION * 2 + 1200);
    const sends = planTransmissions(pcm);
    expect(sends.length).toBe(3);
    for (const s of sends) {
      expect(s.length).toBeLessThanOrEqual(5000);
      expect(s.length % PACKET_SIZE).not.toBe(0);
      expect(s.length % PACKET_SIZE).not.toBe(4);
    }
  });

  it('reconstructs the input exactly: original bytes first, silence pads last', () => {
    const pcm = new Uint8Array(9000).fill(0x42);
    const sends = planTransmissions(pcm);
    // 4,800 (padded to 4,808) + 4,200 (200 remainder, unpadded)
    expect(sends.map((s) => s.length)).toEqual([4808, 4200]);
    const rebuilt = new Uint8Array(pcm.length);
    let o = 0;
    for (const s of sends) {
      const take = Math.min(MAX_MONO_BYTES_PER_TRANSMISSION, pcm.length - o);
      rebuilt.set(s.subarray(0, take), o);
      o += take;
      // everything the pad added must be silence
      for (let i = take; i < s.length; i++) expect(s[i]).toBe(0);
    }
    expect(Array.from(rebuilt)).toEqual(Array.from(pcm));
  });
});

describe('lengthHeader', () => {
  it('is a little-endian uint32', () => {
    expect(Array.from(lengthHeader(0x12345678))).toEqual([0x78, 0x56, 0x34, 0x12]);
  });
});

describe('ulawToPcm16', () => {
  it('decodes G.711 mu-law reference points', () => {
    // 0xFF is the canonical silence code; 0x80/0x00 are full scale with the
    // sign convention the backend's verified codec (routers/phone_agent.py)
    // uses: invert first, sign = u & 0x80.
    const dec = (b: number) => new Int16Array(ulawToPcm16(new Uint8Array([b])).buffer)[0];
    expect(dec(0xff)).toBe(0);
    expect(dec(0x80)).toBe(32124);
    expect(dec(0x00)).toBe(-32124);
  });

  it('doubles the byte count', () => {
    expect(ulawToPcm16(new Uint8Array(400)).length).toBe(800);
  });
});

describe('makeTonePcm', () => {
  it('renders the device sample rate as int16 LE', () => {
    const tone = makeTonePcm(440, 100);
    expect(tone.length).toBe((8000 * 100 * 2) / 1000); // 100 ms at 8 kHz, 2 bytes per sample
    const peak = Math.max(...Array.from(new Int16Array(tone.buffer)));
    expect(peak).toBeLessThanOrEqual(32767);
    expect(peak).toBeGreaterThan(0);
  });
});

describe('looksLikeMp3', () => {
  it('detects ID3 and frame-sync headers', () => {
    expect(looksLikeMp3(new Uint8Array([0x49, 0x44, 0x33, 0x04]))).toBe(true);
    expect(looksLikeMp3(new Uint8Array([0xff, 0xfb, 0x90, 0x00]))).toBe(true);
  });

  it('leaves mu-law alone when it is not a frame header', () => {
    expect(looksLikeMp3(new Uint8Array([0x00, 0x00, 0x00]))).toBe(false);
    expect(looksLikeMp3(new Uint8Array([]))).toBe(false);
  });
});

/** Scripted fake: notifies before completing each write, exactly like the handler. */
function fakeIo(opts: { mtu?: number; stall?: boolean } = {}): SpeakerIo & { writes: Uint8Array[] } {
  const io = {
    writes: [] as Uint8Array[],
    pumps: null as null | (() => void),
    async ensureMtu() {
      return opts.mtu ?? 517;
    },
    write(bytes: Uint8Array) {
      io.writes.push(bytes);
      if (!opts.stall) {
        const pump = io.pumps;
        // notify-before-process ordering, as in audio_data_write_handler
        queueMicrotask(() => pump?.());
      }
      return Promise.resolve();
    },
    subscribe(onPump: () => void) {
      io.pumps = onPump;
      return () => {
        io.pumps = null;
      };
    },
  };
  return io as unknown as SpeakerIo & { writes: Uint8Array[] };
}

describe('playPcm16Mono8k', () => {
  it('writes the header, then pump-paced 400-byte packets with a short final one', async () => {
    const io = fakeIo();
    const pcm = new Uint8Array(1000);
    await playPcm16Mono8k(pcm, { io });

    // 1,000 % 400 == 200: no padding. Header first: little-endian uint32 of
    // 1000 = 0x03E8 -> [0xE8, 0x03, 0, 0].
    expect(Array.from(io.writes[0]!)).toEqual([0xe8, 0x03, 0, 0]);
    const chunks = io.writes.slice(1).map((w) => w.length);
    expect(chunks).toEqual([PACKET_SIZE, PACKET_SIZE, 200]);
  });

  it('chunks every transmission as full 400s plus a playable remainder', async () => {
    const u32le = (b: Uint8Array) => new DataView(b.buffer, b.byteOffset).getUint32(0, true);
    for (const total of [400, 800, 4804, 10_000]) {
      const io = fakeIo();
      await playPcm16Mono8k(new Uint8Array(total), { io });
      // Split the recorded writes into sends: a 4-byte write is a length header.
      const sends: number[][] = [];
      for (const w of io.writes) {
        if (w.length === 4) sends.push([u32le(w)]);
        else sends[sends.length - 1]!.push(w.length);
      }
      expect(sends.length).toBeGreaterThan(0);
      for (const [declared, ...chunkSizes] of sends) {
        const last = chunkSizes[chunkSizes.length - 1]!;
        // speak() plays on the `< 400` branch: full-size packets must never be
        // last (old-firmware stall), and a 4-byte last packet reads as a header.
        expect(last).toBeLessThan(PACKET_SIZE);
        expect(last % PACKET_SIZE).not.toBe(4);
        for (const c of chunkSizes.slice(0, -1)) expect(c).toBe(PACKET_SIZE);
        const sum = chunkSizes.reduce((a, b) => a + b, 0);
        expect(sum).toBe(declared); // header accounts match the bytes sent
      }
    }
  });

  it('splits over-cap audio into multiple transmissions', async () => {
    const io = fakeIo();
    await playPcm16Mono8k(new Uint8Array(MAX_MONO_BYTES_PER_TRANSMISSION + 10), { io });
    const headers = io.writes.filter((w) => w.length === 4);
    expect(headers.length).toBe(2);
  });

  it('refuses a negotiated MTU that would fragment packets', async () => {
    const io = fakeIo({ mtu: 23 });
    await expect(playPcm16Mono8k(new Uint8Array(4), { io })).rejects.toThrow(/MTU 23/);
    expect(io.writes.length).toBe(0);
  });

  it('gives up when the device stops pumping', async () => {
    const io = fakeIo({ stall: true });
    await expect(playPcm16Mono8k(new Uint8Array(10), { io, pumpTimeoutMs: 30 })).rejects.toThrow(
      /no pump notification/
    );
  });

  it('rejects a mid-byte sample boundary', async () => {
    await expect(playPcm16Mono8k(new Uint8Array(401), { io: fakeIo() })).rejects.toThrow(/int16/);
  });
});

describe('firmwareSupportsStreaming', () => {
  it('accepts the scheduler from the release that ships it', () => {
    expect(firmwareSupportsStreaming('2.0.11')).toBe(true);
    expect(firmwareSupportsStreaming('2.1.0')).toBe(true);
    expect(firmwareSupportsStreaming('3.0.0')).toBe(true);
    // lab builds of the PR firmware are tagged 2.0.9x and sort above 2.0.11
    expect(firmwareSupportsStreaming('2.0.95')).toBe(true);
  });

  it('rejects burst-only firmware, comparing numbers not characters', () => {
    expect(firmwareSupportsStreaming('2.0.10')).toBe(false);
    expect(firmwareSupportsStreaming('2.0.9')).toBe(false); // lexically > '2.0.11'
    expect(firmwareSupportsStreaming('1.9.9')).toBe(false);
  });

  it('rejects unreadable revisions', () => {
    expect(firmwareSupportsStreaming(null)).toBe(false);
    expect(firmwareSupportsStreaming(undefined)).toBe(false);
    expect(firmwareSupportsStreaming('')).toBe(false);
    expect(firmwareSupportsStreaming('Seeed Studio XIAO')).toBe(false);
  });
});

describe('planTransmissions custom cap', () => {
  it('slices at the raised streaming cap, padding only where speak() demands it', () => {
    const cap = MAX_STREAMING_MONO_BYTES_PER_TRANSMISSION;
    const sends = planTransmissions(new Uint8Array(cap + 10), cap);
    expect(sends.length).toBe(2);
    expect(sends[0]!.length).toBe(cap + 8); // cap % 400 == 0 -> stall escape padding
    expect(sends[1]!.length).toBe(10); // ambiguous-free tail stays bare
  });

  it('defaults to the release-firmware clip', () => {
    const sends = planTransmissions(new Uint8Array(MAX_MONO_BYTES_PER_TRANSMISSION + 10));
    expect(sends.length).toBe(2);
    expect(sends[0]!.length).toBe(MAX_MONO_BYTES_PER_TRANSMISSION + 8);
  });
});

describe('splitSpeechChunks', () => {
  const cap = MAX_STREAMING_MONO_BYTES_PER_TRANSMISSION;

  it('leaves text that fits one stream alone', () => {
    expect(splitSpeechChunks('hello there friend', cap)).toEqual(['hello there friend']);
  });

  it('cuts overflowing replies without losing words', () => {
    const text =
      'The first sentence is quite long and keeps going for a while. ' +
      'The second one is just as long and continues to ramble onward.';
    const chunks = splitSpeechChunks(text, cap);
    expect(chunks.length).toBeGreaterThan(1);
    expect(chunks.join(' ').split(/\s+/).length).toBe(text.split(/\s+/).length);
  });

  it('prefers comma clauses over cutting sentences apart', () => {
    const text = 'alpha beta gamma delta, epsilon zeta eta theta, iota kappa lambda mu';
    const chunks = splitSpeechChunks(text, cap);
    expect(chunks).toEqual([
      'alpha beta gamma delta,',
      'epsilon zeta eta theta,',
      'iota kappa lambda mu',
    ]);
  });

  it('keeps every chunk inside the stream word budget', () => {
    const text = Array.from({ length: 40 }, (_, i) => `word${i}`).join(' ');
    const budget = Math.floor(cap / 5600); // measured bytes-per-word of this TTS path
    for (const chunk of splitSpeechChunks(text, cap)) {
      expect(chunk.split(/\s+/).filter(Boolean).length).toBeLessThanOrEqual(budget);
    }
  });
});

describe('playPcm16Mono8k streaming cap', () => {
  it('sends one continuous stream per chunk below the raised cap', async () => {
    const io = fakeIo();
    await playPcm16Mono8k(new Uint8Array(29_000), {
      io,
      maxMonoBytesPerTransmission: MAX_STREAMING_MONO_BYTES_PER_TRANSMISSION,
    });
    expect(io.writes.filter((w) => w.length === 4).length).toBe(1);
    const body = io.writes.filter((w) => w.length !== 4).reduce((a, w) => a + w.length, 0);
    expect(body).toBe(29_000);
  });

  it('still respects the default clip cap when no cap is passed', async () => {
    const io = fakeIo();
    await playPcm16Mono8k(new Uint8Array(29_000), { io });
    expect(io.writes.filter((w) => w.length === 4).length).toBe(7); // ceil(29000/4800)
  });
});
