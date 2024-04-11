import * as React from 'react';
import { Alert, KeyboardAvoidingView, Text, TextInput, View } from 'react-native';
import { useRouter } from '../../routing';
import { Theme } from '../../theme';
import * as RNLocalize from "react-native-localize";
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { parsePhoneNumber } from 'libphonenumber-js';
import { Country, countries } from '../../utils/countries';
import { SButton } from '../components/SButton';
import { useHappyAction } from '../helpers/useHappyAction';
import { requestPhoneAuth } from '../../modules/api/auth';

export const PhoneScreen = React.memo(() => {

    const router = useRouter();
    const safeArea = useSafeAreaInsets();

    // Fields
    const inputRef = React.useRef<TextInput>(null);
    const defaultCountry = React.useMemo(() => {
        let c = RNLocalize.getCountry().toLowerCase();
        let country = countries.find((v) => v.shortname.toLowerCase() === c)
        if (!country) {
            country = countries.find((v) => v.shortname.toLowerCase() === 'us')
        }
        return country!;
    }, []);
    const [country, setCountry] = React.useState(defaultCountry);
    const [number, setNumber] = React.useState('');

    // Actions
    const [requesting, doRequest] = useHappyAction(async () => {
        let val = country.value + ' ' + number;
        await requestPhoneAuth(val, '');
        router.navigate('code', { number: val });
    });
    const openCountryPicker = React.useCallback(() => {
        router.navigate('country', {
            current: country,
            callback: (item: Country) => {
                setCountry(item);
            }
        });
    }, [country]);
    const setNumberValue = React.useCallback((src: string) => {
        if (requesting) {
            return;
        }
        try {
            const parsed = parsePhoneNumber(src);
            if (parsed && parsed.countryCallingCode) {
                let ex: Country | undefined;
                if ('+' + parsed.countryCallingCode === defaultCountry.value) {
                    ex = defaultCountry;
                } else if (parsed.countryCallingCode === '1') {
                    ex = countries.find((v) => v.shortname === 'US');
                } else if (parsed.countryCallingCode === '7') {
                    ex = countries.find((v) => v.shortname === 'RU');
                } else {
                    ex = countries.find((v) => v.value === '+' + parsed.countryCallingCode);
                }
                if (ex) {
                    setCountry(ex);
                    setNumber(parsed.nationalNumber);
                    return;
                }
            }
        } catch (e) {
            // Ignore
        }
        setNumber(src);
    }, [requesting]);

    return (
        <View style={{ flexGrow: 1, backgroundColor: Theme.background }}>
            <KeyboardAvoidingView
                style={{ flexGrow: 1, alignItems: 'center', flexDirection: 'column', paddingHorizontal: 32, marginBottom: safeArea.bottom }}
                behavior="padding"
                keyboardVerticalOffset={safeArea.top + 44}
            >
                <View style={{ justifyContent: 'space-between', flexGrow: 1, flexBasis: 0, alignSelf: 'stretch' }}>
                    <View />
                    <View>
                        <Text style={{ fontSize: 36, alignSelf: 'center', marginBottom: 8 }}>Your Phone</Text>
                        <Text style={{ fontSize: 22, color: Theme.text, alignSelf: 'center', lineHeight: 30 }}>Please, confirm your country code</Text>
                        <Text style={{ fontSize: 22, color: Theme.text, alignSelf: 'center', lineHeight: 30 }}>and enter your phone number.</Text>
                        <SButton title={country.label + ' ' + country.emoji} style={{ alignSelf: 'stretch', marginTop: 48, marginBottom: 12 }} onPress={openCountryPicker} disabled={requesting} />
                        <View style={{ height: 50, backgroundColor: '#F2F2F2', alignSelf: 'stretch', flexDirection: 'row', borderRadius: 8 }}>
                            <View style={{ marginLeft: 4, width: 60, height: 50, justifyContent: 'center', alignItems: 'center' }}>
                                <Text style={{ fontSize: 17, fontWeight: '600', opacity: 0.4 }}>
                                    {country.value}
                                </Text>
                            </View>
                            <TextInput
                                ref={inputRef}
                                placeholder='Phone number'
                                keyboardType='phone-pad'
                                value={number}
                                onChangeText={setNumberValue}
                                style={{
                                    height: 50,
                                    paddingLeft: 64,
                                    paddingRight: 16,
                                    fontSize: 17,
                                    fontWeight: '500',
                                    position: 'absolute',
                                    left: 0,
                                    right: 0,
                                    top: 0,
                                    bottom: 0,
                                }}
                            />
                        </View>
                    </View>
                    <SButton title='Continue' style={{ alignSelf: 'stretch', marginTop: 48, paddingBottom: 16 }} onPress={doRequest} loading={requesting} />
                </View>
            </KeyboardAvoidingView>
        </View>
    );
});