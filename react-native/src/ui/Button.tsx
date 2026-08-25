import React from 'react';
import {
  type PressableProps,
  type StyleProp,
  StyleSheet,
  Text,
  type TextStyle,
} from 'react-native';
import {FocusPressable} from './Pressable';
import {tokens} from './tokens';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
export type ButtonSize = 'compact' | 'default' | 'large' | 'icon';

export type ButtonProps = Omit<PressableProps, 'children' | 'style'> & {
  children: React.ReactNode;
  labelStyle?: StyleProp<TextStyle>;
  size?: ButtonSize;
  style?: PressableProps['style'];
  variant?: ButtonVariant;
};

export function Button({
  accessibilityRole = 'button',
  accessibilityState,
  children,
  disabled = false,
  labelStyle,
  size = 'default',
  style,
  variant = 'primary',
  ...props
}: ButtonProps) {
  const isDisabled = disabled === true;
  const content =
    typeof children === 'string' || typeof children === 'number' ? (
      <Text
        style={[
          styles.label,
          variant === 'primary' && styles.primaryLabel,
          variant === 'secondary' && styles.secondaryLabel,
          variant === 'ghost' && styles.ghostLabel,
          variant === 'danger' && styles.dangerLabel,
          labelStyle,
        ]}>
        {children}
      </Text>
    ) : (
      children
    );

  return (
    <FocusPressable
      {...props}
      accessibilityRole={accessibilityRole}
      accessibilityState={{...accessibilityState, disabled: isDisabled}}
      disabled={isDisabled}
      style={state => [
        styles.base,
        variant === 'primary' && styles.primary,
        variant === 'secondary' && styles.secondary,
        variant === 'ghost' && styles.ghost,
        variant === 'danger' && styles.danger,
        size === 'compact' && styles.compact,
        size === 'default' && styles.defaultSize,
        size === 'large' && styles.large,
        size === 'icon' && styles.icon,
        state.pressed && styles.pressed,
        isDisabled && styles.disabled,
        typeof style === 'function' ? style(state) : style,
      ]}>
      {content}
    </FocusPressable>
  );
}

const styles = StyleSheet.create({
  base: {
    alignItems: 'center',
    borderRadius: tokens.radius.md,
    flexDirection: 'row',
    gap: tokens.space.sm,
    justifyContent: 'center',
    paddingHorizontal: tokens.space.md,
  },
  primary: {backgroundColor: tokens.color.primary},
  secondary: {
    backgroundColor: tokens.color.input,
    borderColor: tokens.color.line,
    borderWidth: tokens.border.width,
  },
  ghost: {backgroundColor: tokens.color.transparent},
  danger: {
    backgroundColor: tokens.color.transparent,
    borderColor: tokens.color.danger,
    borderWidth: tokens.border.width,
  },
  compact: {height: tokens.size.controlCompact},
  defaultSize: {height: tokens.size.control},
  large: {height: tokens.size.controlLarge},
  icon: {
    height: tokens.size.control,
    paddingHorizontal: tokens.space.none,
    width: tokens.size.control,
  },
  pressed: {opacity: tokens.opacity.pressed},
  disabled: {opacity: tokens.opacity.disabled},
  label: tokens.type.label,
  primaryLabel: {color: tokens.color.textInverse},
  secondaryLabel: {color: tokens.color.text},
  ghostLabel: {color: tokens.color.text},
  dangerLabel: {color: tokens.color.danger},
});
