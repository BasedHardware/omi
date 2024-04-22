import React, {useState} from 'react';
import {View, StyleSheet, Text, TouchableOpacity} from 'react-native';
import LiveAudioStream from 'react-native-live-audio-stream';
import {createClient, LiveTranscriptionEvents} from '@deepgram/sdk';
import {DEEPGRAM_API_KEY} from '@env';

const RecordTab = () => {
  const [isRecording, setIsRecording] = useState(false);
  const [transcribedText, setTranscribedText] = useState('');

  console.log(DEEPGRAM_API_KEY);
  const startRecording = async () => {
    const options = {
      sampleRate: 44100,
      channels: 1,
      bitsPerSample: 16,
      audioSource: 6,
      bufferSize: 4096,
    };

    try {
      const model = 'nova-2';
      const language = 'en';
      const smart_format = true;
      const encoding = 'pcm_s16le';
      const sample_rate = 44100;

      const url = `wss://api.deepgram.com/v1/listen?access_token=${DEEPGRAM_API_KEY}`;
      const ws = new WebSocket(url);

      ws.onopen = () => {
        console.log('WebSocket connection opened');
        // Initialize your audio stream
        LiveAudioStream.init(options);

        LiveAudioStream.on('data', data => {
          // Send the audio data to the WebSocket server
          ws.send(data);
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
