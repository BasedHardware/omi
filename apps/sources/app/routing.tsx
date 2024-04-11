import { createNativeStackNavigator } from '@react-navigation/native-stack';
import * as React from 'react';
import { CountryPicker } from './auth/CountryScreen';
import { Splash } from './Splash';
import { PhoneScreen } from './auth/PhoneScreen';
import { CodeScreen } from './auth/CodeScreen';
import { OnboardingState } from '../global';
import { PreUsernameScreen } from './pre/PreUsername';
import { PrePreparingScreen } from './pre/PrePreparing';
import { HomeScreen } from './Home';
import { PreNameScreen } from './pre/PreName';
import { PreNotificationsScreen } from './pre/PreNotifications';
import { PreActivationScreen } from './pre/PreActivation';
import { SessionScreen } from './session/Session';
import { PairingScreen } from './wearable/Pairing';
import { SessionsScreens } from './home/SessionsScreen';

export const Stack = createNativeStackNavigator();

export const App = (
    <>
        <Stack.Screen
            name='home'
            component={HomeScreen}
            options={{ headerShown: false }}
        />
        <Stack.Screen
            name='session'
            component={SessionScreen}
            options={{ title: 'Session' }}
        />
        <Stack.Screen
            name='sessions'
            component={SessionsScreens}
            options={{ title: 'Sessions' }}
        />
        <Stack.Screen
            name='pairing'
            component={PairingScreen}
            options={{ title: 'Connect new device', presentation: 'formSheet' }}
        />
    </>
);

export const Pre = (state: OnboardingState) => {
    if (state.kind === 'prepare') {
        return (
            <Stack.Screen
                name='prepare'
                component={PrePreparingScreen}
                options={{
                    headerShown: false
                }}
            />
        );
    }
    if (state.kind === 'need_username') {
        return (
            <Stack.Screen
                name='need_username'
                component={PreUsernameScreen}
                options={{
                    headerShown: false
                }}
            />
        );
    }
    if (state.kind === 'need_name') {
        return (
            <Stack.Screen
                name='need_name'
                component={PreNameScreen}
                options={{
                    headerShown: false
                }}
            />
        );
    }
    if (state.kind === 'need_push') {
        return (
            <Stack.Screen
                name='need_push'
                component={PreNotificationsScreen}
                options={{
                    headerShown: false
                }}
            />
        );
    }
    if (state.kind === 'need_activation') {
        return (
            <Stack.Screen
                name='need_activation'
                component={PreActivationScreen}
                options={{
                    headerShown: false
                }}
            />
        );
    }
    return null;
}

export const Auth = (
    <>
        <Stack.Screen
            name='splash'
            component={Splash}
            options={{
                headerShown: false
            }}
        />
        <Stack.Screen
            name='phone'
            component={PhoneScreen}
        />
        <Stack.Screen
            name='code'
            component={CodeScreen}
        />
    </>
);

export const Modals = (
    <>
        <Stack.Screen
            name='country'
            component={CountryPicker}
            options={{ headerShown: false }}
        />
    </>
);