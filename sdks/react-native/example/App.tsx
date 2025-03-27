import React, { useState, useRef, useEffect } from 'react';
import { StyleSheet, Text, View, TouchableOpacity, SafeAreaView, ScrollView, Alert, Platform, Linking } from 'react-native';
import { echo, OmiConnection, BleAudioCodec, OmiDevice } from 'omi-react-native';
import { BleManager, State } from 'react-native-ble-plx';

export default function App() {
  const [response, setResponse] = useState<string | null>(null);
  const [devices, setDevices] = useState<OmiDevice[]>([]);
  const [scanning, setScanning] = useState(false);
  const [connected, setConnected] = useState(false);
  const [codec, setCodec] = useState<BleAudioCodec | null>(null);
  const [bluetoothState, setBluetoothState] = useState<State>(State.Unknown);
  const [permissionGranted, setPermissionGranted] = useState<boolean>(false);
  
  const omiConnection = useRef(new OmiConnection()).current;
  const stopScanRef = useRef<(() => void) | null>(null);
  const bleManagerRef = useRef<BleManager | null>(null);
  
  useEffect(() => {
    // Initialize BLE Manager
    const manager = new BleManager();
    bleManagerRef.current = manager;
    
    // Subscribe to state changes
    const subscription = manager.onStateChange((state) => {
      console.log('Bluetooth state:', state);
      setBluetoothState(state);
      
      if (state === State.PoweredOn) {
        // Bluetooth is on, now we can request permission
        requestBluetoothPermission();
      }
    }, true); // true to check the initial state
    
    return () => {
      // Clean up subscription and manager when component unmounts
      subscription.remove();
      if (bleManagerRef.current) {
        bleManagerRef.current.destroy();
      }
    };
  }, []);
  
  const requestBluetoothPermission = async () => {
    try {
      if (Platform.OS === 'ios') {
        // On iOS, the scan will trigger the permission dialog
        const subscription = bleManagerRef.current?.onStateChange((state) => {
          if (state === State.PoweredOn) {
            bleManagerRef.current?.startDeviceScan(null, null, (error) => {
              if (error) {
                console.error('Permission error:', error);
                setPermissionGranted(false);
                Alert.alert(
                  'Bluetooth Permission',
                  'Please enable Bluetooth permission in your device settings to use this feature.',
                  [
                    { text: 'Cancel', style: 'cancel' },
                    { text: 'Open Settings', onPress: () => Linking.openSettings() }
                  ]
                );
              } else {
                setPermissionGranted(true);
              }
              // Stop scanning immediately after permission check
              bleManagerRef.current?.stopDeviceScan();
              subscription?.remove();
            });
          }
        }, false);
      } else if (Platform.OS === 'android') {
        // On Android, we need to check for location and bluetooth permissions
        try {
          // This will trigger the permission dialog
          await bleManagerRef.current?.startDeviceScan(null, null, (error) => {
            if (error) {
              console.error('Permission error:', error);
              setPermissionGranted(false);
              Alert.alert(
                'Bluetooth Permission',
                'Please enable Bluetooth and Location permissions in your device settings to use this feature.',
                [
                  { text: 'Cancel', style: 'cancel' },
                  { text: 'Open Settings', onPress: () => Linking.openSettings() }
                ]
              );
            } else {
              setPermissionGranted(true);
            }
            // Stop scanning immediately after permission check
            bleManagerRef.current?.stopDeviceScan();
          });
        } catch (error) {
          console.error('Error requesting permissions:', error);
          setPermissionGranted(false);
        }
      }
    } catch (error) {
      console.error('Error in requestBluetoothPermission:', error);
      setPermissionGranted(false);
    }
  };

  const handlePress = () => {
    const result = echo('Hello Omi!');
    setResponse(result);
  };

  const startScan = () => {
    // Check if Bluetooth is on and permission is granted
    if (bluetoothState !== State.PoweredOn) {
      Alert.alert(
        'Bluetooth is Off',
        'Please turn on Bluetooth to scan for devices.',
        [
          { text: 'Cancel', style: 'cancel' },
          { text: 'Open Settings', onPress: () => Linking.openSettings() }
        ]
      );
      return;
    }
    
    if (!permissionGranted) {
      requestBluetoothPermission();
      return;
    }
    
    setDevices([]);
    setScanning(true);
    
    stopScanRef.current = omiConnection.scanForDevices(
      (device) => {
        setDevices((prev) => {
          // Check if device already exists
          if (prev.some((d) => d.id === device.id)) {
            return prev;
          }
          return [...prev, device];
        });
      },
      30000 // 30 seconds timeout
    );
    
    // Auto-stop after 30 seconds
    setTimeout(() => {
      stopScan();
    }, 30000);
  };
  
  const stopScan = () => {
    if (stopScanRef.current) {
      stopScanRef.current();
      stopScanRef.current = null;
    }
    setScanning(false);
  };
  
  const connectToDevice = async (deviceId: string) => {
    try {
      // First check if we're already connected to a device
      if (connected) {
        // Disconnect from the current device first
        await disconnectFromDevice();
      }
      
      // Set connecting state
      setConnected(false);
      
      const success = await omiConnection.connect(deviceId, (id, state) => {
        console.log(`Device ${id} connection state: ${state}`);
        const isConnected = state === 'connected';
        setConnected(isConnected);
        
        if (!isConnected) {
          setCodec(null);
        }
      });
      
      if (success) {
        setConnected(true);
        Alert.alert('Connected', 'Successfully connected to device');
      } else {
        setConnected(false);
        Alert.alert('Connection Failed', 'Could not connect to device');
      }
    } catch (error) {
      console.error('Connection error:', error);
      setConnected(false);
      Alert.alert('Connection Error', String(error));
    }
  };
  
  const disconnectFromDevice = async () => {
    try {
      await omiConnection.disconnect();
      setConnected(false);
      setCodec(null);
    } catch (error) {
      console.error('Disconnect error:', error);
    }
  };
  
  const getAudioCodec = async () => {
    try {
      if (!connected || !omiConnection.isConnected()) {
        Alert.alert('Not Connected', 'Please connect to a device first');
        return;
      }
      
      try {
        const codecValue = await omiConnection.getAudioCodec();
        setCodec(codecValue);
        Alert.alert('Audio Codec', `Current codec: ${codecValue}`);
      } catch (error) {
        console.error('Get codec error:', error);
        
        // If we get a connection error, update the UI state
        if (String(error).includes('not connected')) {
          setConnected(false);
          Alert.alert('Connection Lost', 'The device appears to be disconnected. Please reconnect and try again.');
        } else {
          Alert.alert('Error', `Failed to get audio codec: ${error}`);
        }
      }
    } catch (error) {
      console.error('Unexpected error:', error);
      Alert.alert('Error', `An unexpected error occurred: ${error}`);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.title}>Omi SDK Example</Text>
        
        {/* Bluetooth Status Banner */}
        {bluetoothState !== State.PoweredOn && (
          <View style={styles.statusBanner}>
            <Text style={styles.statusText}>
              {bluetoothState === State.PoweredOff 
                ? 'Bluetooth is turned off. Please enable Bluetooth to use this app.' 
                : bluetoothState === State.Unauthorized
                ? 'Bluetooth permission not granted. Please allow Bluetooth access in settings.'
                : 'Bluetooth is not available or initializing...'}
            </Text>
            <TouchableOpacity 
              style={styles.statusButton}
              onPress={() => {
                if (bluetoothState === State.PoweredOff) {
                  Linking.openSettings();
                } else if (bluetoothState === State.Unauthorized) {
                  requestBluetoothPermission();
                }
              }}
            >
              <Text style={styles.statusButtonText}>
                {bluetoothState === State.PoweredOff ? 'Open Settings' : 'Request Permission'}
              </Text>
            </TouchableOpacity>
          </View>
        )}
        
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Echo Test</Text>
          <TouchableOpacity 
            style={styles.button} 
            onPress={handlePress}
          >
            <Text style={styles.buttonText}>Say Hello</Text>
          </TouchableOpacity>
          
          {response && (
            <View style={styles.responseContainer}>
              <Text style={styles.responseTitle}>Response:</Text>
              <Text style={styles.responseText}>{response}</Text>
            </View>
          )}
        </View>
        
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Bluetooth Connection</Text>
          <TouchableOpacity 
            style={[styles.button, scanning ? styles.buttonWarning : null]} 
            onPress={scanning ? stopScan : startScan}
          >
            <Text style={styles.buttonText}>{scanning ? "Stop Scan" : "Scan for Devices"}</Text>
          </TouchableOpacity>
          
          {connected && (
            <TouchableOpacity 
              style={[styles.button, styles.buttonDanger, {marginTop: 10}]} 
              onPress={disconnectFromDevice}
            >
              <Text style={styles.buttonText}>Disconnect</Text>
            </TouchableOpacity>
          )}
        </View>
        
        {devices.length > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Found Devices</Text>
            <View style={styles.deviceList}>
              {devices.map((device) => (
                <View key={device.id} style={styles.deviceItem}>
                  <View>
                    <Text style={styles.deviceName}>{device.name}</Text>
                    <Text style={styles.deviceInfo}>RSSI: {device.rssi} dBm</Text>
                  </View>
                  <TouchableOpacity 
                    style={[styles.button, styles.smallButton, connected ? styles.buttonDisabled : null]} 
                    onPress={() => connectToDevice(device.id)}
                    disabled={connected}
                  >
                    <Text style={styles.buttonText}>Connect</Text>
                  </TouchableOpacity>
                </View>
              ))}
            </View>
          </View>
        )}
        
        {connected && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Device Functions</Text>
            <TouchableOpacity 
              style={styles.button} 
              onPress={getAudioCodec}
            >
              <Text style={styles.buttonText}>Get Audio Codec</Text>
            </TouchableOpacity>
            
            {codec && (
              <View style={styles.codecContainer}>
                <Text style={styles.codecTitle}>Current Audio Codec:</Text>
                <Text style={styles.codecValue}>{codec}</Text>
              </View>
            )}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
  },
  statusBanner: {
    backgroundColor: '#FF9500',
    padding: 12,
    borderRadius: 8,
    marginBottom: 15,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  statusText: {
    color: 'white',
    fontSize: 14,
    fontWeight: '500',
    flex: 1,
    marginRight: 10,
  },
  statusButton: {
    backgroundColor: 'rgba(255, 255, 255, 0.3)',
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: 6,
  },
  statusButtonText: {
    color: 'white',
    fontWeight: '600',
    fontSize: 12,
  },
  content: {
    padding: 20,
    paddingTop: Platform.OS === 'android' ? 40 : 0,
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
    marginBottom: 20,
    color: '#333',
    textAlign: 'center',
  },
  section: {
    marginBottom: 25,
    padding: 15,
    backgroundColor: 'white',
    borderRadius: 10,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 3,
    elevation: 2,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    marginBottom: 15,
    color: '#333',
  },
  button: {
    backgroundColor: '#007AFF',
    paddingVertical: 12,
    paddingHorizontal: 20,
    borderRadius: 8,
    alignItems: 'center',
    elevation: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
  },
  smallButton: {
    paddingVertical: 8,
    paddingHorizontal: 12,
  },
  buttonWarning: {
    backgroundColor: '#FF9500',
  },
  buttonDanger: {
    backgroundColor: '#FF3B30',
  },
  buttonDisabled: {
    backgroundColor: '#A0A0A0',
    opacity: 0.7,
  },
  buttonText: {
    color: 'white',
    fontSize: 16,
    fontWeight: '600',
  },
  responseContainer: {
    marginTop: 15,
    padding: 12,
    backgroundColor: '#f0f0f0',
    borderRadius: 8,
    borderLeftWidth: 4,
    borderLeftColor: '#007AFF',
  },
  responseTitle: {
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 5,
    color: '#555',
  },
  responseText: {
    fontSize: 14,
    color: '#333',
  },
  deviceList: {
    marginTop: 5,
  },
  deviceItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#eee',
  },
  deviceName: {
    fontSize: 16,
    fontWeight: '500',
    color: '#333',
  },
  deviceInfo: {
    fontSize: 12,
    color: '#666',
    marginTop: 2,
  },
  codecContainer: {
    marginTop: 15,
    padding: 12,
    backgroundColor: '#f0f0f0',
    borderRadius: 8,
    alignItems: 'center',
  },
  codecTitle: {
    fontSize: 14,
    fontWeight: '500',
    color: '#555',
  },
  codecValue: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#007AFF',
    marginTop: 5,
  },
});
