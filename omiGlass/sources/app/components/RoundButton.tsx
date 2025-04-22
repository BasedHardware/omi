import * as React from 'react';
import { ActivityIndicator, Platform, Pressable, StyleProp, Text, View, ViewStyle } from 'react-native';
import { iOSUIKit } from 'react-native-typography';
import { Theme } from './theme';

export type RoundButtonSize = 'large' | 'normal' | 'small';
const sizes: { [key in RoundButtonSize]: { height: number, fontSize: number, hitSlop: number, pad: number } } = {
    large: { height: 48, fontSize: 21, hitSlop: 0, pad: Platform.OS == 'ios' ? 0 : -1 },
    normal: { height: 32, fontSize: 16, hitSlop: 8, pad: Platform.OS == 'ios' ? 1 : -2 },
    small: { height: 24, fontSize: 14, hitSlop: 12, pad: Platform.OS == 'ios' ? -1 : -1 }
}

export type RoundButtonDisplay = 'default' | 'inverted';
const displays: { [key in RoundButtonDisplay]: {
    textColor: string,
    backgroundColor: string,
    borderColor: string,
} } = {
    default: {
        backgroundColor: '#fff',
        borderColor: '#fff',
        textColor: 'black'
    },
    inverted: {
        backgroundColor: 'transparent',
        borderColor: 'transparent',
        textColor: Theme.text,
    }
}

export const RoundButton = React.memo((props: { size?: RoundButtonSize, display?: RoundButtonDisplay, title?: any, style?: StyleProp<ViewStyle>, disabled?: boolean, loading?: boolean, onPress?: () => void, action?: () => Promise<any> }) => {
    const [loading, setLoading] = React.useState(false);
    const doLoading = props.loading !== undefined ? props.loading : loading;
    const doAction = React.useCallback(() => {
        if (props.onPress) {
            props.onPress();
            return;
        }
        if (props.action) {
            setLoading(true);
            (async () => {
                try {
                    await props.action!();
                } finally {
                    setLoading(false);
                }
            })();
        }
    }, [props.onPress, props.action]);

    const size = sizes[props.size || 'large'];
    const display = displays[props.display || 'default'];

    return (
        <Pressable
            disabled={doLoading || props.disabled}
            hitSlop={size.hitSlop}
            style={(p) => ([
                {
                    borderWidth: 1,
                    borderRadius: size.height / 2,
                    backgroundColor: display.backgroundColor,
                    borderColor: display.borderColor,
                    opacity: props.disabled ? 0.5 : 1
                },
                {
                    opacity: p.pressed ? 0.9 : 1
                },
                props.style])}
            onPress={doAction}
        >
            <View style={{ height: size.height - 2, alignItems: 'center', justifyContent: 'center', minWidth: 64, paddingHorizontal: 16 }}>
                {doLoading && (
                    <View style={{ position: 'absolute', left: 0, right: 0, bottom: 0, top: 0, alignItems: 'center', justifyContent: 'center' }}>
                        <ActivityIndicator color={display.textColor} size='small' />
                    </View>
                )}
                <Text style={[iOSUIKit.title3, { marginTop: size.pad, opacity: doLoading ? 0 : 1, color: display.textColor, fontSize: size.fontSize, fontWeight: '600', includeFontPadding: false }]} numberOfLines={1}>{props.title}</Text>
            </View>
        </Pressable>
    )
});