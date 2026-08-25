import React from 'react';
import {StyleSheet, TextInput, View} from 'react-native';
import ArrowUp from 'lucide-react-native/icons/arrow-up';
import Search from 'lucide-react-native/icons/search';
import {FocusPressable} from './Pressable';
import {Icon} from './Icon';
import {Input} from './Field';
import {tokens} from './tokens';

export function HomeSearchField({
  compact,
  desktop,
  onBlur,
  onChangeText,
  onFocus,
  onOpenChat,
  onPressIn,
  inputRef,
  query,
  searchFocused,
  searchArmed,
}: {
  compact: boolean;
  desktop: boolean;
  onBlur: () => void;
  onChangeText: (value: string) => void;
  onFocus: () => void;
  onOpenChat: () => void;
  onPressIn: () => void;
  inputRef: React.RefObject<TextInput | null>;
  query: string;
  searchFocused: boolean;
  searchArmed: boolean;
}) {
  return (
    <View
      accessibilityLabel="Home search dock"
      style={[
        styles.dock,
        desktop && styles.desktopDock,
        compact && styles.compactDock,
        !compact && !desktop && styles.wideDock,
        searchFocused && styles.focused,
      ]}>
      <Icon
        accessible={false}
        color={desktop ? tokens.color.chromeText : tokens.color.textSubtle}
        fallback={Search}
        size={desktop ? tokens.space.lg : tokens.size.icon}
        strokeWidth={tokens.icon.strokeWidth}
        symbolName="magnifyingglass"
      />
      <Input
        accessibilityHint={
          desktop
            ? 'Filters loaded conversations and memories only.'
            : undefined
        }
        accessibilityLabel="Search Home"
        onBlur={onBlur}
        onChangeText={onChangeText}
        onFocus={onFocus}
        onPressIn={onPressIn}
        placeholder="Search Omi"
        placeholderTextColor={
          desktop ? tokens.color.chromeText : tokens.color.textSubtle
        }
        ref={inputRef}
        showSoftInputOnFocus={searchArmed}
        containerStyle={styles.inputFrame}
        style={[styles.input, desktop && styles.desktopInput]}
        value={query}
      />
      <FocusPressable
        accessibilityLabel="Open Chat"
        accessibilityRole="button"
        onPress={onOpenChat}
        style={({pressed}) => [
          styles.askButton,
          desktop && styles.desktopAskButton,
          pressed && styles.pressed,
        ]}>
        <Icon
          color={tokens.color.textInverse}
          fallback={ArrowUp}
          size={desktop ? tokens.size.iconSmall : 17}
          strokeWidth={2.5}
          symbolName="arrow.up"
        />
      </FocusPressable>
    </View>
  );
}

const styles = StyleSheet.create({
  dock: {
    alignItems: 'center',
    alignSelf: 'center',
    backgroundColor: '#292929',
    borderColor: '#4a4a4a',
    borderRadius: tokens.space.xl,
    borderWidth: tokens.border.width,
    flexDirection: 'row',
    gap: tokens.space.sm,
    marginBottom: tokens.space.sm,
    marginTop: 'auto',
    maxWidth: tokens.size.searchMax,
    minHeight: tokens.size.searchDock,
    paddingLeft: 15,
    paddingRight: tokens.radius.sm,
    width: '100%',
  },
  desktopDock: {
    alignItems: 'center',
    alignSelf: 'stretch',
    backgroundColor: tokens.color.input,
    borderColor: tokens.color.transparent,
    borderRadius: tokens.space.md,
    borderWidth: tokens.space.none,
    flex: tokens.layout.grow,
    flexGrow: tokens.layout.grow,
    gap: 10,
    marginBottom: tokens.space.none,
    marginTop: tokens.space.none,
    maxWidth: '100%',
    minHeight: tokens.size.controlCompact,
    paddingHorizontal: tokens.space.md,
    width: 'auto',
  },
  compactDock: {
    backgroundColor: '#222621',
    borderColor: '#515a53',
    borderRadius: 28,
    marginBottom: tokens.space.md,
    minHeight: tokens.size.searchDockCompact,
  },
  wideDock: {
    marginBottom: tokens.space.xl,
    marginTop: 22,
    maxWidth: tokens.size.content,
  },
  focused: {
    borderColor: tokens.color.focus,
    borderWidth: tokens.border.width,
  },
  inputFrame: {
    backgroundColor: tokens.color.transparent,
    borderColor: tokens.color.transparent,
    borderWidth: tokens.space.none,
    flex: tokens.layout.grow,
    minHeight: 28,
    paddingHorizontal: tokens.space.none,
  },
  input: {
    color: tokens.color.primary,
    flex: tokens.layout.grow,
    fontSize: 15,
    minHeight: tokens.size.controlLarge,
  },
  desktopInput: {
    color: tokens.color.text,
    minHeight: 28,
    paddingVertical: tokens.space.xs,
  },
  askButton: {
    alignItems: 'center',
    backgroundColor: tokens.color.primary,
    borderRadius: 19,
    height: tokens.size.ask,
    justifyContent: 'center',
    width: tokens.size.ask,
  },
  desktopAskButton: {
    borderRadius: tokens.radius.lg,
    height: tokens.size.askCompact,
    width: tokens.size.askCompact,
  },
  pressed: {opacity: tokens.opacity.pressed},
});
