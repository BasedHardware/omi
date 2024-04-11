import * as React from 'react';
import { ActivityIndicator, ScrollView, Text, View } from 'react-native';
import { Theme } from '../../theme';
import { useAppModel } from '../../global';
import { useAtomValue } from 'jotai';
import { RoundButton } from '../components/RoundButton';

export const PairingScreen = React.memo(() => {
    const appModel = useAppModel();
    const wearable = useAtomValue(appModel.wearable.discoveryStatus);
    React.useEffect(() => {
        appModel.wearable.startDiscovery();
        return () => {
            appModel.wearable.stopDiscrovery();
        };
    }, []);
    const devices = wearable?.devices ?? [];

    return (
        <View style={{ flexGrow: 1, backgroundColor: Theme.background }}>
            <Text style={{ paddingHorizontal: 16, paddingVertical: 16, fontSize: 24 }}>Discovered devices</Text>
            {devices.length === 0 && (
                <View style={{ flexGrow: 1 }}>
                    <ActivityIndicator />
                </View>
            )}
            {devices.length > 0 && (
                <ScrollView style={{ flexGrow: 1, alignSelf: 'stretch' }} contentContainerStyle={{ padding: 16, paddingBottom: 128 }}>
                    {devices.map((device) => (
                        <RoundButton key={device.id} title={device.name} action={() => appModel.wearable.tryPairDevice(device.id)} />
                    ))}
                </ScrollView>
            )}
        </View>
    );
});