import { delay } from "../../utils/time";
import { runInLock } from "../lock/runInLock";
import { s3bucket, s3client } from "../storage/files";
import { inTx } from "../storage/inTx";
import { pushUpdate } from "../updates/updates";
import { whisper } from "./inference";

export async function startAgentWorker() {
    runInLock('transc-worker', async (refresh) => {

        // Read pending tracking sessions
        const pending = await inTx(async (tx) => {
            return await tx.trackingSession.findFirst({
                where: {
                    state: 'PROCESSING',
                    audioFile: { not: null },
                    transcription: null
                }
            });
        });
        if (!pending) {
            await delay(5000);
            return;
        }

        // Prepare audio url
        let presignedUrl = await s3client.presignedGetObject(s3bucket, pending.audioFile!); // By default expires in 7 days

        // Call whisper
        let output = await whisper(presignedUrl);
        if (!output) {
            output = '';
        }
        console.warn('Transcription:', output);

        // Update transcription
        await inTx(async (tx) => {

            // Update session
            await tx.trackingSession.update({
                where: {
                    id: pending.id
                },
                data: {
                    transcription: output,
                    state: 'FINISHED' // Mark as finished
                }
            });

            // Push update about transcription
            let session = await tx.trackingSession.findUniqueOrThrow({
                where: {
                    id: pending.id
                }
            });
            await pushUpdate(tx, session.userId, {
                type: 'session-transcribed',
                id: session.id,
                transcription: output!
            });
            await pushUpdate(tx, session.userId, {
                type: 'session-updated',
                id: session.id,
                state: 'finished'
            });
        });

        // Delay for a while
        await delay(100);
    });
}