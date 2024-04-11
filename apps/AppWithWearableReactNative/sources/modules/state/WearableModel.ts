import { AsyncLock } from "teslabot";
import { connectToDevice, manager, startBluetooth } from "../wearable/bt";
import { Jotai } from "./_types";
import { atom, useAtomValue } from "jotai";
import { storage } from "../../storage";
import { COMPASS_SERVICE, KNOWN_BT_SERVICES, ProtocolDefinition, SUPER_SERVICE, resolveProtocol, supportedDeviceNames } from "../wearable/protocol";
import { DeviceModel } from "./DeviceModel";
import { KnownBTServices } from "../wearable/bt_common";

export class WearableModel {
    private lock = new AsyncLock();
    readonly jotai: Jotai;
    readonly pairingStatus = atom<'loading' | 'need-pairing' | 'ready' | 'denied' | 'unavailable'>('loading');
    readonly discoveryStatus = atom<{ devices: { name: string, id: string }[] } | null>(null);
    onStreamingStart?: (protocol: ProtocolDefinition) => void;
    onStreamingStop?: () => void;
    onStreamingFrame?: (data: Uint8Array) => void;
    private _device: DeviceModel | null = null;
    readonly status = atom((get) => {
        let pairing = get(this.pairingStatus);
        if (pairing === 'ready') {
            return {
                pairing: 'ready' as const,
                device: get(this._device!.state),
            };
        } else {
            return {
                pairing,
                device: null
            };
        }
    });
    private _discoveryCancel: (() => void) | null = null;

    constructor(jotai: Jotai) {
        this.jotai = jotai;
        let id = storage.getString('wearable-device');
        if (id) {
            this._device = new DeviceModel(id, jotai);
            this._device.onStreamingStart = this.#onStreamingStart;
            this._device.onStreamingStop = this.#onStreamingStop;
            this._device.onStreamingFrame = this.#onStreamingFrame;
        }
    }

    get device() {
        return this._device;
    }

    start = () => {
        this.lock.inLock(async () => {

            // Starting bluetooth
            let result = await startBluetooth();
            if (result === 'denied') {
                this.jotai.set(this.pairingStatus, 'denied');
                return;
            } else if (result === 'failure') {
                this.jotai.set(this.pairingStatus, 'unavailable');
                return;
            }

            // Not paired
            if (!this._device) {
                this.jotai.set(this.pairingStatus, 'need-pairing');
                return;
            }

            // Connected
            this.jotai.set(this.pairingStatus, 'ready');
        });
    }

    //
    // Service Discovery
    //

    startDiscovery = () => {
        if (this._discoveryCancel != null) {
            return;
        }

        // Start scan
        if (!this.jotai.get(this.discoveryStatus)) {
            this.jotai.set(this.discoveryStatus, { devices: [] });
        }
        manager().startDeviceScan(null, null, (error, device) => {
            if (device && device.name && supportedDeviceNames(device.name)) {
                let devices = this.jotai.get(this.discoveryStatus)!.devices;
                if (devices.find((v) => v.id === device.id)) {
                    return;
                }
                devices = [{ name: device.name, id: device.id }, ...devices];
                this.jotai.set(this.discoveryStatus, { devices });
            }
            if (error) {
                console.error(error);
            }
        });

        // Stop scan
        this._discoveryCancel = () => {
            if (this._discoveryCancel != null) {
                this._discoveryCancel = null;
                manager().stopDeviceScan();
            }
        }
    }

    stopDiscrovery = () => {
        if (this._discoveryCancel != null) {
            this._discoveryCancel();
        }
    }

    resetDiscoveredDevices = () => {
        this.jotai.set(this.discoveryStatus, null);
    }

    tryPairDevice = (id: string) => {
        return this.lock.inLock(async () => {
            if (!!this._device) {
                return 'already-paired' as const;
            }

            // Connecting to device
            let connected = await connectToDevice(id);
            if (!connected) {
                return 'connection-error' as const;
            }

            // Check protocols
            const protocol = resolveProtocol(connected);
            if (!protocol) {
                connected.disconnect();
                return 'unsupported' as const;
            }

            // Save device
            this._device = new DeviceModel(connected, this.jotai);
            this._device.onStreamingStart = this.#onStreamingStart;
            this._device.onStreamingStop = this.#onStreamingStop;
            this._device.onStreamingFrame = this.#onStreamingFrame;
            storage.set('wearable-device', id);
            this.jotai.set(this.pairingStatus, 'ready');

            return 'ok' as const;
        });
    }

    //
    // Streaming
    //

    #onStreamingStart = (protocol: ProtocolDefinition) => {
        if (this.onStreamingStart) {
            this.onStreamingStart(protocol);
        }
    }

    #onStreamingStop = () => {
        if (this.onStreamingStop) {
            this.onStreamingStop();
        }
    }

    #onStreamingFrame = (data: Uint8Array) => {
        if (this.onStreamingFrame) {
            this.onStreamingFrame(data);
        }
    }

    //
    // UI
    //

    use() {
        return useAtomValue(this.status);
    }
}