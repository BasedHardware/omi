import React, {useState} from 'react';
import base64 from 'react-native-base64';
import {View, StyleSheet, Text, TouchableOpacity} from 'react-native';
import LiveAudioStream from 'react-native-live-audio-stream';
import {DEEPGRAM_API_KEY} from '@env';

const RecordTab = () => {
  const [isRecording, setIsRecording] = useState(false);
  const [transcribedText, setTranscribedText] = useState('');

  const startRecording = async () => {
    const options = {
      sampleRate: 44100,
      channels: 1,
      bitsPerSample: 16,
      bufferSize: 4096,
    };

    try {
      const model = 'nova-2';
      const language = 'en-US';
      const smart_format = true;
      const encoding = 'linear16';
      const sample_rate = 44100;

      const url = `wss://api.deepgram.com/v1/listen?model=${model}&language=${language}&smart_format=${smart_format}&encoding=${encoding}&sample_rate=${sample_rate}`;
      const ws = new WebSocket(url, ['token', DEEPGRAM_API_KEY]);

      ws.onopen = () => {
        console.log('WebSocket connection opened');
        // Initialize your audio stream
        LiveAudioStream.init(options);

        LiveAudioStream.on('data', base64String => {
          // Decode base64 string to binary data
          const binaryString = base64.decode(base64String);
          const len = binaryString.length;
          const bytes = new Uint8Array(len);
          for (let i = 0; i < len; i++) {
            bytes[i] = binaryString.charCodeAt(i);
          }

          // Now, bytes is an ArrayBuffer that can be sent via WebSocket
          ws.send(bytes.buffer);
        });

        // Start recording
        LiveAudioStream.start();
        setIsRecording(true);
      };

      ws.onmessage = event => {
        // Handle the transcription data here
        console.log('Transcription data:', event.data);
      };

      ws.onerror = error => {
        console.error('WebSocket error:', error);
      };

      ws.onclose = () => {
        console.log('WebSocket connection closed');
      };
    } catch (error) {
      console.error('Failed to start recording', error);
    }
  };

  const stopRecording = async () => {
    try {
      LiveAudioStream.stop();
      setIsRecording(false);
      // Handle the stop recording logic here, like saving the file if needed
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
      <View style={styles.transcriptionContainer}>
        <Text style={styles.transcriptionText}>{transcribedText}</Text>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'space-around',
  },
  recordButton: {
    width: 100,
    height: 100,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: 'red',
    borderRadius: 50,
  },
  buttonText: {
    color: 'white',
    fontSize: 18,
  },
  transcriptionContainer: {
    width: '80%',
    alignItems: 'center',
  },
  transcriptionText: {
    color: 'black',
    fontSize: 16,
    textAlign: 'center',
  },
});

export default RecordTab;
