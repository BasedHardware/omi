import React, {useEffect, useState} from 'react';
import {Platform, StyleSheet, TextInput, View} from 'react-native';
import {MaterialIcon} from '../ui/MaterialIcon';

import {FocusPressable} from '../ui/Pressable';
import {useOmiStyles, useOmiTheme} from '../design/OmiTheme';
import type {OmiTheme} from '../design/tokens';

export type MobileOmnibarMode = 'Ask' | 'Search';

/**
 * The shared Ask/Search composer: one capsule on a raised surface, mode
 * icons inline on the left, and an ink send circle on the right (the same
 * shape the chat transcript's composer rule describes).
 *
 * The field is one TextInput instance on every page, so sending from Home
 * and landing on the pushed chat page keeps focus and the keyboard. It grows
 * with the draft (up to eight lines on the chat page). On the chat page
 * Return adds a line and the circle sends, as in every messaging app; on the
 * Home dock Return submits. On web, Enter submits and Shift+Enter adds a
 * line.
 */
export function MobileOmnibar({
  mode,
  onModeChange,
  value,
  onChange,
  onSubmit,
  onStop,
  busy,
  canStop,
  inputRef,
  chatPage = false,
}: {
  mode: MobileOmnibarMode;
  onModeChange: (mode: MobileOmnibarMode) => void;
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onStop: () => void;
  busy: boolean;
  canStop: boolean;
  inputRef: React.RefObject<TextInput | null>;
  chatPage?: boolean;
}) {
  const theme = useOmiTheme();
  const styles = useOmiStyles(createStyles);
  const stopping = canStop;
  const disabled =
    !stopping && (value.trim() === '' || (mode === 'Ask' && busy));
  const submit = () => {
    if (!disabled) {
      if (stopping) {
        onStop();
      } else {
        onSubmit();
      }
    }
  };
  const glyph = disabled ? theme.color.inkDisabled : theme.color.onInk;
  const lineHeight = theme.type.body.lineHeight;
  const minHeight = theme.size.hitTarget;
  const maxHeight = lineHeight * (chatPage ? 8 : 4) + (minHeight - lineHeight);
  const [height, setHeight] = useState(minHeight);
  useEffect(() => {
    if (value === '') {
      setHeight(minHeight);
    }
  }, [minHeight, value]);
  return (
    <View
      accessibilityLabel={chatPage ? 'Chat composer' : 'Ask and search dock'}
      style={styles.root}>
      <View style={styles.field}>
        {!chatPage &&
          (['Ask', 'Search'] as const).map(item => (
            <FocusPressable
              key={item}
              accessibilityRole="button"
              accessibilityLabel={`${item} mode`}
              accessibilityState={{selected: mode === item}}
              onPress={() => onModeChange(item)}
              style={({pressed}) => [
                styles.mode,
                mode === item && styles.selected,
                pressed && mode !== item && styles.pressed,
              ]}>
              <MaterialIcon
                name={item === 'Ask' ? 'chat_bubble' : 'search'}
                size={theme.size.iconSmall + 2}
                color={
                  mode === item ? theme.color.ink : theme.color.inkTertiary
                }
              />
            </FocusPressable>
          ))}
        <TextInput
          ref={inputRef}
          accessibilityLabel={mode === 'Ask' ? 'Ask Omi' : 'Search loaded data'}
          value={value}
          onChangeText={onChange}
          onSubmitEditing={submit}
          multiline
          submitBehavior={chatPage ? 'newline' : 'submit'}
          blurOnSubmit={false}
          onKeyPress={event => {
            const key = event.nativeEvent as {key?: string; shiftKey?: boolean};
            if (Platform.OS === 'web' && key.key === 'Enter' && !key.shiftKey) {
              (event as {preventDefault?: () => void}).preventDefault?.();
              submit();
            }
          }}
          onContentSizeChange={event => {
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
          {...(Platform.OS === 'web' ? {rows: 1} : {})}
          returnKeyType={
            chatPage ? 'default' : mode === 'Ask' ? 'send' : 'search'
          }
          placeholder={mode === 'Ask' ? 'Ask Omi…' : 'Search Omi…'}
          placeholderTextColor={theme.color.inkTertiary}
          keyboardAppearance={theme.scheme}
          selectionColor={theme.color.ink}
          style={[styles.input, {height}]}
        />
        {mode === 'Search' && value.length > 0 && (
          <FocusPressable
            accessibilityRole="button"
            accessibilityLabel="Clear search"
            onPress={() => onChange('')}
            style={styles.clear}>
            <MaterialIcon
              name="close"
              size={theme.size.iconSmall}
              color={theme.color.inkSecondary}
            />
          </FocusPressable>
        )}
        <FocusPressable
          accessibilityRole="button"
          accessibilityLabel={
            stopping
              ? 'Stop response'
              : mode === 'Ask'
              ? 'Send to Omi'
              : 'Search loaded data'
          }
          disabled={disabled}
          hitSlop={4}
          onPress={submit}
          style={({pressed}) => [
            styles.submit,
            disabled && styles.submitDisabled,
            pressed && !disabled && styles.submitPressed,
          ]}>
          {stopping ? (
            <MaterialIcon name="stop" size={16} color={glyph} />
          ) : mode === 'Ask' ? (
            <MaterialIcon name="arrow_upward" size={20} color={glyph} />
          ) : (
            <MaterialIcon name="search" size={18} color={glyph} />
          )}
        </FocusPressable>
      </View>
    </View>
  );
}

const createStyles = (t: OmiTheme) => ({
  root: {
    paddingHorizontal: t.layout.pageGutter.mobile,
    paddingTop: t.space.xs,
    paddingBottom: t.space.sm,
    backgroundColor: 'transparent',
  },
  field: {
    flexDirection: 'row' as const,
    alignItems: 'flex-end' as const,
    minHeight: t.size.control + 4,
    paddingHorizontal: t.space.xs,
    paddingVertical: 3,
    gap: 2,
    borderRadius: t.radius.pill,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: t.color.hairline,
    backgroundColor: t.color.surface,
  },
  mode: {
    width: t.size.hitTarget,
    height: t.size.hitTarget,
    borderRadius: t.radius.pill,
    justifyContent: 'center' as const,
    alignItems: 'center' as const,
  },
  selected: {backgroundColor: t.color.fillSelected},
  pressed: {backgroundColor: t.color.fillPressed},
  input: {
    ...t.type.body,
    flex: 1,
    minWidth: 0,
    paddingHorizontal: t.space.sm,
    paddingTop: (t.size.hitTarget - t.type.body.lineHeight) / 2,
    paddingBottom: (t.size.hitTarget - t.type.body.lineHeight) / 2,
    color: t.color.ink,
    // The capsule is the focus affordance on web.
    ...(Platform.OS === 'web' ? {outlineStyle: 'none' as never} : {}),
  },
  clear: {
    width: t.size.hitTarget,
    height: t.size.hitTarget,
    justifyContent: 'center' as const,
    alignItems: 'center' as const,
  },
  submit: {
    width: t.size.controlCompact + 2,
    height: t.size.controlCompact + 2,
    margin: 3,
    borderRadius: t.radius.pill,
    justifyContent: 'center' as const,
    alignItems: 'center' as const,
    backgroundColor: t.color.ink,
  },
  submitDisabled: {backgroundColor: t.color.fill},
  submitPressed: {opacity: t.motion.pressedOpacity},
});
