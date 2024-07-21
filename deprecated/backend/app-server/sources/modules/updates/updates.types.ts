//
// NOTE: This updates are delivered directly to the client.
//

export type UpdateSessionCreated = {
    type: 'session-created'
    id: string;
    index: number;
    created: number;
};

export type UpdateSessionState = {
    type: 'session-updated'
    id: string;
    state: 'starting' | 'in-progress' | 'processing' | 'finished' | 'canceled';
};

export type UpdateSessionAudio = {
    type: 'session-audio-updated'
    id: string;
    audio: {
        duration: number,
        size: number
    }
};

export type UpdateSessionTranscribed = {
    type: 'session-transcribed'
    id: string;
    transcription: string;
};

export type UpdateType = UpdateSessionCreated | UpdateSessionState | UpdateSessionAudio | UpdateSessionTranscribed;