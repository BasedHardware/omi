import * as React from 'react';
import { SafeAreaView, StyleSheet, View, Text } from 'react-native';
import { RoundButton } from './components/RoundButton';
import { Theme } from './components/theme';
import { useDevice } from '../modules/useDevice';
import { DeviceView } from './DeviceView';
import { startAudio } from '../modules/openai';

export const Main = React.memo(() => {

    const [device, connectDevice, isAutoConnecting] = useDevice();
    const [isConnecting, setIsConnecting] = React.useState(false);
    const [connectionError, setConnectionError] = React.useState<string | null>(null);
    
    // Handle connection attempt
    const handleConnect = React.useCallback(async () => {
        setIsConnecting(true);
        setConnectionError(null);
        try {
            await connectDevice();
        } catch (error) {
            console.error('Connection error:', error);
            setConnectionError(error instanceof Error ? error.message : 'Connection failed');
        } finally {
            setIsConnecting(false);
        }
    }, [connectDevice]);
    
    return (
        <SafeAreaView style={styles.container}>
            {!device && (
                <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', alignSelf: 'center' }}>
                    {isConnecting ? (
                        <Text style={styles.statusText}>Connecting to OpenGlass...</Text>
                    ) : (
                        <>
                            <RoundButton title="Connect to the device" action={handleConnect} />
                            {connectionError && (
                                <Text style={styles.errorText}>{connectionError}</Text>
                            )}
                        </>
                    )}
                </View>
            )}
            {device && (
                <DeviceView device={device} />
            )}
        </SafeAreaView>
    );
});

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: Theme.background,
        alignItems: 'stretch',
        justifyContent: 'center',
    },
    statusText: {
        color: Theme.text,
        fontSize: 18,
        marginBottom: 16,
    },
    errorText: {
        color: '#ff4444',
        fontSize: 14,
        marginTop: 16,
        textAlign: 'center',
        paddingHorizontal: 20,
    }
});