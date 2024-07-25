import { delay } from "../../utils/time";
import { runInLock } from "../lock/runInLock";
import { inTx } from "../storage/inTx";
import * as tmp from 'tmp';
import { log } from "../../utils/log";
import { combine, metadata } from "../media/ffmpeg";
import { s3bucket, s3client } from "../storage/files";
import { randomUUID } from "crypto";
import { pushUpdate } from "../updates/updates";

export async function startCombineWorker() {
    runInLock('combine-worker', async (refresh) => {

        // Read pending tracking sessions
        const chunks = await inTx(async (tx) => {
            let pending = await tx.trackingSession.findFirst({
                where: {
                    state: 'PROCESSING',
                    audioFile: null
                }
            });

            if (pending) {
                let ch = await tx.trackingAudioChunk.findMany({
                    where: {
                        sessionId: pending.id
                    }
                });
                return { chunks: ch, session: pending.id };
            } else {
                return null;
            }
        });
        if (!chunks) {
            await delay(5000);
            return;
        }

        // Refresh lock
        if (!await refresh()) {
            return; // Lost lock
        }

        // Combine
        let id = randomUUID();
        let key = `sessions/${id}.m4a`;
        let meta: { duration: number, size: number };
        const outputObj = tmp.fileSync({ postfix: '.m4a' });
        try {

            log('Converting chunks into file...');
            await combine(chunks.chunks.map((c) => ({ source: c.data, ext: c.format === 'aac' ? '.m4a' : 'wav' })), outputObj.name);
            log('Converted successfuly to ' + outputObj.name);

            // Refresh lock
            if (!await refresh()) {
                return; // Lost lock
            }

            // Upload
            log('Uploading to ' + key);
            await s3client.fPutObject(s3bucket, key, outputObj.name);
            log('Uploaded successfuly to ' + key);

            // Load meta
            meta = await metadata(outputObj.name);

            // Refresh lock
            if (!await refresh()) {
                return; // Lost lock
            }

        } finally {
            outputObj.removeCallback();
        }

        //
        // Update session
        //

        await inTx(async (tx) => {

            // Update session
            await tx.trackingSession.update({
                where: {
                    id: chunks.session
                },
                data: {
                    audioFile: key,
                    audioDuration: meta.duration * 1000, // ms
                    audioSize: meta.size,
                }
            });

            // Push update
            let session = await tx.trackingSession.findUniqueOrThrow({
                where: {
                    id: chunks.session
                }
            });
            await pushUpdate(tx, session.userId, {
                type: 'session-audio-updated',
                id: session.id,
                audio: {
                    duration: meta.duration * 1000, // ms
                    size: meta.size
                }
            });
        });

    }, { lockTimeout: 60000, lockDelay: 5000 }); // Lock timeout 60s
}