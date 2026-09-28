import React from 'react';
import {StyleSheet, TextInput, View} from 'react-native';
import {MaterialIcon} from '../ui/MaterialIcon';

import {FocusPressable} from '../ui/Pressable';
import {useOmiStyles, useOmiTheme} from '../design/OmiTheme';
import type {OmiTheme} from '../design/tokens';

export type MobileOmnibarMode = 'Ask' | 'Search';

/**
 * The shared Ask/Search composer: one capsule on a raised surface, mode
 * icons inline on the left, and an ink send circle on the right (the same
 * shape the chat transcript's composer rule describes).
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
          returnKeyType={mode === 'Ask' ? 'send' : 'search'}
          placeholder={mode === 'Ask' ? 'Ask Omi…' : 'Search Omi…'}
          placeholderTextColor={theme.color.inkTertiary}
          keyboardAppearance={theme.scheme}
          selectionColor={theme.color.ink}
          style={styles.input}
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
    alignItems: 'center' as const,
    minHeight: t.size.control + 4,
    paddingHorizontal: t.space.xs,
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
    minHeight: t.size.hitTarget,
    paddingHorizontal: t.space.sm,
    paddingVertical: 0,
    color: t.color.ink,
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
