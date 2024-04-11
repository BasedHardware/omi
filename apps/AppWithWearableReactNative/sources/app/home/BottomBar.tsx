import * as React from 'react';
import { Pressable, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Theme } from '../../theme';

const TabBarItem = React.memo((props: { icon: string, active: boolean, onPress: () => void }) => {
    return (
        <Pressable style={{ flexGrow: 1, flexBasis: 0, justifyContent: 'center', alignItems: 'center' }} onPress={props.onPress}>
            <Ionicons name={props.icon as any} size={24} color="black" />
            {props.active && <View style={{ width: 6, height: 6, borderRadius: 4, backgroundColor: Theme.accent, marginTop: 4, position: 'absolute', bottom: 10 }}></View>}
        </Pressable>
    )
});

const ActionBarItem = React.memo((props: { icon: string, kind: 'normal' | 'warning' | 'active', onPress: () => void }) => {
    return (
        <Pressable style={{ flexGrow: 1, flexBasis: 0, justifyContent: 'center', alignItems: 'center' }} onPress={props.onPress}>
            <Ionicons name={props.icon as any} size={48} color={props.kind === 'warning' ? Theme.accent : (props.kind === 'active' ? 'blue' : 'black')} />
        </Pressable>
    );
});

export const BottomBar = React.memo((props: {
    onPress: (page: 'home' | 'search' | 'sessions' | 'settings') => void,
    active: 'home' | 'search' | 'sessions' | 'settings',
    actionIcon: string,
    actionStyle: 'normal' | 'warning' | 'active'
    onActionPress: () => void
}) => {
    return (
        <View style={{ height: 64, flexDirection: 'row', alignItems: 'stretch' }}>
            <TabBarItem icon="aperture" active={props.active === 'home'} onPress={() => props.onPress('home')} />
            {/* <TabBarItem icon="search" active={props.active === 'search'} onPress={() => props.onPress('search')} /> */}
            <ActionBarItem icon={props.actionIcon} kind={props.actionStyle} onPress={props.onActionPress} />
            {/* <TabBarItem icon="stats-chart" active={props.active === 'sessions'} onPress={() => props.onPress('sessions')} /> */}
            <TabBarItem icon="settings" active={props.active === 'settings'} onPress={() => props.onPress('settings')} />
        </View>
    );
});