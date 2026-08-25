import { describe, it, expect } from 'vitest'
import { BleAudioProcessor, MAX_CONSECUTIVE_DECODE_FAILURES } from './bleAudioProcessor'

/** Packet framing: [u16 index LE, u8 frameId, ...content]. */
const packet = (index: number, frameId: number, content: number[]): Uint8Array =>
  Uint8Array.from([index & 0xff, (index >> 8) & 0xff, frameId, ...content])

const collector = (): {
  pcm: Int16Array[]
  degraded: boolean[]
  delegate: ConstructorParameters<typeof BleAudioProcessor>[0]['delegate']
} => {
  const pcm: Int16Array[] = []
  const degraded: boolean[] = []
  return {
    pcm,
    degraded,
    delegate: {
      onPcm: (p) => pcm.push(p),
      onDegradedChange: (isDegraded) => degraded.push(isDegraded)
    }
  }
}

describe('BleAudioProcessor packet reassembly (Omi)', () => {
  it('joins packets until the codec frame length is reached, then decodes', () => {
    const sink = collector()
    // pcm8 decodes one sample per byte, so the PCM length reveals the exact
    // frame the reassembler handed the decoder.
    const processor = new BleAudioProcessor({ codec: 'pcm8', delegate: sink.delegate })
    processor.processAudioData(packet(1, 0, new Array(40).fill(128)))
    expect(sink.pcm.length).toBe(0)
    processor.processAudioData(packet(2, 1, new Array(40).fill(128)))
    expect(sink.pcm.length).toBe(1)
    expect(sink.pcm[0].length).toBe(80)
  })

  it('counts lost packets and drops the frame in progress', () => {
    const sink = collector()
    const processor = new BleAudioProcessor({ codec: 'pcm8', delegate: sink.delegate })
    processor.processAudioData(packet(1, 0, new Array(40).fill(128)))
    // Packet 2 never arrives.
    processor.processAudioData(packet(3, 1, new Array(40).fill(128)))
    expect(processor.snapshot.lostPackets).toBe(1)
    expect(sink.pcm.length).toBe(0)
  })

  it('ignores implausible index jumps without counting them as loss', () => {
    const sink = collector()
    const processor = new BleAudioProcessor({ codec: 'pcm8', delegate: sink.delegate })
    processor.processAudioData(packet(1, 0, new Array(10).fill(128)))
    processor.processAudioData(packet(5000, 0, new Array(80).fill(128)))
    expect(processor.snapshot.lostPackets).toBe(0)
    expect(sink.pcm.length).toBe(1)
  })

  it('a frameId that does not follow the last one resets the pending frame', () => {
    const sink = collector()
    const processor = new BleAudioProcessor({ codec: 'pcm8', delegate: sink.delegate })
    processor.processAudioData(packet(1, 0, new Array(40).fill(128)))
    processor.processAudioData(packet(2, 5, new Array(40).fill(128)))
    expect(sink.pcm.length).toBe(0)
    // A fresh frame 0 starts cleanly afterwards.
    processor.processAudioData(packet(3, 0, new Array(80).fill(128)))
    expect(sink.pcm.length).toBe(1)
  })

  it('frameId 0 flushes whatever was pending before starting the next frame', () => {
    const sink = collector()
    const processor = new BleAudioProcessor({ codec: 'pcm8', delegate: sink.delegate })
    processor.processAudioData(packet(1, 0, new Array(30).fill(128)))
    processor.processAudioData(packet(2, 0, new Array(80).fill(128)))
    // The 30-byte partial is flushed, then the 80-byte frame completes.
    expect(sink.pcm.map((p) => p.length)).toEqual([30, 80])
  })

  it('drops packets shorter than the 3-byte header without disturbing the stream', () => {
    const sink = collector()
    const processor = new BleAudioProcessor({ codec: 'pcm8', delegate: sink.delegate })
    processor.processAudioData(packet(1, 0, new Array(40).fill(128)))
    // A runt carrying a far-away index must not be read as a packet at all;
    // treating it as one would poison index tracking and drop the frame.
    processor.processAudioData(Uint8Array.from([9, 0]))
    processor.processAudioData(packet(2, 1, new Array(40).fill(128)))
    expect(sink.pcm.length).toBe(1)
    expect(sink.pcm[0].length).toBe(80)
    expect(processor.snapshot.decodeFailures).toBe(0)
    expect(processor.snapshot.lostPackets).toBe(0)
  })
})

describe('BleAudioProcessor framed slicing', () => {
  it('slices opusFS320 input every 40 bytes and drops a partial tail', () => {
    const sink = collector()
    const processor = new BleAudioProcessor({ codec: 'opusFS320', delegate: sink.delegate })
    // The Opus decoder is not ready in this synchronous test, so decodes miss;
    // the failure count is the count of slices handed to the decoder.
    processor.processAudioData(new Uint8Array(90))
    expect(processor.snapshot.decodeFailures).toBe(2)
  })

  it('slices lc3 input every 30 bytes into real silence frames', () => {
    const sink = collector()
    const processor = new BleAudioProcessor({ codec: 'lc3FS1030', delegate: sink.delegate })
    processor.processAudioData(new Uint8Array(95))
    expect(sink.pcm.length).toBe(3)
    expect(sink.pcm.every((p) => p.length === 160)).toBe(true)
  })
})

describe('BleAudioProcessor degradation ladder', () => {
  it('flags degraded at exactly ten consecutive failures and clears on recovery', () => {
    const sink = collector()
    const processor = new BleAudioProcessor({ codec: 'lc3FS1030', delegate: sink.delegate })
    // Zero-length frames fail; the LC3 decoder only rejects empty input.
    for (let i = 0; i < MAX_CONSECUTIVE_DECODE_FAILURES - 1; i += 1) {
      processor.processFrame(new Uint8Array(0))
    }
    expect(sink.degraded).toEqual([])
    expect(processor.isDegraded).toBe(false)

    processor.processFrame(new Uint8Array(0))
    expect(sink.degraded).toEqual([true])
    expect(processor.isDegraded).toBe(true)

    // Further failures do not re-fire the flag.
    processor.processFrame(new Uint8Array(0))
    expect(sink.degraded).toEqual([true])

    processor.processFrame(new Uint8Array(30))
    expect(sink.degraded).toEqual([true, false])
    expect(processor.isDegraded).toBe(false)
    expect(processor.snapshot.decodeFailures).toBe(11)
    expect(processor.snapshot.framesProcessed).toBe(1)
  })

  it('a success inside the ladder restarts the count', () => {
    const sink = collector()
    const processor = new BleAudioProcessor({ codec: 'lc3FS1030', delegate: sink.delegate })
    for (let i = 0; i < 9; i += 1) processor.processFrame(new Uint8Array(0))
    processor.processFrame(new Uint8Array(30))
    for (let i = 0; i < 9; i += 1) processor.processFrame(new Uint8Array(0))
    expect(processor.isDegraded).toBe(false)
  })

  it('reports no decoder for an unknown codec instead of throwing', () => {
    const sink = collector()
    const processor = new BleAudioProcessor({ codec: 'unknown', delegate: sink.delegate })
    expect(processor.hasDecoder).toBe(false)
    processor.processFrame(new Uint8Array(10))
    expect(processor.snapshot.decodeFailures).toBe(1)
  })
})

describe('BleAudioProcessor stats and reset', () => {
  it('tracks bytes and frames, and reset clears the packet state', () => {
    const sink = collector()
    const processor = new BleAudioProcessor({ codec: 'pcm8', delegate: sink.delegate })
    processor.processAudioData(packet(1, 0, new Array(80).fill(128)))
    expect(processor.snapshot.framesProcessed).toBe(1)
    expect(processor.snapshot.bytesProcessed).toBe(83)

    processor.processAudioData(packet(2, 0, new Array(40).fill(128)))
    processor.reset()
    // After a reset the half-built frame is gone and index tracking restarts,
    // so a distant index is not counted as loss.
    processor.processAudioData(packet(900, 0, new Array(80).fill(128)))
    expect(processor.snapshot.lostPackets).toBe(0)
    expect(processor.snapshot.framesProcessed).toBe(2)
  })
})
