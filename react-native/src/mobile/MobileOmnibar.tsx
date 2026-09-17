import React from 'react';
import {StyleSheet, Text, TextInput, View} from 'react-native';
import ArrowUp from 'lucide-react-native/icons/arrow-up';
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
  voiceControl,
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
  voiceControl?: React.ReactNode;
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
      <View style={styles.modes}>
        {(['Ask', 'Search'] as const).map(item => (
          <FocusPressable
            key={item}
            accessibilityRole="button"
            accessibilityLabel={`${item} mode`}
            accessibilityState={{selected: mode === item}}
            onPress={() => onModeChange(item)}
            style={[styles.mode, mode === item && styles.selected]}>
            <Text
              style={[styles.modeText, mode === item && styles.selectedText]}>
              {item}
            </Text>
          </FocusPressable>
        ))}
        {voiceControl && <View style={styles.voice}>{voiceControl}</View>}
      </View>
      <View style={styles.field}>
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
    marginVertical: 8,
    padding: 6,
    borderRadius: 22,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: color.border,
    backgroundColor: color.surface,
    gap: 4,
  },
  modes: {flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 4},
  voice: {marginLeft: 'auto', flexShrink: 1},
  mode: {
    minHeight: 44,
    paddingHorizontal: 18,
    borderRadius: 16,
    justifyContent: 'center',
  },
  selected: {backgroundColor: color.surfaceRaised},
  modeText: {fontSize: 13, color: color.textMuted},
  selectedText: {color: color.text, fontWeight: '600'},
  field: {flexDirection: 'row', alignItems: 'center'},
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
