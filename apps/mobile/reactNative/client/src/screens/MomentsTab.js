import React, {useContext} from 'react';
import {useNavigation} from '@react-navigation/native';
import {View, Text, StyleSheet, FlatList} from 'react-native';
import {Button} from 'react-native-elements';
import {GestureHandlerRootView} from 'react-native-gesture-handler';
import {MomentsContext} from '../contexts/MomentsContext';
import BleManager from 'react-native-ble-manager';
import useAudioStream from '../contexts/useAudioStreamer';
import MomentListItem from '../components/moments/MomentsListItem';

const MomentsTab = () => {
  const {moments} = useContext(MomentsContext);
  const {
    isRecording,
    streamingTranscript,
    stopRecording,
    startRecording,
  } = useAudioStream();

  const navigation = useNavigation();

  const handleStopRecording = async () => {
    stopRecording();
    
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
          onPress={isRecording ? handleStopRecording : startRecording}
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
