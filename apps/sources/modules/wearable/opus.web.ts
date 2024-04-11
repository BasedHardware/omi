import { OpusDecoder } from 'opus-decoder';
import { WaveFile } from 'wavefile';

export async function decodeOpus(frames: Uint8Array[]): Promise<WaveFile | null> {

    // Load decoder
    const decoder = new OpusDecoder();
    await decoder.ready;

    // Decode frames
    let output = decoder.decodeFrames(frames);

    // Create wav
    const wav = new WaveFile();
    wav.fromScratch(1, output.sampleRate, '32f', output.channelData[0]);

    return wav;
}