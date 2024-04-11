import * as React from 'react';
import { StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Theme } from '../theme';
import { TopBar } from './home/TopBar';
import { BottomBar } from './home/BottomBar';
import { SessionsScreens } from './home/SessionsScreen';
import { MemoriesScreen } from './home/MemoriesScreen';
import { SearchScreen } from './home/SearchScreen';
import { SettingsScreen } from './home/SettingsScreen';
import { storage } from '../storage';
import { useAppModel } from '../global';
import { useAtomValue } from 'jotai';
import { useRouter } from '../routing';

export const HomeScreen = React.memo(() => {
    const safeArea = useSafeAreaInsets();
    const appModel = useAppModel();
    const wearable = appModel.useWearable();
    const capture = useAtomValue(appModel.capture.captureState);
    const router = useRouter();
    const [tab, setTab] = React.useState<'home' | 'search' | 'sessions' | 'settings'>(() => (storage.getString('app-tab') as any) || 'home');
    const onActionPress = () => {

        if (wearable.pairing === 'need-pairing') {
            // Need to reset discovered devices before opening the pairing screent to avoid showing old devices
            appModel.wearable.resetDiscoveredDevices();
            router.navigate('pairing');
        } else if (wearable.pairing === 'denied') {
            // TODO: Handle denied
        } else if (wearable.pairing === 'unavailable') {
            // TODO: Handle unavailable
        } else {
            if (!capture) {
                appModel.capture.start();
            } else {
                appModel.capture.stop();
            }
        }

    }
    const onTabPress = (page: 'home' | 'search' | 'sessions' | 'settings') => {
        storage.set('app-tab', page);
        setTab(page);
    };

    // Action button
    let actionIcon = 'mic-circle-outline';
    let actionStyle: 'normal' | 'warning' | 'active' = 'normal';
    if (wearable.pairing === 'need-pairing') {
        actionIcon = 'bluetooth';
        actionStyle = 'warning';
    } else if (wearable.pairing === 'unavailable' || wearable.pairing === 'denied') {
        actionIcon = 'bluetooth';
        actionStyle = 'warning';
    } else if (wearable.pairing === 'ready') {
        if (!!capture) {
            actionIcon = 'stop-circle-outline';
            actionStyle = 'active';
        } else {
            actionIcon = 'mic-circle-outline';
            actionStyle = 'normal';
        }
    }



    return (
        <View style={[styles.container, { paddingTop: safeArea.top }]}>
            <TopBar />
            <View style={{ flexGrow: 1, flexBasis: 0, flexDirection: 'column', alignItems: 'stretch', alignSelf: 'stretch', display: tab === 'home' ? 'flex' : 'none' }}>
                <MemoriesScreen />
            </View>
            <View style={{ flexGrow: 1, flexBasis: 0, flexDirection: 'column', alignItems: 'stretch', alignSelf: 'stretch', display: tab === 'search' ? 'flex' : 'none' }}>
                <SearchScreen />
            </View>
            <View style={{ flexGrow: 1, flexBasis: 0, flexDirection: 'column', alignItems: 'stretch', alignSelf: 'stretch', display: tab === 'sessions' ? 'flex' : 'none' }}>
                <SessionsScreens />
            </View>
            <View style={{ flexGrow: 1, flexBasis: 0, flexDirection: 'column', alignItems: 'stretch', alignSelf: 'stretch', display: tab === 'settings' ? 'flex' : 'none' }}>
                <SettingsScreen />
            </View>
            <View style={[styles.bottomBar, { height: 64 + safeArea.bottom, paddingBottom: safeArea.bottom }]}>
                <BottomBar active={tab} onPress={onTabPress} actionIcon={actionIcon} onActionPress={onActionPress} actionStyle={actionStyle} />
            </View>
        </View>
    );
});

// const BottomPanel = React.memo(() => {
//     const appModel = useAppModel();
//     const wearable = appModel.useWearable();
//     const capture = useAtomValue(appModel.capture.captureState);
//     const router = useRouter();
//     const doOpenPairing = () => {
//         // Need to reset discovered devices before opening the pairing screent to avoid showing old devices
//         appModel.wearable.resetDiscoveredDevices();
//         router.navigate('pairing');
//     };

//     // Basic pairing statuses
//     if (wearable.pairing === 'loading') {
//         return <ActivityIndicator size="small" color={Theme.accent} />
//     }
//     if (wearable.pairing === 'need-pairing') {
//         return <RoundButton title="Pair new device" onPress={doOpenPairing} />
//     }
//     if (wearable.pairing === 'denied') {
//         return <Text>Bluetooth permission denied</Text>
//     }
//     if (wearable.pairing === 'unavailable') {
//         return <Text>Bluetooth unavailable</Text>
//     }

//     // Handle ready state
//     return (
//         <View style={{ flexGrow: 1, alignSelf: 'stretch', flexDirection: 'row', alignItems: 'center' }}>
//             <View style={{ flexGrow: 1, flexBasis: 0, paddingLeft: 32 }}>
//                 {capture && capture.streaming && (
//                     <Text>Recording...</Text>
//                 )}
//                 {capture && !capture.streaming && (
//                     <Text><Ionicons name="warning-outline" size={18} color="black" />Connecting</Text>
//                 )}
//             </View>
//             <View style={{}}>
//                 {!!capture && (
//                     <RoundButton title="Stop" onPress={() => appModel.capture.stop()} />
//                 )}
//                 {!capture && (
//                     <RoundButton title="Start" onPress={() => appModel.capture.start()} />
//                 )}
//             </View>
//             <View style={{ flexGrow: 1, flexBasis: 0, flexDirection: 'row', justifyContent: 'flex-end', paddingRight: 32 }}>

//             </View>
//         </View>
//     );
// });

const styles = StyleSheet.create({
    container: {
        flexGrow: 1,
        justifyContent: 'center',
        alignItems: 'center',
        backgroundColor: Theme.background
    },
    bottomBar: {
        position: 'absolute',
        left: 0,
        right: 0,
        bottom: 0,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: 'white'
    }
});