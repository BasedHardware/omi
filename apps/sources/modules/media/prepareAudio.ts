import { WaveFile } from 'wavefile';
import { Worklets } from 'react-native-worklets-core';

export function prepareAudio(format: 'opus' | 'pcm-16' | 'pcm-8' | 'mulaw-16' | 'mulaw-8', frames: Uint8Array[]) {
    'worklet';

    // PCM
    if (format === 'pcm-8' || format === 'pcm-16') {

        // Combine all frames
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

        // Create WavFile
        let wav: WaveFile;
        if (format === 'pcm-16') {
            wav = new WaveFile();
            wav.fromScratch(1, 16000, '16', samples);

        } else {
            wav = new WaveFile();
            wav.fromScratch(1, 8000, '16', samples);
        }
        let output = wav.toBuffer();

        return { format: 'wav', data: output };
    }

    // MuLaw
    if (format === 'mulaw-8' || format === 'mulaw-16') {

        // Combine all frames
        const totalLength = frames.reduce((sum, frame) => sum + frame.length, 0);
        const samples = new Uint8Array(totalLength);
        let sampleIndex = 0;
        for (let i = 0; i < frames.length; i++) {
            for (let j = 0; j < frames[i].length; j++) {
                samples[sampleIndex++] = frames[i][j];
            }
        }

        // Create WavFile
        let wav: WaveFile;
        if (format === 'mulaw-16') {
            wav = new WaveFile();
            wav.fromScratch(1, 16000, '8m', samples);
            wav.fromMuLaw();
        } else {
            wav = new WaveFile();
            wav.fromScratch(1, 8000, '8m', samples);
            wav.fromMuLaw();
        }
        let output = wav.toBuffer();

        // Output
        return { format: 'wav', data: output };
    }

    // Opus
    if (format === 'opus') {
        const totalLength = frames.reduce((sum, frame) => sum + frame.length, 0) + frames.length * 2;
        const samples = new Uint8Array(totalLength);
        let sampleIndex = 0;
        for (let i = 0; i < frames.length; i++) {
            samples[sampleIndex++] = frames[i].length & 0xFF;
            samples[sampleIndex++] = (frames[i].length >> 8) & 0xFF;
            for (let j = 0; j < frames[i].length; j++) {
                samples[sampleIndex++] = frames[i][j];
            }
        }

        return { format: 'opus-frames', data: samples };
    }

    throw new Error('Unsupported format');
}

export const prepareAudioAsync = Worklets.createRunInContextFn(prepareAudio);