import React from 'react';
import {StyleSheet, TextInput, View} from 'react-native';
import ArrowUp from 'lucide-react-native/icons/arrow-up';
import MessageCircle from 'lucide-react-native/icons/message-circle';
import Search from 'lucide-react-native/icons/search';
import Square from 'lucide-react-native/icons/square';
import X from 'lucide-react-native/icons/x';
import {FocusPressable} from '../ui/Pressable';
import {mobileColor as color} from './mobileTokens';

export type MobileOmnibarMode = 'Ask' | 'Search';

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
}) {
  const stopping = mode === 'Ask' && canStop;
  const disabled =
    !stopping && (value.trim() === '' || (mode === 'Ask' && busy));
  const submit = () => {
    if (!disabled) {
      if (stopping) onStop();
      else onSubmit();
    }
  };
  return (
    <View accessibilityLabel="Ask and search dock" style={styles.root}>
      <View style={styles.field}>
        <View style={styles.modes}>
          {(['Search', 'Ask'] as const).map(item => {
            const Icon = item === 'Search' ? Search : MessageCircle;
            return (
              <FocusPressable
                key={item}
                accessibilityRole="button"
                accessibilityLabel={`${item} mode`}
                accessibilityHint={`Use ${item.toLowerCase()} mode`}
                accessibilityState={{selected: mode === item}}
                onPress={() => onModeChange(item)}
                style={[styles.mode, mode === item && styles.selected]}>
                <Icon
                  color={mode === item ? color.text : color.textMuted}
                  size={17}
                />
              </FocusPressable>
            );
          })}
        </View>
        <TextInput
          ref={inputRef}
          accessibilityLabel={mode === 'Ask' ? 'Ask Omi' : 'Search loaded data'}
          value={value}
          onChangeText={onChange}
          onSubmitEditing={submit}
          returnKeyType={mode === 'Ask' ? 'send' : 'search'}
          placeholder={mode === 'Ask' ? 'Ask anything…' : 'Search loaded data…'}
          placeholderTextColor={color.textSubtle}
          style={styles.input}
        />
        {mode === 'Search' && value.length > 0 && (
          <FocusPressable
            accessibilityRole="button"
            accessibilityLabel="Clear search"
            onPress={() => onChange('')}
            style={styles.clear}>
            <X size={18} color={color.textMuted} />
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
          onPress={submit}
          style={[styles.submit, disabled && styles.disabled]}>
          {stopping ? (
            <Square
              size={14}
              fill={color.background}
              color={color.background}
            />
          ) : mode === 'Ask' ? (
            <ArrowUp size={20} color={color.background} />
          ) : (
            <Search size={18} color={color.background} />
          )}
        </FocusPressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    marginHorizontal: 10,
    marginVertical: 6,
    backgroundColor: 'transparent',
    padding: 0,
  },
  modes: {flexDirection: 'row', gap: 2},
  mode: {
    width: 38,
    height: 38,
    borderRadius: 14,
    justifyContent: 'center',
    alignItems: 'center',
  },
  selected: {backgroundColor: color.surfaceRaised},
  field: {
    backgroundColor: color.surface,
    borderColor: color.border,
    borderRadius: 22,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: 'row',
    alignItems: 'center',
    padding: 4,
  },
  input: {
    flex: 1,
    minWidth: 0,
    minHeight: 44,
    paddingHorizontal: 12,
    fontSize: 16,
    color: color.text,
  },
  clear: {
    width: 44,
    height: 44,
    justifyContent: 'center',
    alignItems: 'center',
  },
  submit: {
    width: 44,
    height: 44,
    borderRadius: 16,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: color.text,
  },
  disabled: {opacity: 0.35},
});
