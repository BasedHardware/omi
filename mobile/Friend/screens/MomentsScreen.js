import React, {useState, useContext, useEffect} from 'react';
import base64 from 'react-native-base64';
import {View, StyleSheet, Text, TouchableOpacity} from 'react-native';
import LiveAudioStream from 'react-native-live-audio-stream';
import {DEEPGRAM_API_KEY} from '@env';
import axios from 'axios';

import {MomentsContext} from '../contexts/MomentsContext';

const MomentsTab = () => {
  const [isRecording, setIsRecording] = useState(false);
  const {streamingTranscript, buildTranscript} = useContext(MomentsContext);
  let ws; // Define WebSocket at component level

  useEffect(() => {
    // Cleanup WebSocket on component unmount
    return () => {
      if (ws) {
        ws.close();
      }
    };
  }, []);

  const initWebSocket = () => {
    const model = 'nova-2';
    const language = 'en-US';
    const smart_format = true;
    const encoding = 'linear16';
    const sample_rate = 44100;

    const url = `wss://api.deepgram.com/v1/listen?model=${model}&language=${language}&smart_format=${smart_format}&encoding=${encoding}&sample_rate=${sample_rate}`;
    ws = new WebSocket(url, ['token', DEEPGRAM_API_KEY]);

    ws.onopen = () => {
      console.log('WebSocket connection opened');
      startStreaming(); // Start streaming after WebSocket is open
    };

    ws.onerror = error => {
      console.error('WebSocket error:', error);
    };

    ws.onclose = () => {
      console.log('WebSocket connection closed');
    };

    ws.onmessage = event => {
      const dataObj = JSON.parse(event.data);
      const transcribedWord = dataObj?.channel?.alternatives?.[0]?.transcript;
      console.log('Transcribed word:', transcribedWord);
      if (transcribedWord) {
        buildTranscript(transcribedWord);
      } else {
        console.log('Silence detected or transcript not available');
      }
    };
  };

  const startStreaming = () => {
    const options = {
      sampleRate: 44100,
      channels: 1,
      bitsPerSample: 16,
      bufferSize: 4096,
    };

    // Initialize audio stream
    LiveAudioStream.init(options);
    LiveAudioStream.on('data', base64String => {
      const binaryString = base64.decode(base64String);
      const len = binaryString.length;
      const bytes = new Uint8Array(len);
      for (let i = 0; i < len; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }

      ws.send(bytes.buffer);
    });

    // Start recording
    LiveAudioStream.start();
    setIsRecording(true);

    // Used to keep connection to deepgram alive until we explicitly close it
    setInterval(() => {
      const keepAliveMsg = JSON.stringify({type: 'KeepAlive'});
      ws.send(keepAliveMsg);
      console.log('Sent KeepAlive message');
    }, 3000);
  };

  const startRecording = async () => {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      initWebSocket(); // Initialize WebSocket if not already open
    } else {
      startStreaming(); // If WebSocket is already open, start streaming directly
    }
  };

  const stopRecording = async () => {
    try {
      LiveAudioStream.stop();
      setIsRecording(false);

      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({type: 'CloseStream'}));

        axios
          .post('http://localhost:50000/moments', {
            text: streamingTranscript,
          })
          .then(() => {
            console.log('Moment added to the database');
          })
          .catch(error => {
            console.error('Failed to add moment to the database', error);
          });

        ws.close(); // Close WebSocket connection
      }
    } catch (error) {
      console.error('Failed to stop recording', error);
    }
  };

  return (
    <View style={styles.container}>
      <TouchableOpacity
        onPress={isRecording ? stopRecording : startRecording}
        style={styles.recordButton}>
        <Text style={styles.buttonText}>{isRecording ? 'Stop' : 'Record'}</Text>
      </TouchableOpacity>
      <View style={styles.transcriptContainer}>
        <Text style={styles.transcriptText}>{streamingTranscript}</Text>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#F5FCFF',
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
  },
  transcriptText: {
    fontSize: 16,
  },
});

export default MomentsTab;
