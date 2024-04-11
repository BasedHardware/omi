import { createStore } from "jotai";
import { SuperClient } from "../api/client";
import { SessionsModel } from "./SessionsModel";
import { WearableModel } from "./WearableModel";
import { Jotai } from "./_types";
import { UpdatesModel } from "./UpdatesModel";
import { Update } from "../api/schema";
import { CaptureModel } from "./CaptureModel";
import { SyncModel } from "./SyncModel";

export class AppModel {
    readonly client: SuperClient;
    readonly jotai: Jotai;
    readonly sessions: SessionsModel;
    readonly wearable: WearableModel;
    readonly updates: UpdatesModel;
    readonly sync: SyncModel;
    readonly capture: CaptureModel

    constructor(client: SuperClient) {
        this.client = client;
        this.jotai = createStore();
        this.sessions = new SessionsModel(client, this.jotai);
        this.wearable = new WearableModel(this.jotai);
        this.sync = new SyncModel(client);
        this.capture = new CaptureModel(this.sync, this.jotai, this.wearable);
        this.updates = new UpdatesModel(client);
        this.updates.onUpdates = this.#handleUpdate;
        this.wearable.onStreamingStart = this.capture.onCaptureStart;
        this.wearable.onStreamingStop = this.capture.onCaptureStop;
        this.wearable.onStreamingFrame = this.capture.onCaptureFrame;

        // Start
        this.updates.start();
        this.sessions.invalidate();
        this.wearable.start();
    }

    useSessions = () => {
        return this.sessions.use();
    }

    useWearable = () => {
        return this.wearable.use();
    }

    #handleUpdate = async (update: Update) => {
        console.warn(update);
        if (update.type === 'session-created') {
            this.sessions.apply({ id: update.id, index: update.index, state: 'starting', audio: null });
        } else if (update.type === 'session-updated') {
            this.sessions.applyPartial({ id: update.id, state: update.state });
        } else if (update.type === 'session-audio-updated') {
            this.sessions.applyPartial({ id: update.id, audio: update.audio });
        } else if (update.type === 'session-transcribed') {
            this.sessions.applyPartialFull({ id: update.id, text: update.transcription });
        }
    }
}