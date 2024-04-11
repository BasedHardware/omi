import * as React from 'react';
import { Alert, KeyboardAvoidingView, Text, View } from 'react-native';
import * as Haptics from 'expo-haptics';
import { Theme } from '../../theme';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useClient, useGlobalStateController } from '../../global';
import { ShakeInstance, Shaker } from '../components/Shaker';
import { SInput } from '../components/SInput';
import { SButton } from '../components/SButton';
import { useHappyAction } from '../helpers/useHappyAction';
import { alert } from '../helpers/alert';

export const PreNameScreen = React.memo(() => {
    const controller = useGlobalStateController();
    const safeArea = useSafeAreaInsets();
    const client = useClient();
    const [firstName, setFirstName] = React.useState('');
    const firstNameRef = React.useRef<ShakeInstance>(null);
    const [lastName, setLastName] = React.useState('');
    const [requesting, doRequest] = useHappyAction(async () => {
        let f = firstName.trim();
        let l: string | null = lastName.trim();
        if (f.length === 0) { // Check first name
            firstNameRef.current?.shake();
            Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
            return;
        }
        if (l.length === 0) {
            l = null;
        }

        let res = await client.preName(f, l);
        if (!res.ok) {
            if (res.error === 'invalid_name') {
                alert('Error', 'You name is invalid', [{ text: 'OK' }]);
                return;
            }
        } else {
            await controller.refresh(); // This moves to the next screen
        }
    });
    return (
        <View style={{ flexGrow: 1, backgroundColor: Theme.background }}>
            <KeyboardAvoidingView
                style={{ flexGrow: 1, alignItems: 'center', flexDirection: 'column', paddingHorizontal: 32, marginBottom: safeArea.bottom }}
                behavior="padding"
                keyboardVerticalOffset={safeArea.top + 44}
            >
                <View style={{ flexGrow: 1, flexBasis: 0, alignSelf: 'stretch', justifyContent: 'space-between' }}>
                    <View />
                    <View>
                        <Text style={{ fontSize: 36, alignSelf: 'center', marginBottom: 8 }}>Your name</Text>
                        <Text style={{ fontSize: 22, alignSelf: 'center', lineHeight: 30 }}>How your friends should find you?</Text>
                        <Shaker style={{ marginTop: 24 }} ref={firstNameRef}>
                            <SInput placeholder='First Name' value={firstName} onValueChange={setFirstName} />
                        </Shaker>
                        <Shaker style={{ marginTop: 16 }}>
                            <SInput placeholder='Last Name (optional)' value={lastName} onValueChange={setLastName} />
                        </Shaker>
                    </View>
                    <SButton title='Continue' style={{ alignSelf: 'stretch', marginTop: 48, paddingBottom: 16 }} onPress={doRequest} loading={requesting} />
                </View>
            </KeyboardAvoidingView>
        </View>
    );
});