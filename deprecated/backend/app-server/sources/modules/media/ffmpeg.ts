import * as tmp from 'tmp';
import * as fs from 'fs';
import ffmpeg from 'fluent-ffmpeg';
import { log } from '../../utils/log';

export async function combine(files: (string | { source: Buffer, ext: string })[], to: string) {

    // Prepare inputs
    let start = Date.now();
    let pending: (() => void)[] = [];
    try {

        // Prepare inputs
        let inputs: string[] = [];
        for (let i in files) {
            let input = files[i];
            if (typeof input === 'string') {
                inputs[i] = input;
            } else {
                let temp = tmp.fileSync({ postfix: input.ext });
                fs.writeFileSync(temp.name, input.source);
                inputs[i] = temp.name;
                pending.push(temp.removeCallback);
            }
        }

        // Prepare outputs
        const command = ffmpeg();
        for (let chunk of inputs) {
            console.warn(chunk);
            command.input(chunk);
        }
        command
            .outputFormat('mp4')
            .audioCodec('aac')
            .audioChannels(1)
            .audioBitrate(128)

        // Convert
        let tmpDir = tmp.dirSync();
        pending.push(tmpDir.removeCallback);
        await new Promise((resolve, reject) => {
            command
                .on('end', () => { resolve(undefined); })
                .on('error', (err) => { reject(err); })
                .mergeToFile(to, tmpDir.name);
        });
    } finally {
        for (let p of pending) {
            p();
        }
        log('Converted in ' + (Date.now() - start) + 'ms, files: ' + files.length);
    }
}

export async function metadata(file: string): Promise<{ duration: number, size: number }> {
    return new Promise((resolve, reject) => {
        ffmpeg.ffprobe(file, (err, metadata) => {
            if (err) {
                reject(err);
            } else {
                resolve({ duration: metadata.format.duration!, size: metadata.format.size! });
            }
        });
    });
}