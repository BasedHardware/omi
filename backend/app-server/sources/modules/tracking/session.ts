import { inTx } from "../storage/inTx";
import { fetchRepeatKey, saveRepeatKey } from "../storage/repeatKey";
import { pushUpdate } from "../updates/updates";

export async function startSession(uid: string, tid: string, repeatKey: string, timeout_s: number) {
    return await inTx(async (tx) => {

        // Check if session already exists
        let repeatKeyValue = 'session-create-' + uid + '-' + repeatKey;
        let repeat = await fetchRepeatKey(tx, repeatKeyValue);
        if (repeat) {
            return await tx.trackingSession.findUniqueOrThrow({ where: { id: repeat, userId: uid } });
        }

        // Find max session index using aggregate
        let maxIndex = await tx.trackingSession.aggregate({
            where: {
                userId: uid
            },
            _max: {
                index: true
            }
        });
        let nextId = 0;
        if (maxIndex._max.index !== null) {
            nextId = maxIndex._max.index + 1;
        }

        // Create session
        let session = await tx.trackingSession.create({
            data: {
                index: nextId,
                userId: uid,
                state: 'STARTING',
                expiresAt: new Date(Date.now() + timeout_s * 1000),
            }
        });

        // Save repeat key
        await saveRepeatKey(tx, repeatKeyValue, session.id);

        // Notify
        await pushUpdate(tx, uid, {
            type: 'session-created',
            id: session.id,
            index: session.index,
            created: session.createdAt.getTime()
        });

        // Return session
        return session;
    });
}

export async function stopSession(uid: string, session: string) {
    return await inTx(async (tx) => {

        // If session does not exist, return false
        let trackingSession = await tx.trackingSession.findUnique({ where: { id: session, userId: uid } });
        if (!trackingSession) {
            return false;
        }

        // Already stopped
        if (trackingSession.state === 'FINISHED' || trackingSession.state === 'PROCESSING' || trackingSession.state === 'CANCELED') {
            return false;
        }

        // Check if session has something to process
        let hasData = !!(await tx.trackingAudioChunk.findFirst({ where: { sessionId: session } }));

        // Update session state
        if (hasData) {

            // If has data, set to processing
            await tx.trackingSession.update({
                where: { id: session },
                data: {
                    state: 'PROCESSING',
                }
            });

            // Notify
            await pushUpdate(tx, uid, {
                type: 'session-updated',
                id: session,
                state: 'processing'
            });

        } else {

            // If no data, set to canceled
            await tx.trackingSession.update({
                where: { id: session },
                data: {
                    state: 'CANCELED'
                }
            });

            // Notify
            await pushUpdate(tx, uid, {
                type: 'session-updated',
                id: session,
                state: 'canceled'
            });
        }

        // Return success
        return true;
    });
}

export async function listSessions(uid: string, after: string | null) {
    return await inTx(async (tx) => {
        let sessions = await tx.trackingSession.findMany({
            where: {
                userId: uid,
                index: after ? { gt: parseInt(after) } : undefined
            },
            orderBy: [{
                index: 'desc'
            }],
            take: 21
        });

        // Resolve next cursor
        let next: string | null = null;
        if (sessions.length === 21) {
            next = sessions[20].index.toString();
        }

        // Return sessions
        return {
            sessions,
            next
        };
    });
}

export async function getSession(uid: string, id: string) {
    return await inTx(async (tx) => {
        return await tx.trackingSession.findFirstOrThrow({
            where: {
                userId: uid,
                id: id
            }
        });
    });
}

export async function expireSessions() {
    return await inTx(async (tx) => {
        let sessions = await tx.trackingSession.findMany({
            where: {
                expiresAt: {
                    lte: new Date()
                },
                state: {
                    in: ['STARTING']
                }
            }
        });
        for (let session of sessions) {

            // Check if session has something to process
            let hasData = !!(await tx.trackingAudioChunk.findFirst({ where: { sessionId: session.id } }));

            // Update session state
            if (hasData) {
                // If has data, set to processing
                await tx.trackingSession.update({
                    where: { id: session.id },
                    data: {
                        state: 'PROCESSING',
                    }
                });

                // Notify
                await pushUpdate(tx, session.userId, {
                    type: 'session-updated',
                    id: session.id,
                    state: 'processing'
                });
            } else {

                // If no data, set to canceled
                await tx.trackingSession.update({
                    where: { id: session.id },
                    data: {
                        state: 'CANCELED'
                    }
                });

                // Notify
                await pushUpdate(tx, session.userId, {
                    type: 'session-updated',
                    id: session.id,
                    state: 'canceled'
                });
            }
        }

        return sessions.length;
    });
}