import React, {useState, useContext, useRef} from 'react';
import {useNavigation} from '@react-navigation/native';
import BleManager from 'react-native-ble-manager';
import base64 from 'react-native-base64';
import {View, Text, StyleSheet, FlatList} from 'react-native';
import {Button} from 'react-native-elements';
import {GestureHandlerRootView} from 'react-native-gesture-handler';
import LiveAudioStream from 'react-native-live-audio-stream';
import {DEEPGRAM_API_KEY} from '@env';
import {MomentsContext} from '../contexts/MomentsContext';
import {BluetoothContext} from '../contexts/BluetoothContext';
import MomentListItem from '../components/moments/MomentsListItem';

class AudioStreamer {
  constructor(
    setIsRecording,
    setStreamingTranscript,
    wsRef,
    bleManagerEmitter,
    handleCreateMoment,
  ) {
    this.setIsRecording = setIsRecording;
    this.setStreamingTranscript = setStreamingTranscript;
    this.ws = wsRef;
    this.bleManagerEmitter = bleManagerEmitter;
    this.handleCreateMoment = handleCreateMoment;
    this.serviceUUID = '19B10000-E8F2-537E-4F6C-D104768A1214';
    this.audioCharacteristicUUID = '19B10001-E8F2-537E-4F6C-D104768A1214';
    this.silenceTimer = null;
    this.isSilenceTimerActive = false;
    this.peripheralId = null;
    this.initListeners();
  }

  initListeners() {
    this.bleManagerEmitter.addListener(
      'BleManagerDidUpdateValueForCharacteristic',
      this.handleUpdateValueForCharacteristic.bind(this),
    );
  }

  initWebSocket(peripheralId) {
    this.peripheralId = peripheralId;
    const model = 'nova-2';
    const language = 'en-US';
    const smart_format = true;
    const encoding = 'linear16';
    const sample_rate = 8000;

    const url = `wss://api.deepgram.com/v1/listen?model=${model}&language=${language}&smart_format=${smart_format}&encoding=${encoding}&sample_rate=${sample_rate}`;
    this.ws.current = new WebSocket(url, ['token', DEEPGRAM_API_KEY]);

    this.ws.current.onopen = () => {
      if (peripheralId) {
        this.startBluetoothStreaming(peripheralId);
      } else {
        this.startPhoneStreaming();
      }
    };

    this.ws.current.onerror = error => {
      console.error('WebSocket error:', error);
    };

    this.ws.current.onclose = () => {
      console.log('WebSocket connection closed');
    };

    this.ws.current.onmessage = event => {
      const dataObj = JSON.parse(event.data);
      const transcribedWord = dataObj?.channel?.alternatives?.[0]?.transcript;
      if (transcribedWord) {
        // Clear any existing silence timer because new audio has been received
        clearTimeout(this.silenceTimer);
        this.isSilenceTimerActive = false; // Reset the flag
        this.setStreamingTranscript(
          prevTranscript => prevTranscript + ' ' + transcribedWord,
        );
      } else {
        console.log('Silence detected or transcript not available');
        // Start the silence timer only if it's not already active
        if (!this.isSilenceTimerActive) {
          this.silenceTimer = setTimeout(() => {
            this.handleCreateMoment();
            this.restartRecording();
            this.isSilenceTimerActive = false;
          }, 5000); // 30 seconds of silence
          this.isSilenceTimerActive = true; // Set the flag
        }
      }
    };
  }

  restartRecording() {
    if (this.peripheralId) {
      this.startBluetoothStreaming(this.peripheralId);
    } else {
      this.startPhoneStreaming();
    }
  }

  handleUpdateValueForCharacteristic(data) {
    const array = new Uint8Array(data.value);
    const audioData = array.subarray(3);
    this.ws.current.send(audioData.buffer);
  }

  startBluetoothStreaming(peripheralId) {
    BleManager.startNotification(
      peripheralId,
      this.serviceUUID,
      this.audioCharacteristicUUID,
    )
      .then(() => {
        console.log('Started notification on ' + this.serviceUUID);
        this.setIsRecording(true);
      })
      .catch(error => {
        console.log('Notification error', error);
      });
  }

  startPhoneStreaming() {
    const options = {
      sampleRate: 8000,
      channels: 1,
      bitsPerSample: 16,
      bufferSize: 4096,
    };

    LiveAudioStream.init(options);
    LiveAudioStream.on('data', base64String => {
      const binaryString = base64.decode(base64String);
      const len = binaryString.length;
      const bytes = new Uint8Array(len);
      for (let i = 0; i < len; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }
      this.ws.current.send(bytes.buffer);
    });

    LiveAudioStream.start();
    this.setIsRecording(true);

    setInterval(() => {
      const keepAliveMsg = JSON.stringify({type: 'KeepAlive'});
      this.ws.current.send(keepAliveMsg);
      console.log('Sent KeepAlive message');
    }, 7000);
  }

  stopRecording = async () => {
    try {
      LiveAudioStream.stop();
      this.setIsRecording(false);
      this.ws.current.send(JSON.stringify({type: 'CloseStream'}));
      this.ws.current.close();
    } catch (error) {
      console.error('Failed to stop recording', error);
    }
  };
}

const MomentsTab = () => {
  const [isRecording, setIsRecording] = useState(false);
  const [streamingTranscript, setStreamingTranscript] = useState('');
  const ws = useRef(null);
  const {moments, setMoments, addMoment} = useContext(MomentsContext);
  const {bleManagerEmitter} = useContext(BluetoothContext);

  const createMoment = async () => {
    console.log('Creating moment', streamingTranscript);
    try {
      const newMoment = {
        text: streamingTranscript,
        date: new Date(),
      };
      setMoments([...moments, newMoment]);
      await addMoment(newMoment);
      setStreamingTranscript('');
    } catch (error) {
      console.error('Error creating moment', error);
    }
  };

  const audioStreamer = new AudioStreamer(
    setIsRecording,
    setStreamingTranscript,
    ws,
    bleManagerEmitter,
    createMoment,
  );
  const navigation = useNavigation();

  const startRecording = async () => {
    // Check if a Bluetooth device is connected
    const connectedDevices = await BleManager.getConnectedPeripherals([
      audioStreamer.serviceUUID,
    ]);
    if (connectedDevices.length > 0) {
      // If a Bluetooth device is connected, start streaming audio from the Bluetooth device
      audioStreamer.initWebSocket(connectedDevices[0].id);
    } else {
      // If no Bluetooth device is connected, initialize the WebSocket and start streaming from the phone's microphone
      audioStreamer.initWebSocket();
    }
  };

  const stopRecording = async () => {
    clearTimeout(audioStreamer.silenceTimer);
    audioStreamer.isSilenceTimerActive = false;
    audioStreamer.stopRecording();
    await createMoment();
  };

  const handlePress = item => {
    navigation.navigate('Moment Details', {
      title: item.title,
      summary: item.summary,
      transcript: item.text,
      actionItems: item.actionItems,
    });
  };

  return (
    <GestureHandlerRootView style={{flex: 1}}>
      <View style={styles.container}>
        <Button
          title={isRecording ? 'Stop' : 'Record'}
          onPress={isRecording ? stopRecording : startRecording}
          buttonStyle={styles.recordButton}
        />
        <View style={styles.transcriptContainer}>
          <Text style={styles.transcriptText}>{streamingTranscript}</Text>
        </View>
        <FlatList
          data={moments}
          keyExtractor={(item, index) => index.toString()}
          renderItem={({item}) => (
            <MomentListItem item={item} onItemPress={handlePress} />
          )}
          style={{flex: 1}}
        />
      </View>
    </GestureHandlerRootView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F5FCFF',
  },
  contentContainer: {
    justifyContent: 'center',
    alignItems: 'center',
  },
  recordButton: {
    padding: 20,
    backgroundColor: 'red',
    borderRadius: 50,
  },
  buttonText: {
    color: '#FFFFFF',
    fontSize: 20,
  },
  transcriptContainer: {
    marginTop: 20,
    padding: 10,
    borderWidth: 1,
    borderColor: '#cccccc',
    borderRadius: 5,
    backgroundColor: '#ffffff',
    shadowColor: '#000',
    shadowOffset: {width: 0, height: 1},
    shadowOpacity: 0.2,
    shadowRadius: 1.41,
    elevation: 2,
  },

  transcriptText: {
    fontSize: 16,
  },
});

export default MomentsTab;
