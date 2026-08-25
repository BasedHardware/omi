import React, {useState} from 'react';
import {
  Pressable as NativePressable,
  type PressableProps,
  StyleSheet,
} from 'react-native';
import {tokens} from './tokens';

export function FocusPressable({
  onBlur,
  onFocus,
  style,
  ...props
}: PressableProps) {
  const [focused, setFocused] = useState(false);

  return (
    <NativePressable
      {...props}
      onBlur={event => {
        setFocused(false);
        onBlur?.(event);
      }}
      onFocus={event => {
        setFocused(true);
        onFocus?.(event);
      }}
      style={state => [
        typeof style === 'function' ? style(state) : style,
        focused && styles.focusRing,
      ]}
    />
  );
}

export const Pressable = FocusPressable;

const styles = StyleSheet.create({
  focusRing: {
    borderColor: tokens.color.focus,
    borderWidth: tokens.border.width,
  },
});
