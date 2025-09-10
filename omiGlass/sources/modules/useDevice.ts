import * as React from 'react';

const DEVICE_STORAGE_KEY = 'openglassDeviceId';

export function useDevice(): [BluetoothRemoteGATTServer | null, () => Promise<void>, boolean] {

    // Create state
    let deviceRef = React.useRef<BluetoothRemoteGATTServer | null>(null);
    let [device, setDevice] = React.useState<BluetoothRemoteGATTServer | null>(null);
    let [isAutoConnecting, setIsAutoConnecting] = React.useState<boolean>(false);

    // Setup disconnect handler
    const setupDisconnectHandler = (connectedDevice: BluetoothDevice) => {
        connectedDevice.ongattserverdisconnected = async () => {
            console.log('Device disconnected, attempting to reconnect...');
            
            // Attempt to reconnect
            setIsAutoConnecting(true);
            try {
                if (connectedDevice.gatt) {
                    const gatt = await connectedDevice.gatt.connect();
                    deviceRef.current = gatt;
                    setDevice(gatt);
                    console.log('Reconnection successful!');
                }
            } catch (err) {
                console.error('Reconnection failed:', err);
                deviceRef.current = null;
                setDevice(null);
            } finally {
                setIsAutoConnecting(false);
            }
        };
    };

    // Create callback
    const doConnect = React.useCallback(async () => {
        try {
            // Connect to device
            console.log('Requesting device connection...');
            let connected = await navigator.bluetooth.requestDevice({
                filters: [{ name: 'OMI Glass' }],
                optionalServices: ['19B10000-E8F2-537E-4F6C-D104768A1214'.toLowerCase()],
            });

            // Store device ID for future reconnections
            console.log('Storing device ID:', connected.id);
            localStorage.setItem(DEVICE_STORAGE_KEY, connected.id);

            // Connect to gatt
            console.log('Connecting to GATT server...');
            let gatt: BluetoothRemoteGATTServer = await connected.gatt!.connect();
            console.log('Connected successfully!');

            // Update state
            deviceRef.current = gatt;
            setDevice(gatt);
            
            // Setup disconnect handler for auto-reconnect
            setupDisconnectHandler(connected);
            
        } catch (e) {
            // Handle error
            console.error('Connection failed:', e);
        }
    }, []);

    // Return
    return [device, doConnect, isAutoConnecting];
}
