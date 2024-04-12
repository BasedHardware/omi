import * as React from 'react';
import { SafeAreaProvider, initialWindowMetrics } from 'react-native-safe-area-context';
import { NavigationContainer } from '@react-navigation/native';
import { View } from 'react-native';
import { Theme } from './theme';
import { GlobalStateContext, GlobalStateControllerContext, useNewGlobalController } from './global';
import { App, Auth, Modals, Pre, Stack } from './app/routing';
import { Provider } from 'jotai';

export function Boot() {
    const [state, controller] = useNewGlobalController();

    const content = (
        <NavigationContainer>
            <Stack.Navigator
                screenOptions={{
                    headerShadowVisible: false,
                    headerBackTitle: 'Back',
                    headerTintColor: Theme.accent,
                    title: ''
                }}
            >
                {state.kind === 'empty' && Auth}
                {state.kind === 'onboarding' && Pre(state.state)}
                {state.kind === 'ready' && App}
                <Stack.Group screenOptions={{ presentation: 'modal' }}>
                    {Modals}
                </Stack.Group>
            </Stack.Navigator>
        </NavigationContainer>
    );

    return (
        <View style={{ flexGrow: 1, flexBasis: 0, alignSelf: 'stretch' }}>
            <SafeAreaProvider initialMetrics={initialWindowMetrics}>
                <GlobalStateContext.Provider value={state}>
                    <GlobalStateControllerContext.Provider value={controller}>
                        {state.kind === 'ready' && (
                            <Provider store={state.appModel.jotai}>
                                {content}
                            </Provider>
                        )}
                        {state.kind !== 'ready' && (
                            content
                        )}
                    </GlobalStateControllerContext.Provider>
                </GlobalStateContext.Provider>
            </SafeAreaProvider>
        </View>
    );
}