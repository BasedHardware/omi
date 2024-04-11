import { InvalidateSync } from "teslabot";
import { BTDevice } from "../wearable/bt_common";
import { connectToDevice } from "../wearable/bt";
import { log } from "../../utils/logs";
import { Jotai } from "./_types";
import { atom } from "jotai";
import { ProtocolDefinition, resolveProtocol } from "../wearable/protocol";
import { backoff } from "../../utils/time";

export class DeviceModel {
    readonly id: string;
    readonly #sync: InvalidateSync;
    readonly jotai: Jotai;
    readonly state = atom<'connecting' | 'connected' | 'subscribed'>('connecting');
    onStreamingStart?: (protocol: ProtocolDefinition) => void;
    onStreamingStop?: () => void;
    onStreamingFrame?: (data: Uint8Array) => void;

    #device: BTDevice | null = null;
    #needStreaming = false;
    #streaming: { ptocol: ProtocolDefinition, subscription: () => void } | null = null;

    constructor(id: string | BTDevice, jotai: Jotai) {
        if (typeof id === 'object') {
            this.#device = id;
            this.id = id.id;
            if (id.connected) {
                jotai.set(this.state, 'connected');
            } else {
                jotai.set(this.state, 'connecting');
            }
        } else {
            this.id = id;
        }
        this.jotai = jotai;
        this.#sync = new InvalidateSync(this.#update, { backoff });
        this.#sync.invalidate();
    }

    #update = async () => {
        log('BT', 'DeviceModel#update');

        // Initial connect to device
        if (!this.#device) {
            log('BT', 'Device is not loaded: loading');
            let dev = await connectToDevice(this.id);
            if (!dev) {
                throw new Error('Device not found'); // Backoff retry
            }
            this.#device = dev;
            dev.onDisconnected(() => { log('BT', 'Device disconnected notification'); this.#sync.invalidate(); });
            log('BT', 'Device loaded');
            if (this.#device.connected) {
                this.jotai.set(this.state, 'connected');
            } else {
                this.jotai.set(this.state, 'connecting');
            }
        }

        // Handling device connection state
        log('BT', 'Device connection state state: ' + this.#device.connected);
        if (this.#device.connected) {
            log('BT', 'Device is connected: nothing to do');
        } else {
            log('BT', 'Device is not connected: attempting to connect');
            this.jotai.set(this.state, 'connecting');
            if (this.#streaming) {
                this.#streaming.subscription(); // Unsubscribe
                this.#streaming = null; // Reset streaming
                if (this.onStreamingStop) {
                    this.onStreamingStop();
                }
            }

            let reconnected = await connectToDevice(this.id);
            if (!reconnected) {
                throw new Error('Device not found'); // Backoff retry
            }
            this.#device = reconnected;
            log('BT', 'Device connected');
            this.jotai.set(this.state, 'connected');
        }

        // Handling subscribing
        if (this.#needStreaming && !this.#streaming) {
            log('BT', 'Need streaming: subscribing');

            // Resolve protocol
            const protocol = await resolveProtocol(this.#device);
            if (!protocol) {
                log('BT', 'Protocol not found');
                throw new Error('Protocol not found'); // Should not happen
            }

            // Subscribe
            let sub = protocol.source.subscribe((data) => {
                if (this.onStreamingFrame) {
                    this.onStreamingFrame(data);
                }
            });

            // Save subscription
            this.#streaming = { ptocol: protocol, subscription: sub };
            if (this.onStreamingStart) {
                this.onStreamingStart(protocol);
            }

            // Update state
            this.jotai.set(this.state, 'subscribed');
        }

        // Handle unsubscribing
        if (!this.#needStreaming && this.#streaming) {
            log('BT', 'No need streaming: unsubscribing');
            if (this.#streaming) {
                this.#streaming.subscription(); // Unsubscribe
                this.#streaming = null; // Reset streaming
                if (this.onStreamingStop) {
                    this.onStreamingStop();
                }
            }

            // Update state
            this.jotai.set(this.state, 'connected');
        }
    }

    startStreaming = () => {
        this.#needStreaming = true;
        this.#sync.invalidate();
    }

    stopStreaming = () => {
        this.#needStreaming = false;
        this.#sync.invalidate();
    }
}