import * as React from 'react';
import { Pressable, Text, View } from 'react-native';
import { useRouter } from '../../routing';

export const SettingsScreen = React.memo(() => {
    const router = useRouter();
    return (
        <View>
            <Text>Settings</Text>
            <Pressable
                style={{
                    backgroundColor: '#eee',
                    marginHorizontal: 16,
                    marginVertical: 8,
                    borderRadius: 16,
                    paddingHorizontal: 16,
                    paddingVertical: 18,
                    flexDirection: 'row'
                }}
                onPress={() => { router.navigate('sessions') }}
            >
                <Text style={{ color: 'black', fontSize: 24, flexGrow: 1, flexBasis: 0, alignSelf: 'center' }}>Sessions</Text>
            </Pressable>
        </View>
    );
});