import * as React from 'react';

export function useDevice(): [BluetoothRemoteGATTServer | null, () => Promise<void>] {

    // Create state
    let deviceRef = React.useRef<BluetoothRemoteGATTServer | null>(null);
    let [device, setDevice] = React.useState<BluetoothRemoteGATTServer | null>(null);

    // Create callback
    const doConnect = React.useCallback(async () => {
        try {

            // Connect to device
            let connected = await navigator.bluetooth.requestDevice({
                filters: [{ name: 'OpenGlass' }],
                optionalServices: ['19B10000-E8F2-537E-4F6C-D104768A1214'.toLowerCase()],
            });

            // Connect to gatt
            let gatt: BluetoothRemoteGATTServer = await connected.gatt!.connect();

            // Update state
            deviceRef.current = gatt;
            setDevice(gatt);

            // Reset on disconnect (avoid loosing everything on disconnect)
            // connected.ongattserverdisconnected = () => {
            //     deviceRef.current = null;
            //     setDevice(null);
            // }
        } catch (e) {
            // Handle error
            console.error(e);
        }
    }, [device]);

    // Return
    return [device, doConnect];
}