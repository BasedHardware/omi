import * as React from 'react';
import axios from 'axios';
import { storage } from './storage';
import { SuperClient } from './modules/api/client';
import * as Notifications from 'expo-notifications';
import { AppModel } from './modules/state/AppModel';

const ONBOARDING_VERSION = 1; // Increment this to reset onboarding

//
// State
//

export type OnboardingState = {
    kind: 'prepare'
} | {
    kind: 'need_username'
} | {
    kind: 'need_name'
} | {
    kind: 'need_push'
} | {
    kind: 'need_activation'
};

export type GlobalState = {
    kind: 'empty'
} | {
    kind: 'onboarding',
    state: OnboardingState,
    token: string,
    client: SuperClient
} | {
    kind: 'ready',
    token: string,
    client: SuperClient,
    appModel: AppModel
};

export const GlobalStateContext = React.createContext<GlobalState>({ kind: 'empty' });

export function useGlobalState() {
    return React.useContext(GlobalStateContext);
}

export function useClient() {
    let state = useGlobalState();
    if (state.kind === 'empty') {
        throw new Error('GlobalState is empty');
    }
    return state.client;
}

export function useAppModel() {
    let state = useGlobalState();
    if (state.kind !== 'ready') {
        throw new Error('GlobalState is not ready');
    }
    return state.appModel;
};

//
// Controller
//

export type GlobalStateController = {
    login(token: string): void,
    logout(): void,
    refresh(): Promise<void>,
};

export const GlobalStateControllerContext = React.createContext<GlobalStateController | null>(null);

export function useGlobalStateController() {
    const controller = React.useContext(GlobalStateControllerContext);
    if (!controller) {
        throw new Error('GlobalStateControllerContext not found');
    }
    return controller;
}

//
// Storage
//

export function storeToken(token: string) {
    storage.set('token', token);
}

export function clearToken() {
    storage.delete('token');
}

export function getToken() {
    return storage.getString('token');
}

export function onboardingMarkCompleted() {
    storage.set('onboarding:completed', ONBOARDING_VERSION);
}

export function isOnboardingCompleted() {
    return storage.getNumber('onboarding:completed') === ONBOARDING_VERSION;
}

export function resetOnboardingState() {
    storage.delete('onboarding:completed');
    storage.delete('onboarding:skip_notifications');
}

export function markSkipNotifications() {
    storage.set('onboarding:skip_notifications', true);
}

export function isSkipNotifications() {
    return storage.getBoolean('onboarding:skip_notifications');
}

//
// Implementation
//

async function refreshOnboarding(client: SuperClient): Promise<OnboardingState | null> {

    // Load server state
    let serverState = await client.fetchPreState();
    if (serverState.needUsername) {
        return { kind: 'need_username' };
    }
    if (serverState.needName) {
        return { kind: 'need_name' };
    }

    // Request notifications
    let notificationPermissions = await Notifications.getPermissionsAsync();
    if (notificationPermissions.status === 'undetermined' && !isSkipNotifications() && notificationPermissions.canAskAgain) {
        return { kind: 'need_push' };
    }

    // In the end require activation
    if (serverState.canActivate) {
        return { kind: 'need_activation' };
    }

    // All requirements satisfied
    return null;
}

export function useNewGlobalController(): [GlobalState, GlobalStateController] {

    // Global state handler
    const [state, setState] = React.useState<GlobalState>(() => {

        // Check if we have a token
        let token = getToken();
        if (!token) {
            return { kind: 'empty' };
        }

        // Create client with tokenq
        let client = new SuperClient(axios.create({
            baseURL: 'https://super-server.korshakov.org',
            headers: {
                Authorization: `Bearer ${token}`,
            },
        }), token);

        // If onboarding is completed - we are ready
        if (isOnboardingCompleted()) {
            return {
                kind: 'ready',
                token: token,
                client,
                appModel: new AppModel(client)
            };
        }

        // If onboarding is not completed - we need to load fresh state from the server
        return {
            kind: 'onboarding',
            token: token,
            state: { kind: 'prepare' },
            client
        };
    });

    // Controller
    const controller = React.useMemo<GlobalStateController>(() => {
        let currentState = state;
        return {
            login(token) {

                // Reset persistence
                storeToken(token);
                resetOnboardingState();

                // Create client
                let client = new SuperClient(axios.create({
                    baseURL: 'https://super-server.korshakov.org',
                    headers: {
                        Authorization: `Bearer ${token}`,
                    },
                }), token);

                // Update state
                currentState = {
                    kind: 'onboarding',
                    token: token,
                    state: { kind: 'prepare' },
                    client
                };
                setState(currentState);
            },
            logout() {

                // Reset persistence
                clearToken();
                resetOnboardingState();

                // Update state
                currentState = {
                    kind: 'empty'
                };
                setState(currentState);
            },
            refresh: async () => {
                if (currentState.kind === 'empty') { // Why?
                    return;
                }

                // Fetch onboarding state
                const onboardingState = await refreshOnboarding(currentState.client);

                // Requirements satisfied
                if (!onboardingState) {
                    onboardingMarkCompleted();
                    currentState = {
                        kind: 'ready',
                        token: currentState.token,
                        client: currentState.client,
                        appModel: new AppModel(currentState.client)
                    };
                    setState(currentState);
                    return;
                }

                // Update state with new onboarding state
                currentState = {
                    kind: 'onboarding',
                    token: currentState.token,
                    state: onboardingState,
                    client: currentState.client
                };
                setState(currentState);
            },
        } satisfies GlobalStateController;
    }, []);

    return [state, controller];
}