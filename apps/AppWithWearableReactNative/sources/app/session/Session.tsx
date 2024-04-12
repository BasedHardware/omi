import * as React from 'react';
import { ActivityIndicator, ScrollView, Text, View } from 'react-native';
import { Theme } from '../../theme';
import { useRoute } from '@react-navigation/native';
import { useAppModel } from '../../global';
import humanizeDuration from 'humanize-duration';

export const SessionScreen = React.memo(() => {
    let id = (useRoute().params as any).id as string;
    let appModel = useAppModel();
    let session = appModel.sessions.useFull(id);
    if (!session) {
        return (
            <View style={{ flexGrow: 1, flexBasis: 0, justifyContent: 'center', alignItems: 'center' }}>
                <ActivityIndicator size="large" color={Theme.accent} />
            </View>
        )
    }
    return (
        <ScrollView style={{ backgroundColor: Theme.background }}>
            <Text>Session #{session.index}</Text>
            <Text>State: {session.state}</Text>
            {session.audio ? <Text>Duration: {humanizeDuration(session.audio.duration, { units: ["h", "m", "s", "ms"] })}</Text> : null}
            {session.text ? (
                <>
                    <Text>Text:</Text>
                    <Text>{session.text}</Text>
                </>
            ) : (
                <Text>Text: Processing...</Text>
            )}
        </ScrollView>
    );
});