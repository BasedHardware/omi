import { WaveFile } from "wavefile";
import { CodecType } from "./protocol";
import { decodeOpus } from "./opus";

export async function decode(codec: CodecType, frames: Uint8Array[]) {
    console.warn(frames);
    if (codec === 'pcm-16' || codec === 'pcm-8') {
        const totalLength = frames.reduce((sum, frame) => sum + frame.length, 0);
        const samples = new Int16Array(totalLength / 2);
        let sampleIndex = 0;
        for (let i = 0; i < frames.length; i++) {
            for (let j = 0; j < frames[i].length; j += 2) {
                const byte1 = frames[i][j];
                const byte2 = frames[i][j + 1];
                const sample = (byte2 << 8) | byte1;
                samples[sampleIndex++] = sample;
            }
        }
        if (codec === 'pcm-16') {
            const wav = new WaveFile();
            wav.fromScratch(1, 16000, '16', samples);
            return wav;
        } else {
            const wav = new WaveFile();
            wav.fromScratch(1, 8000, '16', samples);
            return wav;
        }
    }
    if (codec === 'mu-law-16' || codec === 'mu-law-8') {
        const totalLength = frames.reduce((sum, frame) => sum + frame.length, 0);
        const samples = new Uint8Array(totalLength);
        let sampleIndex = 0;
        for (let i = 0; i < frames.length; i++) {
            for (let j = 0; j < frames[i].length; j++) {
                samples[sampleIndex++] = frames[i][j];
            }
        }

        if (codec === 'mu-law-16') {
            const wav = new WaveFile();
            wav.fromScratch(1, 16000, '8m', samples);
            wav.fromMuLaw();
            return wav;
        } else {
            const wav = new WaveFile();
            wav.fromScratch(1, 8000, '8m', samples);
            wav.fromMuLaw();
            return wav;
        }
    }
    if (codec === 'opus') {
        return decodeOpus(frames);
    }
    return null;
}