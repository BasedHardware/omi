import * as React from 'react';
import { KeyboardTypeOptions, Platform, ReturnKeyTypeOptions, StyleProp, View, ViewStyle, Text, TextInput } from 'react-native';

export interface SInputProps {
    style?: StyleProp<ViewStyle>;
    placeholder?: string;
    autoCapitalize?: 'none' | 'sentences' | 'words' | 'characters';
    autoCorrect?: boolean;
    keyboardType?: KeyboardTypeOptions;
    returnKeyType?: ReturnKeyTypeOptions;
    autoComplete?:
    | 'cc-csc'
    | 'cc-exp'
    | 'cc-exp-month'
    | 'cc-exp-year'
    | 'cc-number'
    | 'email'
    | 'name'
    | 'password'
    | 'postal-code'
    | 'street-address'
    | 'tel'
    | 'username'
    | 'off';
    value?: string;
    onValueChange?: (value: string) => void;
    autoFocus?: boolean;
    multiline?: boolean;
    textContentType?:
    | 'none'
    | 'URL'
    | 'addressCity'
    | 'addressCityAndState'
    | 'addressState'
    | 'countryName'
    | 'creditCardNumber'
    | 'emailAddress'
    | 'familyName'
    | 'fullStreetAddress'
    | 'givenName'
    | 'jobTitle'
    | 'location'
    | 'middleName'
    | 'name'
    | 'namePrefix'
    | 'nameSuffix'
    | 'nickname'
    | 'organizationName'
    | 'postalCode'
    | 'streetAddressLine1'
    | 'streetAddressLine2'
    | 'sublocality'
    | 'telephoneNumber'
    | 'username'
    | 'password'
    | 'newPassword'
    | 'oneTimeCode';

    prefix?: string
}

export const SInput = React.memo((props: SInputProps) => {
    return (
        <View style={[{
            backgroundColor: '#F2F2F2',
            borderRadius: 12,
            paddingHorizontal: 16,
            flexDirection: 'row',
        }, props.style]}>
            {props.prefix && (
                <Text
                    numberOfLines={1}
                    style={{
                        marginTop: 3,
                        fontSize: 17,
                        fontWeight: '400',
                        alignSelf: 'center',
                        color: '#9D9FA3',
                    }}
                >
                    {props.prefix}
                </Text>
            )}
            <TextInput
                style={{
                    height: props.multiline ? 44 * 3 : 48,
                    paddingTop: props.multiline ? 12 : 10,
                    paddingBottom: props.multiline ? 14 : (Platform.OS === 'ios' ? 12 : 10),
                    flexGrow: 1,
                    fontSize: 17,
                    lineHeight: 22,
                    fontWeight: '400',
                    textAlignVertical: props.multiline ? 'top' : 'center'
                }}
                autoFocus={props.autoFocus}
                placeholder={props.placeholder}
                placeholderTextColor="#9D9FA3"
                autoCapitalize={props.autoCapitalize}
                autoCorrect={props.autoCorrect}
                keyboardType={props.keyboardType}
                returnKeyType={props.returnKeyType}
                autoComplete={props.autoComplete}
                multiline={props.multiline}
                value={props.value}
                textContentType={props.textContentType}
                onChangeText={props.onValueChange}
            />
        </View>
    )
});