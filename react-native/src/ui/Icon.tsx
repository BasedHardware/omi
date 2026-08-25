import React from 'react';
import {
  Platform,
  type StyleProp,
  type ViewProps,
  type ViewStyle,
} from 'react-native';
import {requireNativeComponent} from '../native-component';
import {tokens} from './tokens';

type OmiSFSymbolProps = ViewProps & {
  symbolColor?: string;
  symbolName: string;
  symbolSize?: number;
};

export type IconComponent = React.ComponentType<{
  accessibilityLabel?: string;
  accessible?: boolean;
  color?: string;
  size?: number;
  strokeWidth?: number;
  style?: StyleProp<ViewStyle>;
}>;

export type IconProps = {
  accessibilityLabel?: string;
  accessible?: boolean;
  color?: string;
  fallback: IconComponent;
  size?: number;
  strokeWidth?: number;
  style?: StyleProp<ViewStyle>;
  symbolColor?: string;
  symbolName: string;
};

const OmiSFSymbol = requireNativeComponent<OmiSFSymbolProps>('OmiSFSymbol');

export function Icon({
  accessibilityLabel,
  accessible = accessibilityLabel !== undefined,
  color = tokens.color.text,
  fallback: Fallback,
  size = tokens.size.icon,
  strokeWidth = tokens.icon.strokeWidth,
  style,
  symbolColor,
  symbolName,
}: IconProps) {
  const resolvedColor = symbolColor ?? color;
  if (Platform.OS === 'macos') {
    return (
      <OmiSFSymbol
        accessibilityLabel={accessibilityLabel}
        accessible={accessible}
        symbolColor={resolvedColor}
        symbolName={symbolName}
        symbolSize={size}
        style={[{height: size, width: size}, style]}
      />
    );
  }

  return (
    <Fallback
      accessibilityLabel={accessibilityLabel}
      accessible={accessible}
      color={resolvedColor}
      size={size}
      strokeWidth={strokeWidth}
      style={style}
    />
  );
}
