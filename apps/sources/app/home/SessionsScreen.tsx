import * as React from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Theme } from '../../theme';
import { useAppModel } from '../../global';
import { useRouter } from '../../routing';

export const SessionsScreens = React.memo(() => {
    const safeArea = useSafeAreaInsets();
    const appModel = useAppModel();
    const sessions = appModel.useSessions();
    const router = useRouter();
    return (
        <View style={{ flexGrow: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: Theme.background }}>
            {sessions === null && (
                <View style={{ flexGrow: 1, alignItems: 'center', justifyContent: 'center', paddingBottom: safeArea.bottom, }}>
                    <ActivityIndicator size="large" color={Theme.accent} />
                </View>
            )}
            {sessions !== null && sessions.length === 0 && (
                <View style={{ flexGrow: 1, paddingBottom: safeArea.bottom, }}>
                    <Text>Press record button to start!</Text>
                </View>
            )}
            {sessions !== null && sessions.length > 0 && (
                <ScrollView style={{ flexGrow: 1, flexBasis: 0, alignSelf: 'stretch' }} contentContainerStyle={{ alignItems: 'stretch', paddingBottom: safeArea.bottom + 64 }}>
                    {sessions.map((session) => (
                        <Pressable
                            key={session.id}
                            style={{
                                backgroundColor: '#eee',
                                marginHorizontal: 16,
                                marginVertical: 8,
                                borderRadius: 16,
                                paddingHorizontal: 16,
                                paddingVertical: 18,
                                flexDirection: 'row'
                            }}
                            onPress={() => { router.navigate('session', { id: session.id }) }}
                        >
                            <Text style={{ color: 'black', fontSize: 24, flexGrow: 1, flexBasis: 0, alignSelf: 'center' }}>Session #{(session.index + 1)}</Text>
                            <Text style={{ color: 'black', alignSelf: 'center' }}>{session.state}</Text>
                            <Text>{session.audio ? (session.audio.duration / 1000).toString() : ''}</Text>
                        </Pressable>
                    ))}
                </ScrollView>
            )}
        </View>
    );
});