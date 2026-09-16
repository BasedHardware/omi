import React from 'react';
import {Pressable, StyleSheet, Text, View} from 'react-native';
import {desktopTokens} from '../desktop/tokens';
import {tokens} from './tokens';

export function PermissionRow({
  title,
  granted,
  status,
  onPress,
  disabled = false,
  light = false,
}: {
  title: string;
  granted: boolean;
  status: string;
  onPress: () => void;
  disabled?: boolean;
  light?: boolean;
}) {
  return (
    <Pressable
      accessibilityLabel={`${title}. ${status}`}
      accessibilityRole="button"
      disabled={disabled}
      onPress={onPress}
      style={({pressed}) => [
        styles.row,
        light && styles.rowLight,
        pressed && (light ? styles.rowLightHover : styles.rowHover),
        disabled && styles.disabled,
      ]}>
      <View
        style={[
          styles.checkbox,
          light && styles.checkboxLight,
          granted &&
            (light ? styles.checkboxGrantedLight : styles.checkboxGranted),
        ]}>
        {granted ? (
          <Text style={[styles.check, light && styles.checkLight]}>✓</Text>
        ) : null}
      </View>
      <Text style={[styles.title, light && styles.titleLight]}>{title}</Text>
      <Text style={[styles.status, light && styles.statusLight]}>{status}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: {
    alignItems: 'center',
    alignSelf: 'stretch',
    backgroundColor: 'rgba(255,255,255,0.045)',
    borderColor: 'rgba(255,255,255,0.12)',
    borderRadius: 13,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 11,
    paddingHorizontal: 14,
    paddingVertical: 11,
  },
  rowHover: {backgroundColor: 'rgba(255,255,255,0.085)'},
  rowLight: {
    backgroundColor: 'rgba(0,0,0,0.045)',
    borderColor: 'rgba(0,0,0,0.08)',
  },
  rowLightHover: {backgroundColor: 'rgba(0,0,0,0.085)'},
  disabled: {opacity: 0.48},
  checkbox: {
    alignItems: 'center',
    borderColor: 'rgba(255,255,255,0.28)',
    borderRadius: 6,
    borderWidth: 1,
    height: 18,
    justifyContent: 'center',
    width: 18,
  },
  checkboxLight: {borderColor: 'rgba(0,0,0,0.22)'},
  checkboxGranted: {
    backgroundColor: '#ffffff',
    borderColor: '#ffffff',
  },
  checkboxGrantedLight: {
    backgroundColor: desktopTokens.color.ink,
    borderColor: desktopTokens.color.ink,
  },
  check: {color: '#141414', fontSize: 11, fontWeight: '700'},
  checkLight: {
    color: desktopTokens.color.white,
    fontSize: 11,
    fontWeight: '700',
  },
  title: {
    color: tokens.color.text,
    flex: 1,
    fontSize: 15,
    fontWeight: '500',
    letterSpacing: -0.15,
    lineHeight: 21,
  },
  titleLight: {color: desktopTokens.color.ink},
  status: {
    color: tokens.color.textMuted,
    fontSize: 12,
    fontWeight: '400',
  },
  statusLight: {color: desktopTokens.color.inkMuted},
});
