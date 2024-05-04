import {useState, useRef, useEffect, useContext} from 'react';
import jsTokens from 'js-tokens';
import {DEEPGRAM_API_KEY} from '@env';
import {BluetoothContext} from './BluetoothContext';
import {MomentsContext} from './MomentsContext';
import LiveAudioStream from 'react-native-live-audio-stream';
import base64 from 'react-native-base64';
import BleManager from 'react-native-ble-manager';

const useAudioStream = () => {
  const [isRecording, setIsRecording] = useState(false);
  const [streamingTranscript, setStreamingTranscript] = useState('');
  const [lastWasSilence, setLastWasSilence] = useState(true);
  const [tokenCount, setTokenCount] = useState(0);
  const ws = useRef(null);
  const currentMomentRef = useRef(null);
  const silenceTimer = useRef(null);
  const {bleManagerEmitter} = useContext(BluetoothContext);
  const {setMoments, addMoment, updateMoment} = useContext(MomentsContext);
  const serviceUUID = '19B10000-E8F2-537E-4F6C-D104768A1214';
  const audioCharacteristicUUID = '19B10001-E8F2-537E-4F6C-D104768A1214';

  useEffect(() => {
    // Add listener for Bluetooth data updates
    bleManagerEmitter.addListener(
      'BleManagerDidUpdateValueForCharacteristic',
      handleUpdateValueForCharacteristic,
    );

    return () => {
      clearTimeout(silenceTimer.current);
      bleManagerEmitter.removeAllListeners(
        'BleManagerDidUpdateValueForCharacteristic',
      );
      if (ws.current) {
        ws.current.close();
      }
    };
  }, []);

  const countTokens = text => {
    const token_count = Array.from(jsTokens(text)).length;
    console.log('Counting tokens', token_count);
    return token_count;
  };

  const createOrUpdateMoment = async transcript => {
    if (currentMomentRef.current) {
      console.log('Updating moment', transcript);
      try {
        const momentId = currentMomentRef.current.id;
        await updateMoment({id: momentId, transcript});
      } catch (error) {
        console.error('Error updating moment', error);
      }
    } else {
      console.log('Creating new moment', transcript);
      try {
        const newMoment = {
          transcript,
          date: new Date(),
        };
        await addMoment(newMoment);
        currentMomentRef.current = newMoment;
      } catch (error) {
        console.error('Error creating moment', error);
      }
    }
  };

  // This is the function responsible for handling the data received from the Bluetooth device
  const handleUpdateValueForCharacteristic = data => {
    // data.value is an array that looks to be in PCM8 format
    const array = new Uint8Array(data.value);
    ws.current.send(array.buffer);
  };

  const resetSilenceTimer = transcript => {
    clearTimeout(silenceTimer.current);
    silenceTimer.current = setTimeout(() => {
      createMoment(transcript);
      setLastWasSilence(true);
      setStreamingTranscript('');
    }, 5000);
  };

  const startRecording = async () => {
    // Check for connected Bluetooth peripherals
    const connectedPeripherals = await BleManager.getConnectedPeripherals([
      serviceUUID,
    ]);
    if (connectedPeripherals.length > 0) {
      // If theres a connected device then we stream from it
      initWebSocket(connectedPeripherals[0].id);
    } else {
      // If no connected device then we stream from phone
      initWebSocket();
    }
  };

  const initWebSocket = async peripheralId => {
    const model = 'nova-2';
    const language = 'en-US';
    const smart_format = true;
    const encoding = 'linear16';
    const sample_rate = 8000;

    const url = `wss://api.deepgram.com/v1/listen?model=${model}&language=${language}&smart_format=${smart_format}&encoding=${encoding}&sample_rate=${sample_rate}`;
    ws.current = new WebSocket(url, ['token', DEEPGRAM_API_KEY]);

    ws.current.onopen = () => {
      console.log('WebSocket connection opened');
      if (peripheralId) {
        startBluetoothStreaming(peripheralId);
      } else {
        startPhoneStreaming();
      }
    };
    ws.current.onmessage = event => {
      const dataObj = JSON.parse(event.data);
      const transcribedWord = dataObj?.channel?.alternatives?.[0]?.transcript;
      if (transcribedWord) {
        const tokens = countTokens(transcribedWord);
        setTokenCount(prev => prev + tokens);
        setStreamingTranscript(prev => {
          const updatedTranscript = prev + ' ' + transcribedWord;
          if (lastWasSilence) {
            resetSilenceTimer(updatedTranscript);
            setLastWasSilence(false);
          }
          return updatedTranscript;
        });

        if (tokenCount >= 500) {
          createOrUpdateMoment(streamingTranscript);
          setStreamingTranscript('');
          setTokenCount(0);
        }
        
      } else {
        console.log('Silence detected');
        if (!lastWasSilence) {
          resetSilenceTimer();
          setLastWasSilence(true);
        }
      }
    };
  };

  const startPhoneStreaming = () => {
    const options = {
      sampleRate: 8000,
      channels: 1,
      bitsPerSample: 16,
      bufferSize: 4096,
    };
    LiveAudioStream.init(options);
    LiveAudioStream.on('data', base64String => {
      const binaryString = base64.decode(base64String);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }
      ws.current.send(bytes.buffer);
    });
    LiveAudioStream.start();
    setIsRecording(true);
  };

  const stopRecording = () => {
    LiveAudioStream.stop();
    if (ws.current) {
      ws.current.send(JSON.stringify({type: 'CloseStream'}));
      ws.current.close();
    }
    setIsRecording(false);

    if (streamingTranscript) {
      createMoment(streamingTranscript);
      setStreamingTranscript('');
    }
  };

  const startBluetoothStreaming = peripheralId => {
    BleManager.startNotification(
      peripheralId,
      serviceUUID,
      audioCharacteristicUUID,
    )
      .then(() => {
        console.log('Started notification on ' + serviceUUID);
        setIsRecording(true);
      })
      .catch(error => {
        console.log('Notification error', error);
      });
  };

  const createMoment = async transcript => {
    console.log('Creating moment', transcript);
    try {
      const newMoment = {
        transcript,
        date: new Date(),
      };

      addMoment(newMoment);

      setMoments(currentMoments => [...currentMoments, newMoment]);
    } catch (error) {
      console.error('Error creating moment', error);
    }
  };

  return {
    isRecording,
    streamingTranscript,
    initWebSocket,
    stopRecording,
    createMoment,
    startRecording,
  };
};

export default useAudioStream;
