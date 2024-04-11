import { atom } from "jotai";
import { Jotai } from "./_types";
import { WearableModel } from "./WearableModel";
import { ProtocolDefinition } from "../wearable/protocol";
import { AsyncLock } from "teslabot";
import { randomKey } from "../crypto/randomKey";
import { SyncModel } from "./SyncModel";
import { prepareAudio } from "../media/prepareAudio";
import { compress } from "../../../modules/audio";
import { log } from "../../utils/logs";

export class CaptureModel {

    // Sync state
    readonly jotai: Jotai;
    readonly wearables: WearableModel;
    readonly captureState = atom<{ started: number, streaming: boolean } | null>(null);
    private started = false;

    // Async state
    private sync: SyncModel;
    private lastProtocol: ProtocolDefinition | null = null;
    private asyncLock = new AsyncLock();
    private asyncLocalId: string | null = null;

    constructor(sync: SyncModel, jotai: Jotai, wearables: WearableModel) {
        this.sync = sync;
        this.jotai = jotai;
        this.wearables = wearables;
    }

    start = () => {
        if (this.started) { // Ignore if already started
            return;
        }
        if (!this.wearables.device) { // Ignore if no device
            return;
        }
        this.started = true;
        this.wearables.device.startStreaming();
        this.jotai.set(this.captureState, { started: Date.now(), streaming: false });
        this.asyncLock.inLock(this.#handleStart);
    }

    stop = () => {
        if (!this.started) { // Ignore if not started
            return
        }
        this.started = false;
        this.wearables.device!.stopStreaming(); // Device can't became null
        this.jotai.set(this.captureState, null);
        this.asyncLock.inLock(this.#handleStop);
    }

    //
    // Capture Callbacks
    //

    onCaptureStart = (protocol: ProtocolDefinition) => {
        this.lastProtocol = protocol;
        if (!this.started) { // Ignore
            return;
        }
        this.started = true;
        console.warn('Start capture with codec ' + protocol.codec);

        // Update UI
        let ex = this.jotai.get(this.captureState);
        if (ex) {
            this.jotai.set(this.captureState, { started: ex.started, streaming: true });
        }
    }

    onCaptureFrame = (data: Uint8Array) => {
        if (!this.started) { // Ignore
            return;
        }
        const p = this.lastProtocol;
        if (p) {
            this.asyncLock.inLock(async () => { await this.#handleFrame(p, data); });
        }
    }

    onCaptureStop = () => {
        if (!this.started) { // Ignore
            return;
        }
        this.started = false;
        console.warn('Stop capture');

        // Update UI
        let ex = this.jotai.get(this.captureState);
        if (ex) {
            this.jotai.set(this.captureState, { started: ex.started, streaming: false });
        }
    }

    //
    // Handlers
    //

    #framesIndex = 0;
    #frames: Uint8Array[] = [];

    #handleStart = async () => {
        log('CP', 'Start capture session');
        this.asyncLocalId = randomKey();
        this.#framesIndex = 0;
        this.sync.syncNewSession(this.asyncLocalId);
    }

    #handleStop = async () => {
        log('CP', 'Stop capture session');
        if (this.lastProtocol) {
            await this.#flush(this.lastProtocol!);
        }
        this.sync.syncSessionEnded(this.asyncLocalId!);
    }

    #handleFrame = async (protocol: ProtocolDefinition, data: Uint8Array) => {

        // Preprocess frame
        if (protocol.kind === 'super') {
            data = data.subarray(3); // Cut packet ids since all frames can fit in the bt frame
        } else if (protocol.kind === 'compass') {
            // Nothing to do
        }

        // Push frame
        this.#frames.push(data.subarray(3));

        // Convert if batch is full
        if (this.#frames.length >= 500) {
            await this.#flush(protocol);
        }
    }

    #flush = async (protocol: ProtocolDefinition) => {
        if (this.#frames.length > 0) {

            // Flush
            let prepared = prepareAudio(protocol.codec, this.#frames);
            this.#frames = [];
            if (prepared.format === 'wav') {
                let compressed = await compress(prepared.data);
                log('CP', 'Compressed from ' + prepared.data.length + ' to ' + compressed.data.length);
                prepared = compressed;
            }

            // Upload
            this.sync.syncSessionFrame(this.asyncLocalId!, this.#framesIndex++, prepared.format, prepared.data);
        }
    }
}