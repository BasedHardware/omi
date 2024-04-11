import { InvalidateSync } from "teslabot";
import { storage } from "../../storage";
import { SuperClient } from "../api/client";
import { backoff } from "../../utils/time";
import { fromByteArray } from 'react-native-quick-base64';
import { log } from "../../utils/logs";

export class SyncModel {
    readonly client: SuperClient;
    private localEnded = new Set<string>();
    private localSessions = new Map<string, string | null>();
    private pendingFrames = new Map<string, { index: number, format: string, data: Uint8Array }[]>();
    private readonly sync: InvalidateSync;

    constructor(client: SuperClient) {
        this.client = client;
        let stored = storage.getString('sync-sessions');
        if (stored) {
            console.warn(stored);
            let [keys, values] = JSON.parse(stored);
            for (let i = 0; i < keys.length; i++) {
                this.localSessions.set(keys[i], values[i]);
                this.localEnded.add(keys[i]);
            }
        }
        this.sync = new InvalidateSync(this.#doSync, { backoff });
        this.sync.invalidate();
    }

    syncNewSession(localId: string) {
        this.localSessions.set(localId, null); // No real ID yet
        this.#persistSessions();
        this.sync.invalidate();
        log('SYNC', 'Session started');
    }

    syncSessionEnded(localId: string) {
        if (!this.localSessions.has(localId)) { // Ignore if not started
            return;
        }
        this.localEnded.add(localId);
        log('SYNC', 'Session ended');
        this.sync.invalidate();
    }

    syncSessionFrame(localId: string, index: number, format: string, frame: Uint8Array) {
        if (!this.localSessions.has(localId)) { // Ignore if not started
            return;
        }
        if (this.localEnded.has(localId)) { // Ignore if already ended
            return;
        }
        let frames = this.pendingFrames.get(localId);
        if (!frames) {
            frames = [];
            this.pendingFrames.set(localId, frames);
        }
        frames.push({ index, format, data: frame });
        log('SYNC', 'Frame added');
        this.sync.invalidate();
    }

    #doSync = async () => {
        log('SYNC', 'Do sync');

        // First create all sessions
        let changed = false;
        for (let [localId, remoteId] of this.localSessions) {
            if (!remoteId) {
                log('SYNC', 'Starting session ' + localId);
                let session = await this.client.startSession(localId);
                log('SYNC', 'Assigned remote id ' + localId + ' -> ' + session.id);
                this.localSessions.set(localId, session.id);
                changed = true;
            }
        }
        if (changed) {
            this.#persistSessions();
        }

        // Upload all frames
        let uploaded = new Map<string, number>();
        let stopped = new Set<string>();
        for (let [localId, frames] of this.pendingFrames) {
            let copy = [...frames];
            let remoteId = this.localSessions.get(localId);
            if (!remoteId) {
                continue;
            }
            let count = 0;
            for (let c of copy) {
                let output = await this.client.uploadAudio(remoteId, 'id-' + c.index, c.format, [fromByteArray(c.data)]);
                if (!output.ok) {
                    console.error('Frame upload rejected', output);
                    stopped.add(localId);
                    break;
                } else {
                    count++;
                }
            }
            uploaded.set(localId, count);
        }
        for (let localId of stopped) {
            this.localEnded.add(localId);
        }
        for (let [localid, count] of uploaded) {
            let frames = this.pendingFrames.get(localid);
            if (frames) {
                if (frames.length === count) {
                    this.pendingFrames.delete(localid);
                } else {
                    this.pendingFrames.set(localid, frames.slice(count));
                }
            }
        }

        // Stop all sessions
        stopped.clear();
        for (let [localId, remoteId] of this.localSessions) {
            if (this.localEnded.has(localId) && remoteId) {
                log('SYNC', 'Stopping session ' + localId + '(' + remoteId + ')');
                await this.client.stopSession(remoteId);
                stopped.add(localId);
            }
        }
        if (stopped.size > 0) {
            for (let localId of stopped) {
                this.localSessions.delete(localId);
                this.localEnded.delete(localId);
                this.pendingFrames.delete(localId);
            }
            this.#persistSessions();
        }

        log('SYNC', 'Do sync end');
    }

    #persistSessions = () => {
        storage.set('sync-sessions', JSON.stringify([Array.from(this.localSessions.keys()), Array.from(this.localSessions.values())]));
    }
}