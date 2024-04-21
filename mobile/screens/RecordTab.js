import React, { useState, useEffect } from 'react';
import { View, StyleSheet, Text, TouchableOpacity } from 'react-native';
import { Audio } from 'expo-av';

const RecordTab = () => {
    const [recording, setRecording] = useState();
    const [transcribedText, setTranscribedText] = useState('');

    async function startRecording() {
        try {
            // Check for permissions
            const permission = await Audio.requestPermissionsAsync();
            if (permission.status === 'granted') {
                // Prepare the audio recorder
                await Audio.setAudioModeAsync({
                    allowsRecordingIOS: true,
                    playsInSilentModeIOS: true,
                });
                const { recording } = await Audio.Recording.createAsync(
                    Audio.RECORDING_OPTIONS_PRESET_HIGH_QUALITY
                );
                setRecording(recording);
            } else {
                // Handle permission denied
                console.log('Permission to access microphone was denied');
            }
        } catch (err) {
            console.error('Failed to start recording', err);
        }
    }

    async function stopRecording() {
        setRecording(undefined);
        await recording.stopAndUnloadAsync();
        const uri = recording.getURI();
        console.log('Recording stopped and stored at', uri);
        // Here you would typically handle the audio file, e.g., for transcription
        // setTranscribedText("Transcribed text goes here...");
    }

    return (
        <View style={styles.container}>
            <TouchableOpacity
                onPress={recording ? stopRecording : startRecording}
                style={styles.recordButton}
            >
                <Text style={styles.buttonText}>
                    {recording ? 'Stop' : 'Record'}
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
