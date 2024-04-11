import * as b64 from 'react-native-quick-base64';
import { BleManager, Device, ScanOptions, State, Subscription } from 'react-native-ble-plx';
import { BTDevice, BTService, BTStartResult } from './bt_common';

let _manager: BleManager | null = null;
export function manager() {
    if (_manager === null) {
        _manager = new BleManager();
    }
    return _manager;
}

export async function startBluetooth(): Promise<BTStartResult> {

    let m = manager();
    return new Promise<BTStartResult>((resolve, reject) => {

        // Helpers
        let subscription: Subscription | null = null;
        let ended = false;
        function complete(result: BTStartResult) {
            if (!ended) {
                ended = true;
                if (subscription !== null) {
                    subscription.remove();
                    subscription = null;
                }
                resolve(result);
            }
        }

        // Subscribe
        subscription = m.onStateChange(state => {
            console.log('Bluetooth state:', state);
            if (state === State.PoweredOn) {
                complete('started');
            } else if (state === State.Unsupported) {
                complete('failure');
            } else if (state === State.Unauthorized) {
                complete('denied');
            } else if (state === State.PoweredOff) {
                // Ignore
            } else if (state === State.Resetting) {
                // Ignore
            }
        });

        // Check initial
        (async () => {
            let state = await m.state();
            console.log('Initial state:', state);
            if (state === State.PoweredOn) {
                complete('started');
            } else if (state === State.Unsupported) {
                complete('failure');
            } else if (state === State.Unauthorized) {
                complete('denied');
            }
        })()
    });
}

export async function openDevice(params: { name: string } | { services: string[] }): Promise<BTDevice | null> {
    let m = manager();

    // Load device
    const btDevice = await new Promise<Device | null>((resolve, reject) => {
        let uuids: string[] | null = null;
        let options: ScanOptions | null = null;
        let ended = false;
        function end(device: Device | null) {
            if (!ended) {
                ended = true;
                m.stopDeviceScan();
                resolve(device);
            }
        }
        m.startDeviceScan(uuids, options, (error, device) => {
            console.log('Device:', device?.id, device?.name);
            console.log('Error:', error);
            if (!!device) {
                if ('name' in params) {
                    if (device.name === params.name) {
                        end(device);
                    }
                } else {
                    end(device);
                }
            }
            if (error) {
                console.error(error);
                end(null);
            }
        });
    });
    if (btDevice === null) {
        return null;
    }

    return connectToDevice(btDevice.id);
}

export async function connectToDevice(id: string): Promise<BTDevice | null> {
    let m = manager();
    let btDevice: Device;
    try {
        btDevice = await m.connectToDevice(id, { requestMTU: 250, timeout: 5000 });
    } catch (error) {
        console.error(error);
        return null;
    }
    let name = btDevice.name || 'Unknown';
    let services: BTService[] = [];

    // Connect to device
    await btDevice.connect({ requestMTU: 128 });
    await m.discoverAllServicesAndCharacteristicsForDevice(btDevice.id);

    // Load services
    for (let s of await btDevice.services()) {
        let characteristics = await s.characteristics();
        services.push({
            id: s.uuid,
            characteristics: characteristics.map(c => ({
                id: c.uuid,
                name: c.id,
                canRead: c.isReadable,
                canWrite: c.isWritableWithoutResponse || c.isWritableWithResponse,
                canNotify: c.isNotifiable,
                read: async () => {
                    let value = await c.read();
                    return b64.toByteArray(value.value!);
                },
                write: async (data: Uint8Array) => {
                    await c.writeWithResponse(b64.fromByteArray(data));
                },
                subscribe: (callback: (data: Uint8Array) => void) => {
                    let subs = c.monitor((error, value) => {
                        if (error) {
                            console.error(error);
                        } else {
                            callback(b64.toByteArray(value!.value!));
                        }
                    });
                    return () => {
                        subs.remove();
                    };
                }
            }))
        });
    }

    // Connected state (what about race conditions here?)
    let connected = true;
    let callbacks = new Set<() => void>();
    m.onDeviceDisconnected(id, () => {
        connected = false;
        for (let cb of callbacks) {
            cb();
        }
    });
    connected = await btDevice.isConnected();

    // Wrapper
    return {
        id,
        name,
        services,
        get connected() {
            return connected
        },
        onDisconnected(callback) {
            callbacks.add(callback);
            return () => {
                callbacks.delete(callback);
            };
        },
        async disconnect() {
            await btDevice.cancelConnection();
        }
    };
}

// export function startDiscovery(handler: { discovered: (device: BTDevice) => void, error: (error: Error) => void }) {
//     let m = manager();
//     let devices: Device[] = [];
//     m.startDeviceScan([SUPER_SERVICE], null, (error, device) => {
//         if (!!device) {
//             handler.discovered();
//             devices.push(device);
//         }
//         if (error) {
//             handler.error(error);
//         }
//     });
//     return () => {
//         m.stopDeviceScan();
//         return devices;
//     };
// }