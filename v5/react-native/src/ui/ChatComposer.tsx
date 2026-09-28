import React, {useCallback, useEffect, useState} from 'react';
import {
  Platform,
  StyleSheet,
  TextInput,
  View,
  type NativeSyntheticEvent,
  type StyleProp,
  type TextInputContentSizeChangeEventData,
  type ViewStyle,
} from 'react-native';
import {MaterialIcon} from './MaterialIcon';
import {FocusPressable} from './Pressable';
import {useOmiStyles, useOmiTheme} from '../design/OmiTheme';
import type {OmiTheme} from '../design/tokens';

/** The composer grows with the draft up to this many lines, then scrolls. */
export const CHAT_COMPOSER_MAX_LINES = 8;

type KeyLike = {
  key?: string;
  shiftKey?: boolean;
  altKey?: boolean;
  metaKey?: boolean;
  ctrlKey?: boolean;
  isComposing?: boolean;
};

/**
 * The one chat composer (desktop Chat and the phone chat page): a capsule
 * with a fill and hairline, a multiline field that grows to eight lines, and
 * an ink send circle that becomes Stop while Omi answers.
 *
 * Keyboard: on desktop and web Enter sends and Shift+Enter inserts a line
 * break; Esc leaves the field. Phones keep Return as a line break and send
 * with the button, like every messaging app.
 */
export function ChatComposer({
  value,
  onChangeText,
  onSend,
  onStop,
  canStop,
  busy,
  inputRef,
  placeholder = 'Ask Omi…',
  inputLabel = 'Message Omi',
  sendLabel = 'Send',
  stopLabel = 'Stop',
  enterSends = true,
  accessory,
  style,
}: {
  value: string;
  onChangeText: (text: string) => void;
  onSend: () => void;
  onStop: () => void;
  /** An admitted generation exists: the circle becomes Stop. */
  canStop: boolean;
  /** A send is in flight but not yet cancellable: Send stays disabled. */
  busy: boolean;
  inputRef?: React.RefObject<TextInput | null>;
  placeholder?: string;
  inputLabel?: string;
  sendLabel?: string;
  stopLabel?: string;
  enterSends?: boolean;
  /** Optional control inside the capsule before Send (e.g. Live voice). */
  accessory?: React.ReactNode;
  style?: StyleProp<ViewStyle>;
}) {
  const theme = useOmiTheme();
  const styles = useOmiStyles(createStyles);
  const lineHeight = theme.type.body.lineHeight;
  const verticalPadding = theme.density === 'desktop' ? 6 : 10;
  const minHeight = lineHeight + verticalPadding * 2;
  const maxHeight = lineHeight * CHAT_COMPOSER_MAX_LINES + verticalPadding * 2;
  const [height, setHeight] = useState(minHeight);
  // A cleared draft (after Send) collapses back to one line; browsers never
  // report a shrinking scrollHeight on their own.
  useEffect(() => {
    if (value === '') {
      setHeight(minHeight);
    }
  }, [minHeight, value]);
  const canSend = !busy && value.trim() !== '';
  const disabled = !canStop && !canSend;
  const submit = useCallback(() => {
    if (!canStop && canSend) {
      onSend();
    }
  }, [canSend, canStop, onSend]);
  const onKey = (event: {
    nativeEvent: KeyLike;
    preventDefault?: () => void;
    currentTarget?: unknown;
  }) => {
    const key = event.nativeEvent;
    if (key.key === 'Escape') {
      (event.currentTarget as {blur?: () => void} | undefined)?.blur?.();
      inputRef?.current?.blur();
      return;
    }
    if (
      enterSends &&
      key.key === 'Enter' &&
      !key.shiftKey &&
      !key.altKey &&
      !key.isComposing
    ) {
      event.preventDefault?.();
      submit();
    }
  };
  const glyph = disabled ? theme.color.inkSecondary : theme.color.onInk;
  const macKeys =
    Platform.OS === 'macos' && enterSends
      ? {
          // RN macOS: hand plain Enter to JS (no newline is inserted);
          // Shift+Enter stays native and inserts the line break.
          keyDownEvents: [{key: 'Enter'}],
          onKeyDown: onKey,
        }
      : {};
  return (
    <View
      accessibilityLabel="Chat composer"
      style={[styles.capsule, {borderRadius: (minHeight + 12) / 2}, style]}>
      <TextInput
        ref={inputRef}
        accessibilityLabel={inputLabel}
        placeholder={placeholder}
        placeholderTextColor={theme.color.inkSecondary}
        keyboardAppearance={theme.scheme}
        selectionColor={theme.color.ink}
        value={value}
        onChangeText={onChangeText}
        multiline
        {...(Platform.OS === 'web' ? {rows: 1} : {})}
        {...(macKeys as object)}
        blurOnSubmit={false}
        onKeyPress={onKey as never}
        onSubmitEditing={enterSends ? submit : undefined}
        onContentSizeChange={(
          event: NativeSyntheticEvent<TextInputContentSizeChangeEventData>,
        ) => {
          const next = Math.min(
            maxHeight,
            Math.max(
              minHeight,
              Math.ceil(event.nativeEvent.contentSize.height),
            ),
          );
          setHeight(current => (current === next ? current : next));
        }}
        scrollEnabled={height >= maxHeight}
        textAlignVertical="center"
        style={[
          styles.input,
          {height, paddingVertical: verticalPadding, lineHeight},
        ]}
      />
      {accessory ? <View style={styles.accessory}>{accessory}</View> : null}
      <FocusPressable
        accessibilityRole="button"
        accessibilityLabel={canStop ? stopLabel : sendLabel}
        accessibilityState={{disabled}}
        disabled={disabled}
        hitSlop={theme.density === 'mobile' ? 4 : undefined}
        onPress={canStop ? onStop : submit}
        {...({tooltip: canStop ? stopLabel : sendLabel} as object)}
        style={state => [
          styles.send,
          disabled && styles.sendDisabled,
          state.pressed && !disabled && styles.sendPressed,
        ]}>
        <MaterialIcon
          name={canStop ? 'stop' : 'arrow_upward'}
          size={canStop ? 16 : theme.density === 'desktop' ? 17 : 20}
          color={glyph}
        />
      </FocusPressable>
    </View>
  );
}

const createStyles = (t: OmiTheme) => {
  const send = t.density === 'desktop' ? 30 : t.size.controlCompact;
  return {
    capsule: {
      flexDirection: 'row' as const,
      alignItems: 'flex-end' as const,
      gap: t.space.xs,
      paddingVertical: 6,
      paddingLeft: t.density === 'desktop' ? t.space.md + 2 : t.space.lg,
      paddingRight: 6,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: t.color.hairline,
      backgroundColor: t.density === 'desktop' ? t.color.fill : t.color.surface,
    },
    input: {
      ...t.type.body,
      color: t.color.ink,
      flex: 1,
      minWidth: 0,
      paddingHorizontal: 0,
      // RN web draws a focus outline on the textarea; the capsule is the
      // focus affordance.
      ...(Platform.OS === 'web' ? {outlineStyle: 'none' as never} : {}),
    },
    accessory: {alignSelf: 'center' as const},
    send: {
      width: send,
      height: send,
      marginBottom: t.density === 'desktop' ? 1 : 0,
      borderRadius: t.radius.pill,
      backgroundColor: t.color.ink,
      alignItems: 'center' as const,
      justifyContent: 'center' as const,
    },
    sendDisabled: {backgroundColor: t.color.fillSelected},
    sendPressed: {opacity: t.motion.pressedOpacity},
  };
};
