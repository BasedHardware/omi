import React, { useState, useRef, useEffect } from 'react';
import { StyleSheet, Text, View, TouchableOpacity, SafeAreaView, ScrollView, Alert, Platform, Linking, TextInput } from 'react-native';
import { echo, OmiConnection, BleAudioCodec, OmiDevice } from 'omi-react-native';
import { BleManager, State, Subscription } from 'react-native-ble-plx';

export default function App() {
  const [response, setResponse] = useState<string | null>(null);
  const [devices, setDevices] = useState<OmiDevice[]>([]);
  const [scanning, setScanning] = useState(false);
  const [connected, setConnected] = useState(false);
  const [codec, setCodec] = useState<BleAudioCodec | null>(null);
  const [bluetoothState, setBluetoothState] = useState<State>(State.Unknown);
  const [permissionGranted, setPermissionGranted] = useState<boolean>(false);
  const [isListeningAudio, setIsListeningAudio] = useState<boolean>(false);
  const [audioPacketsReceived, setAudioPacketsReceived] = useState<number>(0);
  const [enableTranscription, setEnableTranscription] = useState<boolean>(false);
  const [deepgramApiKey, setDeepgramApiKey] = useState<string>('');
  const [transcription, setTranscription] = useState<string>('');
  
  // Transcription processing state
  const websocketRef = useRef<WebSocket | null>(null);
  const isTranscribing = useRef<boolean>(false);
  const audioBufferRef = useRef<Uint8Array[]>([]);
  const processingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  
  const omiConnection = useRef(new OmiConnection()).current;
  const stopScanRef = useRef<(() => void) | null>(null);
  const bleManagerRef = useRef<BleManager | null>(null);
  const audioSubscriptionRef = useRef<Subscription | null>(null);
  
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
      // Stop audio listener if active
      if (isListeningAudio) {
        await stopAudioListener();
      }
      
      await omiConnection.disconnect();
      setConnected(false);
      setCodec(null);
    } catch (error) {
      console.error('Disconnect error:', error);
    }
  };
  
  const startAudioListener = async () => {
    try {
      if (!connected || !omiConnection.isConnected()) {
        Alert.alert('Not Connected', 'Please connect to a device first');
        return;
      }
      
      // Reset counter
      setAudioPacketsReceived(0);
      
      console.log('Starting audio bytes listener...');
      
      // Use a counter and timer to batch UI updates
      let packetCounter = 0;
      const updateInterval = setInterval(() => {
        if (packetCounter > 0) {
          setAudioPacketsReceived(prev => prev + packetCounter);
          packetCounter = 0;
        }
      }, 500); // Update UI every 500ms
      
      const subscription = await omiConnection.startAudioBytesListener((bytes) => {
        // Increment local counter instead of updating state directly
        packetCounter++;
        
        // If transcription is enabled and active, add to buffer for WebSocket
        if (bytes.length > 0 && isTranscribing.current) {
          audioBufferRef.current.push(new Uint8Array(bytes));
        }
      });
      
      // Store interval reference for cleanup
      updateIntervalRef.current = updateInterval;
      
      if (subscription) {
        audioSubscriptionRef.current = subscription;
        updateIntervalRef.current = updateInterval;
        setIsListeningAudio(true);
        
        // If transcription was active, stop it when audio listener stops
        if (isTranscribing.current) {
          if (websocketRef.current) {
            websocketRef.current.close();
            websocketRef.current = null;
          }
          
          if (processingIntervalRef.current) {
            clearInterval(processingIntervalRef.current);
            processingIntervalRef.current = null;
          }
          
          isTranscribing.current = false;
        }
        
        Alert.alert('Success', 'Started listening for audio bytes');
      } else {
        Alert.alert('Error', 'Failed to start audio listener');
      }
    } catch (error) {
      console.error('Start audio listener error:', error);
      Alert.alert('Error', `Failed to start audio listener: ${error}`);
    }
  };
  
  /**
   * Initialize WebSocket transcription service with Deepgram
   */
  const initializeWebSocketTranscription = () => {
    if (!deepgramApiKey) {
      console.error('API key is required for transcription');
      return;
    }
    
    try {
      // Close any existing connection
      if (websocketRef.current) {
        websocketRef.current.close();
        websocketRef.current = null;
      }
      
      // Clear any existing processing interval
      if (processingIntervalRef.current) {
        clearInterval(processingIntervalRef.current);
        processingIntervalRef.current = null;
      }
      
      // Reset audio buffer
      audioBufferRef.current = [];
      isTranscribing.current = false;
      
      // Create a new WebSocket connection to Deepgram with configuration in URL params
      const params = new URLSearchParams({
        sample_rate: '16000',
        encoding: 'opus',
        channels: '1',
        model: 'nova-2',
        language: 'en-US',
        smart_format: 'true',
        interim_results: 'false',
        punctuate: 'true',
        diarize: 'true'
      });
      
      const ws = new WebSocket(`wss://api.deepgram.com/v1/listen?${params.toString()}`, [], {
        headers: {
          'Authorization': `Token ${deepgramApiKey}`
        }
      });
      
      ws.onopen = () => {
        console.log('Deepgram WebSocket connection established');
        isTranscribing.current = true;
        
        // Start processing interval to send accumulated audio
        processingIntervalRef.current = setInterval(() => {
          if (audioBufferRef.current.length > 0 && isTranscribing.current) {
            sendAudioToWebSocket();
          }
        }, 250); // Send audio every 250ms
      };
      
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          console.log("Transcript received:", data);
          
          // Check if we have a transcript
          if (data.channel?.alternatives?.[0]?.transcript) {
            const transcript = data.channel.alternatives[0].transcript.trim();
            
            // Only update UI if we have actual text
            if (transcript) {
              setTranscription((prev) => {
                // Limit to last 5 transcripts to avoid too much text
                const lines = prev ? prev.split('\n') : [];
                if (lines.length > 4) {
                  lines.shift();
                }
                
                // Add new transcript with a timestamp
                const now = new Date();
                const timestamp = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}`;
                
                // Add speaker information if available
                const speakerInfo = data.channel.alternatives[0].words?.[0]?.speaker 
                  ? `[Speaker ${data.channel.alternatives[0].words[0].speaker}]` 
                  : '';
                
                lines.push(`[${timestamp}] ${speakerInfo} ${transcript}`);
                
                return lines.join('\n');
              });
            }
          }
        } catch (error) {
          console.error('Error parsing WebSocket message:', error);
        }
      };
      
      ws.onerror = (error) => {
        console.error('Deepgram WebSocket error:', error);
      };
      
      ws.onclose = () => {
        console.log('Deepgram WebSocket connection closed');
        isTranscribing.current = false;
      };
      
      websocketRef.current = ws;
      console.log('Deepgram WebSocket transcription initialized');
      
    } catch (error) {
      console.error('Error initializing Deepgram WebSocket transcription:', error);
    }
  };
  
  /**
   * Send accumulated audio buffer to Deepgram WebSocket
   */
  const sendAudioToWebSocket = () => {
    if (!websocketRef.current || !isTranscribing.current || audioBufferRef.current.length === 0) {
      return;
    }
    
    try {
      // Send each audio chunk individually to Deepgram
      // This is more efficient for streaming audio
      for (const chunk of audioBufferRef.current) {
        if (websocketRef.current.readyState === WebSocket.OPEN) {
          websocketRef.current.send(chunk);
        }
      }
      
      // Clear the buffer after sending
      audioBufferRef.current = [];
    } catch (error) {
      console.error('Error sending audio to Deepgram WebSocket:', error);
    }
  };
  
  
  // Store the update interval reference
  const updateIntervalRef = useRef<NodeJS.Timeout | null>(null);
  
  const stopAudioListener = async () => {
    try {
      // Clear the UI update interval
      if (updateIntervalRef.current) {
        clearInterval(updateIntervalRef.current);
        updateIntervalRef.current = null;
      }
      
      if (audioSubscriptionRef.current) {
        await omiConnection.stopAudioBytesListener(audioSubscriptionRef.current);
        audioSubscriptionRef.current = null;
        setIsListeningAudio(false);
        
        // Disable transcription
        if (enableTranscription) {
          // Close WebSocket connection
          if (websocketRef.current) {
            websocketRef.current.close();
            websocketRef.current = null;
          }
          
          // Clear processing interval
          if (processingIntervalRef.current) {
            clearInterval(processingIntervalRef.current);
            processingIntervalRef.current = null;
          }
        }
      }
    } catch (error) {
      console.error('Stop audio listener error:', error);
      Alert.alert('Error', `Failed to stop audio listener: ${error}`);
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
            
            <View style={styles.audioControls}>
              <TouchableOpacity 
                style={[
                  styles.button, 
                  isListeningAudio ? styles.buttonWarning : null,
                  {marginTop: 15}
                ]} 
                onPress={isListeningAudio ? stopAudioListener : startAudioListener}
              >
                <Text style={styles.buttonText}>
                  {isListeningAudio ? "Stop Audio Listener" : "Start Audio Listener"}
                </Text>
              </TouchableOpacity>
              
              {isListeningAudio && (
                <View style={styles.audioStatsContainer}>
                  <Text style={styles.audioStatsTitle}>Audio Packets Received:</Text>
                  <Text style={styles.audioStatsValue}>{audioPacketsReceived}</Text>
                </View>
              )}
              
              <View style={styles.transcriptionContainer}>
                <Text style={styles.sectionSubtitle}>Deepgram Transcription</Text>
                
                <View style={styles.checkboxContainer}>
                  <TouchableOpacity
                    style={[styles.checkbox, enableTranscription && styles.checkboxChecked]}
                    onPress={() => {
                      const newValue = !enableTranscription;
                      setEnableTranscription(newValue);
                      
                      // If disabling, close any active connections
                      if (!newValue && websocketRef.current) {
                        websocketRef.current.close();
                        websocketRef.current = null;
                        
                        if (processingIntervalRef.current) {
                          clearInterval(processingIntervalRef.current);
                          processingIntervalRef.current = null;
                        }
                      }
                    }}
                  >
                    {enableTranscription && <Text style={styles.checkmark}>✓</Text>}
                  </TouchableOpacity>
                  <Text style={styles.checkboxLabel}>Enable Transcription</Text>
                </View>
                
                {enableTranscription && (
                  <View style={styles.inputContainer}>
                    <Text style={styles.inputLabel}>API Key:</Text>
                    <TextInput
                      style={styles.apiKeyInput}
                      value={deepgramApiKey}
                      onChangeText={(text) => {
                        setDeepgramApiKey(text);
                      }}
                      placeholder="Enter Deepgram API Key"
                      secureTextEntry={true}
                    />
                  </View>
                )}
                
                
                {enableTranscription && (
                  <>
                    <TouchableOpacity 
                      style={[
                        styles.button, 
                        isTranscribing.current ? styles.buttonWarning : null,
                        {marginTop: 15, marginBottom: 15}
                      ]} 
                      onPress={() => {
                        if (isTranscribing.current) {
                          // Stop transcription
                          if (websocketRef.current) {
                            websocketRef.current.close();
                            websocketRef.current = null;
                          }
                          
                          if (processingIntervalRef.current) {
                            clearInterval(processingIntervalRef.current);
                            processingIntervalRef.current = null;
                          }
                          
                          isTranscribing.current = false;
                        } else {
                          // Start transcription
                          if (!deepgramApiKey) {
                            Alert.alert('API Key Required', 'Please enter your Deepgram API key to start transcription');
                            return;
                          }
                          
                          if (!isListeningAudio) {
                            Alert.alert('Audio Required', 'Please start the audio listener first');
                            return;
                          }
                          
                          initializeWebSocketTranscription();
                          setTranscription(''); // Clear previous transcription
                        }
                      }}
                      disabled={!isListeningAudio}
                    >
                      <Text style={styles.buttonText}>
                        {isTranscribing.current ? "Stop Transcription" : "Start Transcription"}
                      </Text>
                    </TouchableOpacity>
                    
                    {transcription && (
                      <View style={styles.transcriptionTextContainer}>
                        <Text style={styles.transcriptionTitle}>Transcription:</Text>
                        <Text style={styles.transcriptionText}>{transcription}</Text>
                      </View>
                    )}
                  </>
                )}
              </View>
            </View>
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
  audioControls: {
    marginTop: 10,
  },
  audioStatsContainer: {
    marginTop: 15,
    padding: 12,
    backgroundColor: '#f0f0f0',
    borderRadius: 8,
    alignItems: 'center',
    borderLeftWidth: 4,
    borderLeftColor: '#FF9500',
  },
  audioStatsTitle: {
    fontSize: 14,
    fontWeight: '500',
    color: '#555',
  },
  audioStatsValue: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#FF9500',
    marginTop: 5,
  },
  transcriptionContainer: {
    marginTop: 20,
    padding: 15,
    backgroundColor: '#f8f8f8',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#e0e0e0',
  },
  sectionSubtitle: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 12,
    color: '#333',
  },
  inputContainer: {
    marginBottom: 12,
  },
  inputLabel: {
    fontSize: 14,
    fontWeight: '500',
    marginBottom: 6,
    color: '#555',
  },
  apiKeyInput: {
    backgroundColor: 'white',
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 6,
    padding: 10,
    fontSize: 14,
  },
  checkboxContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 15,
  },
  checkbox: {
    width: 22,
    height: 22,
    borderWidth: 1,
    borderColor: '#007AFF',
    borderRadius: 4,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 10,
  },
  checkboxChecked: {
    backgroundColor: '#007AFF',
  },
  checkmark: {
    color: 'white',
    fontSize: 14,
    fontWeight: 'bold',
  },
  checkboxLabel: {
    fontSize: 14,
    color: '#333',
  },
  transcriptionTextContainer: {
    marginTop: 12,
    padding: 10,
    backgroundColor: 'white',
    borderRadius: 6,
    borderLeftWidth: 3,
    borderLeftColor: '#007AFF',
  },
  transcriptionTitle: {
    fontSize: 14,
    fontWeight: '500',
    marginBottom: 6,
    color: '#555',
  },
  transcriptionText: {
    fontSize: 14,
    color: '#333',
    lineHeight: 20,
  },
});
