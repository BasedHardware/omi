import React, { useState, useRef } from 'react';
import { StyleSheet, Text, View, TouchableOpacity, SafeAreaView, ScrollView, Alert, Platform } from 'react-native';
import { echo, OmiConnection, BleAudioCodec, OmiDevice } from 'omi-react-native';

export default function App() {
  const [response, setResponse] = useState<string | null>(null);
  const [devices, setDevices] = useState<OmiDevice[]>([]);
  const [scanning, setScanning] = useState(false);
  const [connected, setConnected] = useState(false);
  const [codec, setCodec] = useState<BleAudioCodec | null>(null);
  
  const omiConnection = useRef(new OmiConnection()).current;
  const stopScanRef = useRef<(() => void) | null>(null);

  const handlePress = () => {
    const result = echo('Hello Omi!');
    setResponse(result);
  };

  const startScan = () => {
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
      30000 // 10 seconds timeout
    );
    
    // Auto-stop after 10 seconds
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
      const success = await omiConnection.connect(deviceId, (id, state) => {
        console.log(`Device ${id} connection state: ${state}`);
        setConnected(state === 'connected');
        if (state !== 'connected') {
          setCodec(null);
        }
      });
      
      if (success) {
        setConnected(true);
        Alert.alert('Connected', 'Successfully connected to device');
      } else {
        Alert.alert('Connection Failed', 'Could not connect to device');
      }
    } catch (error) {
      console.error('Connection error:', error);
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
      if (!omiConnection.isConnected()) {
        Alert.alert('Not Connected', 'Please connect to a device first');
        return;
      }
      
      const codecValue = await omiConnection.getAudioCodec();
      setCodec(codecValue);
      Alert.alert('Audio Codec', `Current codec: ${codecValue}`);
    } catch (error) {
      console.error('Get codec error:', error);
      Alert.alert('Error', `Failed to get audio codec: ${error}`);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.title}>Omi SDK Example</Text>
        
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
