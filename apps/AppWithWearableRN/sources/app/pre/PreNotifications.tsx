import * as React from 'react';
import { Text, View } from 'react-native';
import { Theme } from '../../theme';
import { markSkipNotifications, useGlobalStateController } from '../../global';
import * as Notifications from 'expo-notifications';
import { RoundButton } from '../components/RoundButton';

export const PreNotificationsScreen = React.memo(() => {
    const controller = useGlobalStateController();
    const action = React.useCallback(async () => {
        await Notifications.requestPermissionsAsync();
        await controller.refresh();
    }, []);
    const skip = React.useCallback(async () => {
        markSkipNotifications();
        await controller.refresh();
    }, []);
    return (
        <View style={{ flexGrow: 1, backgroundColor: Theme.background, justifyContent: 'center' }}>
            <Text style={{ color: Theme.text, fontSize: 32, alignSelf: 'center', textAlign: 'center' }}>Super works best{'\n'}with notifications on</Text>
            <RoundButton title={'Enable notifications'} style={{ width: 250, alignSelf: 'center', marginTop: 32 }} action={action} />
            <RoundButton title={'Not now'} style={{ width: 250, alignSelf: 'center', marginTop: 32 }} action={skip} />
        </View>
    );
});