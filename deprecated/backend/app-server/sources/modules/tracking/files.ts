import { inTx } from "../storage/inTx";
import { fetchRepeatKey } from "../storage/repeatKey";
import { pushUpdate } from "../updates/updates";

export function uploadAudioChunk(uid: string, session: string, repeatKey: string, format: string, chunks: Buffer[]) {
    return inTx(async (tx) => {

        // Check if session exists
        let trackingSession = await tx.trackingSession.findUnique({ where: { id: session } });
        if (!trackingSession) {
            return false;
        }

        // Check if user is owner of session
        if (trackingSession.userId !== uid) {
            return false;
        }

        // Check if session is in progress
        if (trackingSession.state !== 'IN_PROGRESS' && trackingSession.state !== 'STARTING') {
            return false;
        }

        // Check if repeat key matches
        let repeatKeyValue = 'session-audio-upload-' + session + '-' + repeatKey;
        let repeat = await fetchRepeatKey(tx, repeatKeyValue);
        if (repeat) {
            return true;
        }

        // Save audio chunks
        let last = await tx.trackingAudioChunk.aggregate({
            where: {
                sessionId: session,
            },
            _max: {
                index: true
            }
        });
        let nextIndex = 0;
        if (last._max.index !== null) {
            nextIndex = last._max.index + 1;
        }
        for (let i = 0; i < chunks.length; i++) {
            await tx.trackingAudioChunk.create({
                data: {
                    sessionId: session,
                    index: nextIndex + i,
                    format,
                    data: chunks[i]
                }
            });
        }

        // Update state on first chunk
        if (trackingSession.state === 'STARTING') {
            
            // Update state
            await tx.trackingSession.update({
                where: { id: session },
                data: {
                    state: 'IN_PROGRESS'
                }
            });

            // Notify
            await pushUpdate(tx, uid, {
                type: 'session-updated',
                id: session,
                state: 'in-progress',
            });
        }

        // Save repeat key
        return true;
    });
}