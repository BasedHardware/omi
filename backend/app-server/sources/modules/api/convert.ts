import { SessionState, TrackingSession } from "@prisma/client";

export function sessionToAPI(session: TrackingSession) {
    return {
        id: session.id,
        index: session.index,
        created: session.createdAt.getTime(),
        audio: session.audioFile ? { duration: session.audioDuration, size: session.audioSize } : null,
        state: sessionStateToAPI(session.state)
    };
}

export function sessionToFullAPI(session: TrackingSession) {
    return {
        ...sessionToAPI(session),
        text: session.transcription,
    }
}

export function sessionStateToAPI(state: SessionState) {
    switch (state) {
        case 'STARTING': return 'starting';
        case 'PROCESSING': return 'processing';
        case 'FINISHED': return 'finished';
        case 'CANCELED': return 'canceled';
        case 'IN_PROGRESS': return 'in-progress';
    }
}