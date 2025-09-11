import * as React from 'react';
import { Platform, PermissionsAndroid, Alert } from 'react-native';
import { BleManager, Device } from 'react-native-ble-plx';
import { OmiDevice, OMI_UUIDS } from '../types/device';

const DEVICE_STORAGE_KEY = 'openglassDeviceId';

export function useDevice(): [OmiDevice | null, () => Promise<void>, boolean] {

    // Create state
    let deviceRef = React.useRef<OmiDevice | null>(null);
    let [device, setDevice] = React.useState<OmiDevice | null>(null);
    let [isAutoConnecting, setIsAutoConnecting] = React.useState<boolean>(false);
    let bleManagerRef = React.useRef<BleManager | null>(null);

    // Initialize BLE manager for native platforms
    React.useEffect(() => {
        if (Platform.OS !== 'web') {
            bleManagerRef.current = new BleManager();
        }
    }, []);

    // Cross-platform storage functions
    const getStoredDeviceId = (): string | null => {
        if (Platform.OS === 'web') {
            return localStorage.getItem(DEVICE_STORAGE_KEY);
        }
        // For React Native, we'll use a simple in-memory approach for now (Use async storage in prod)
        return null;
    };

    const setStoredDeviceId = (deviceId: string): void => {
        if (Platform.OS === 'web') {
            localStorage.setItem(DEVICE_STORAGE_KEY, deviceId);
        }
        // For React Native, we'll use a simple in-memory approach for now (Use async storage in prod)
    };

    // Request Bluetooth permissions for Android
    const requestBluetoothPermissions = async (): Promise<boolean> => {
        if (Platform.OS === 'android') {
            try {
                const apiLevel = Platform.Version;
                
                if (apiLevel >= 31) {
                    // Android 12+ permissions
                    const permissions = [
                        PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN,
                        PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT,
                        PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION,
                    ];

                    console.log('Requesting Bluetooth permissions for Android 12+');
                    
                    const granted = await PermissionsAndroid.requestMultiple(permissions);
                    
                    const allPermissionsGranted = permissions.every(
                        permission => granted[permission] === PermissionsAndroid.RESULTS.GRANTED
                    );

                    if (!allPermissionsGranted) {
                        Alert.alert(
                            'Permissions Required',
                            'Bluetooth permissions are required to connect to OMI Glass devices. Please grant permissions in settings.',
                            [{ text: 'OK' }]
                        );
                        return false;
                    }
                } else {
                    // Pre-Android 12 permissions
                    const permissions = [
                        PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION,
                    ];

                    console.log('Requesting Bluetooth permissions for Android < 12');
                    
                    const granted = await PermissionsAndroid.requestMultiple(permissions);
                    
                    const allPermissionsGranted = permissions.every(
                        permission => granted[permission] === PermissionsAndroid.RESULTS.GRANTED
                    );

                    if (!allPermissionsGranted) {
                        Alert.alert(
                            'Permissions Required',
                            'Location permission is required for Bluetooth scanning. Please grant permission in settings.',
                            [{ text: 'OK' }]
                        );
                        return false;
                    }
                }

                console.log('All Bluetooth permissions granted');
                return true;
            } catch (error) {
                console.error('Permission request error:', error);
                return false;
            }
        }
        
        // iOS permissions are handled by the system and declared in Info.plist
        return true;
    };

    // Setup disconnect handler for web
    const setupWebDisconnectHandler = (connectedDevice: BluetoothDevice, deviceId: string, deviceName: string) => {
        connectedDevice.ongattserverdisconnected = async () => {
            console.log('Device disconnected, attempting to reconnect...');
            
            // Attempt to reconnect
            setIsAutoConnecting(true);
            try {
                if (connectedDevice.gatt) {
                    const gatt = await connectedDevice.gatt.connect();
                    const omiDevice: OmiDevice = {
                        id: deviceId,
                        name: deviceName,
                        gatt: gatt
                    };
                    deviceRef.current = omiDevice;
                    setDevice(omiDevice);
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

    // Setup disconnect handler for native
    const setupNativeDisconnectHandler = (nativeDevice: Device) => {
        nativeDevice.onDisconnected(() => {
            console.log('Device disconnected');
            deviceRef.current = null;
            setDevice(null);
        });
    };

    // Web connection function
    const connectWeb = async (): Promise<void> => {
        try {
            console.log('Requesting device connection...');
            let connected = await navigator.bluetooth.requestDevice({
                filters: [{ name: 'OMI Glass' }],
                optionalServices: [OMI_UUIDS.SERVICE.toLowerCase()],
            });

            // Store device ID for future reconnections
            console.log('Storing device ID:', connected.id);
            setStoredDeviceId(connected.id);

            // Connect to gatt
            console.log('Connecting to GATT server...');
            let gatt: BluetoothRemoteGATTServer = await connected.gatt!.connect();
            console.log('Connected successfully!');

            const omiDevice: OmiDevice = {
                id: connected.id,
                name: connected.name || 'OMI Glass',
                gatt: gatt
            };

            deviceRef.current = omiDevice;
            setDevice(omiDevice);
            
            // Setup disconnect handler for auto-reconnect
            setupWebDisconnectHandler(connected, connected.id, connected.name || 'OMI Glass');
            
        } catch (e) {
            console.error('Web connection failed:', e);
        }
    };

    // Native connection function
    const connectNative = async (): Promise<void> => {
        const bleManager = bleManagerRef.current;
        if (!bleManager) {
            console.error('BLE Manager not initialized');
            return;
        }

        try {
            // Request permissions first
            const permissionsGranted = await requestBluetoothPermissions();
            if (!permissionsGranted) {
                throw new Error('Bluetooth permissions not granted');
            }

            // Check if Bluetooth is enabled
            const state = await bleManager.state();
            if (state !== 'PoweredOn') {
                console.error('Bluetooth is not enabled');
                throw new Error('Bluetooth is not enabled. Please enable Bluetooth and try again.');
            }

            console.log('Scanning for OMI Glass devices...');
            
            return new Promise((resolve, reject) => {
                const timeout = setTimeout(() => {
                    bleManager.stopDeviceScan();
                    reject(new Error('Device scan timeout - OMI Glass not found'));
                }, 10000);

                bleManager.startDeviceScan(null, null, async (error, scannedDevice) => {
                    if (error) {
                        console.error('Scan error:', error);
                        clearTimeout(timeout);
                        reject(error);
                        return;
                    }

                    if (scannedDevice && scannedDevice.name === 'OMI Glass') {
                        console.log('Found OMI Glass device:', scannedDevice.id);
                        bleManager.stopDeviceScan();
                        clearTimeout(timeout);

                        try {
                            // Connect to device with timeout
                            const connectedDevice = await scannedDevice.connect();
                            await connectedDevice.discoverAllServicesAndCharacteristics();

                            console.log('Connected successfully to native device!');

                            // Store device ID
                            setStoredDeviceId(scannedDevice.id);

                            // Create OMI device object
                            const omiDevice: OmiDevice = {
                                id: scannedDevice.id,
                                name: scannedDevice.name || 'OMI Glass',
                                nativeDevice: connectedDevice
                            };

                            // Update state
                            deviceRef.current = omiDevice;
                            setDevice(omiDevice);

                            // Setup disconnect handler
                            setupNativeDisconnectHandler(connectedDevice);

                            resolve();
                        } catch (connectionError) {
                            console.error('Native connection failed:', connectionError);
                            reject(connectionError);
                        }
                    }
                });
            });
        } catch (e) {
            console.error('Native connection failed:', e);
            throw e;
        }
    };

    const doConnect = React.useCallback(async () => {
        try {
            if (Platform.OS === 'web') {
                await connectWeb();
            } else {
                await connectNative();
            }
        } catch (error) {
            console.error('Connection failed:', error);
            // Re-throw the error so the UI can handle it
            throw error;
        }
    }, []);

    // Return
    return [device, doConnect, isAutoConnecting];
}
