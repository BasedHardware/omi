import React, {useState, useContext, useRef} from 'react';
import {useNavigation} from '@react-navigation/native';
import base64 from 'react-native-base64';
import {View, Text, StyleSheet, FlatList, TouchableOpacity} from 'react-native';
import {GestureHandlerRootView} from 'react-native-gesture-handler';
import LiveAudioStream from 'react-native-live-audio-stream';
import {DEEPGRAM_API_KEY} from '@env';
import {MomentsContext} from '../contexts/MomentsContext';
import MomentListItem from '../components/MomentsListItem';

const MomentsTab = () => {
  const [isRecording, setIsRecording] = useState(false);
  const [streamingTranscript, setStreamingTranscript] = useState('');
  const {moments, setMoments, addMoment} = useContext(MomentsContext);
  const ws = useRef(null);
  const navigation = useNavigation();

  const initWebSocket = () => {
    const model = 'nova-2';
    const language = 'en-US';
    const smart_format = true;
    const encoding = 'linear16';
    const sample_rate = 44100;

    const url = `wss://api.deepgram.com/v1/listen?model=${model}&language=${language}&smart_format=${smart_format}&encoding=${encoding}&sample_rate=${sample_rate}`;
    ws.current = new WebSocket(url, ['token', DEEPGRAM_API_KEY]);

    ws.current.onopen = () => {
      console.log('WebSocket connection opened');
      startStreaming();
    };

    ws.current.onerror = error => {
      console.error('WebSocket error:', error);
    };

    ws.current.onclose = () => {
      console.log('WebSocket connection closed');
    };

    ws.current.onmessage = event => {
      const dataObj = JSON.parse(event.data);
      const transcribedWord = dataObj?.channel?.alternatives?.[0]?.transcript;
      console.log('Transcribed word:', transcribedWord);
      if (transcribedWord) {
        setStreamingTranscript(
          prevTranscript => prevTranscript + ' ' + transcribedWord,
        );
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

      ws.current.send(bytes.buffer);
    });

    // Start recording
    LiveAudioStream.start();
    setIsRecording(true);

    // Used to keep connection to deepgram alive until we explicitly close it
    // We should use the else statement from ws.onmessage as a trigger to start the counter
    // would minimize unnecessary keepalive messages
    setInterval(() => {
      const keepAliveMsg = JSON.stringify({type: 'KeepAlive'});
      ws.current.send(keepAliveMsg);
      console.log('Sent KeepAlive message');
    }, 7000);
  };

  const startRecording = async () => {
    if (!ws.current || ws.current.readyState !== WebSocket.OPEN) {
      initWebSocket(); // Initialize WebSocket if not already open
    } else {
      startStreaming(); // If WebSocket is already open, start streaming directly
    }
  };

  const stopRecording = async () => {
    try {
      LiveAudioStream.stop();
      setIsRecording(false);
      ws.current.send(JSON.stringify({type: 'CloseStream'}));
      console.log('Sent CloseStream message');

      ws.current.close();

      const newMoment = {
        text: streamingTranscript,
        date: new Date(),
      };
      setMoments([...moments, newMoment]);
      await addMoment(newMoment);
      setStreamingTranscript('');
    } catch (error) {
      console.error('Failed to stop recording', error);
    }
  };

  const handlePress = item => {
    console.log('Moment selected:', item);
    navigation.navigate('Moment Details', {
      title: item.title,
      summary: item.summary,
    });
  };

  return (
    <GestureHandlerRootView style={{flex: 1}}>
      <View style={styles.container}>
        <TouchableOpacity
          onPress={isRecording ? stopRecording : startRecording}
          style={styles.recordButton}>
          <Text style={styles.buttonText}>
            {isRecording ? 'Stop' : 'Record'}
          </Text>
        </TouchableOpacity>
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
  },
  transcriptText: {
    fontSize: 16,
  },
});

export default MomentsTab;
