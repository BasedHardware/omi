import React, {forwardRef, useState} from 'react';
import {
  Platform,
  Pressable as NativePressable,
  type GestureResponderEvent,
  type PressableProps,
  type StyleProp,
  StyleSheet,
  type ViewStyle,
} from 'react-native';
import {type KitTokens, useKitStyleSheets} from '../desktop/DesktopTheme';

/**
 * Pressable state as this kit exposes it: RN's own callback type carries only
 * `pressed`, but macOS and web both deliver hover, so every style callback in
 * the tree may branch on `hovered` (touch platforms simply never set it).
 */
export type PressableState = {pressed: boolean; hovered: boolean};
export type PressableStyleProp =
  | StyleProp<ViewStyle>
  | ((state: PressableState) => StyleProp<ViewStyle>);
export type FocusPressableProps = Omit<PressableProps, 'style'> & {
  style?: PressableStyleProp;
};

// On macOS the chrome row doubles as a window-drag region: a left-click that
// hit-tests to a plain RCTView is swallowed by performWindowDragWithEvent and
// never reaches the React touch system. RCTView defaults to
// mouseDownCanMoveWindow = YES, so without this a pressable only responds on
// its Text glyphs (the glyph, not the padding, is what blocks the drag).
const blocksWindowDrag =
  Platform.OS === 'macos' ? {mouseDownCanMoveWindow: false} : undefined;

export const FocusPressable = forwardRef<
  React.ElementRef<typeof NativePressable>,
  FocusPressableProps
>(function FocusPressable(
  {onBlur, onFocus, onHoverIn, onHoverOut, style, ...props},
  ref,
) {
  const styles = useKitStyleSheets(createStyles);
  const [focused, setFocused] = useState(false);
  const [hovered, setHovered] = useState(false);

  return (
    <NativePressable
      ref={ref}
      {...blocksWindowDrag}
      {...props}
      onAccessibilityTap={
        props.onAccessibilityTap ??
        (props.onPress
          ? () => {
              // The AX activation path carries no gesture payload; every
              // press handler in this tree ignores the event argument.
              props.onPress?.(undefined as unknown as GestureResponderEvent);
            }
          : undefined)
      }
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
      onHoverIn={event => {
        setHovered(true);
        onHoverIn?.(event);
      }}
      onHoverOut={event => {
        setHovered(false);
        onHoverOut?.(event);
      }}
      style={state => [
        typeof style === 'function' ? style({...state, hovered}) : style,
        hovered && !state.pressed && styles.hoverCursor,
        focused && styles.focusRing,
      ]}
    />
  );
});

export const Pressable = FocusPressable;

const createStyles = (tokens: KitTokens) =>
  StyleSheet.create({
    focusRing: {
      borderColor: tokens.color.focus,
      borderWidth: tokens.border.width,
    },
    hoverCursor: {
      // macOS and web both honor the NSCursor/CSS pointer hand; touch
      // platforms never enter hover so the key stays inert there.
      cursor: 'pointer',
    } as ReturnType<typeof StyleSheet.create>,
  });
