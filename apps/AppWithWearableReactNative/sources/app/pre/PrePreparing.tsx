import * as React from 'react';
import { ActivityIndicator, View } from 'react-native';
import { Theme } from '../../theme';
import { useGlobalStateController } from '../../global';
import { backoff } from '../../utils/time';

export const PrePreparingScreen = React.memo(() => {

    // Fetch account data
    const controller = useGlobalStateController();
    React.useEffect(() => {
        let exited = false;
        backoff(async () => {
            if (exited) {
                return;
            }
            await controller.refresh();
        });
        return () => {
            exited = true;
        };
    }, []);

    return (
        <View style={{ flexGrow: 1, backgroundColor: Theme.background, alignSelf: 'stretch', justifyContent: 'center', alignItems: 'center' }}>
            <ActivityIndicator />
        </View>
    );
});