import React, {forwardRef, useState} from 'react';
import {
  Pressable as NativePressable,
  type PressableProps,
  StyleSheet,
} from 'react-native';
import {tokens} from './tokens';

export const FocusPressable = forwardRef<
  React.ElementRef<typeof NativePressable>,
  PressableProps
>(function FocusPressable({onBlur, onFocus, style, ...props}, ref) {
  const [focused, setFocused] = useState(false);

  return (
    <NativePressable
      ref={ref}
      {...props}
      aria-checked={props['aria-checked'] ?? props.accessibilityState?.checked}
      aria-selected={
        props['aria-selected'] ?? props.accessibilityState?.selected
      }
      aria-expanded={
        props['aria-expanded'] ?? props.accessibilityState?.expanded
      }
      aria-busy={props['aria-busy'] ?? props.accessibilityState?.busy}
      disabled={
        props.disabled ??
        props['aria-disabled'] ??
        props.accessibilityState?.disabled
      }
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
});

export const Pressable = FocusPressable;

const styles = StyleSheet.create({
  focusRing: {
    borderColor: tokens.color.focus,
    borderWidth: tokens.border.width,
  },
});
