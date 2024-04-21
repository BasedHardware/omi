import React, { useState } from 'react';
import { View, StyleSheet, Text, TouchableOpacity } from 'react-native';
import AudioStream from 'react-native-live-audio-stream';

const options = {
    sampleRate: 44100, // sample rate
    channels: 1, // number of channels
    bitsPerSample: 16, // bit rate
    audioSource: 6, // android only (see below)
    bufferSize: 4096, // buffer size (default to 2048)
};

const RecordTab = () => {
    const [isRecording, setIsRecording] = useState(false);
    const [transcribedText, setTranscribedText] = useState('');

    const startRecording = async () => {
        try {
            AudioStream.init(options);
            AudioStream.on('data', (data) => {
                // Handle live audio stream data here
            });
            await AudioStream.start();
            setIsRecording(true);
        } catch (error) {
            console.error('Failed to start recording', error);
        }
    };

    const stopRecording = async () => {
        try {
            await AudioStream.stop();
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
                style={styles.recordButton}
            >
                <Text style={styles.buttonText}>
                    {isRecording ? 'Stop' : 'Record'}
                </Text>
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
