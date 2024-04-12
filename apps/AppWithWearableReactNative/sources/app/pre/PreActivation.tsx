import * as React from 'react';
import { Theme } from '../../theme';
import { Text, View } from 'react-native';
import { RoundButton } from '../components/RoundButton';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useClient, useGlobalStateController } from '../../global';

export const PreActivationScreen = React.memo(() => {
    const safeArea = useSafeAreaInsets();
    const controller = useGlobalStateController();
    const client = useClient();
    const action = React.useCallback(async () => {
        await client.preComplete();
        await controller.refresh();
    }, []);
    return (
        <View style={{ flexGrow: 1, backgroundColor: Theme.background, justifyContent: 'center', paddingHorizontal: 32, paddingTop: safeArea.top, paddingBottom: safeArea.bottom }}>
            <View style={{ flexGrow: 1 }} />
            <Text style={{ color: Theme.text, fontSize: 32, alignSelf: 'center', textAlign: 'center' }}>Be respectful</Text>
            <Text style={{ color: Theme.text, fontSize: 20, alignSelf: 'center', textAlign: 'center', marginTop: 32 }}>Please, be respectful to pepole around you and turn off AI when asked.</Text>
            <View style={{ flexGrow: 1 }} />
            <RoundButton title={'Create account'} style={{ width: 250, alignSelf: 'center', marginBottom: 32 }} action={action} />
        </View>
    );
});