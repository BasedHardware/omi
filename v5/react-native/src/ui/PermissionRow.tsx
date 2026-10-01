import React from 'react';
import {StyleSheet, Text, View} from 'react-native';
import {FocusPressable as Pressable} from './Pressable';
import {
  type DesktopTokens,
  useDesktopStyleSheets,
} from '../desktop/DesktopTheme';
import {tokens} from './tokens';

export function PermissionRow({
  title,
  granted,
  status,
  onPress,
  disabled = false,
  light = false,
  description,
  icon,
  grouped = false,
}: {
  title: string;
  granted: boolean;
  status: string;
  onPress: () => void;
  disabled?: boolean;
  light?: boolean;
  description?: string;
  icon?: React.ReactNode;
  grouped?: boolean;
}) {
  const styles = useDesktopStyleSheets(createStyles);
  return (
    <Pressable
      accessibilityLabel={[title, description, status]
        .filter(Boolean)
        .map(text => text?.replace(/[.!?]$/, ''))
        .join('. ')}
      accessibilityRole="button"
      accessibilityState={{disabled, busy: status === 'Asking…'}}
      disabled={disabled}
      onPress={onPress}
      style={({pressed}) => [
        styles.row,
        light && styles.rowLight,
        grouped && styles.grouped,
        pressed && (light ? styles.rowLightHover : styles.rowHover),
        disabled && !granted && styles.disabled,
      ]}>
      {icon ? (
        <View style={styles.icon}>{icon}</View>
      ) : (
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
      )}
      <View style={styles.label}>
        <Text style={[styles.title, light && styles.titleLight]}>{title}</Text>
        {description ? (
          <Text style={[styles.description, light && styles.statusLight]}>
            {description}
          </Text>
        ) : null}
      </View>
      <View style={grouped && styles.statusPill}>
        <Text style={[styles.status, light && styles.statusLight]}>
          {granted && icon ? '✓  ' : ''}
          {status}
        </Text>
      </View>
    </Pressable>
  );
}

const createStyles = (desktopTokens: DesktopTokens) =>
  StyleSheet.create({
    row: {
      alignItems: 'center',
      alignSelf: 'stretch',
      backgroundColor: 'rgba(255,255,255,0.045)',
      borderColor: 'rgba(255,255,255,0.12)',
      borderRadius: 16,
      borderWidth: 1,
      flexDirection: 'row',
      gap: 16,
      paddingHorizontal: 20,
      paddingVertical: 20,
    },
    rowHover: {backgroundColor: 'rgba(255,255,255,0.085)'},
    rowLight: {
      backgroundColor: desktopTokens.color.glassStrong,
      borderColor: desktopTokens.color.line,
    },
    rowLightHover: {backgroundColor: 'rgba(0,0,0,0.085)'},
    grouped: {
      borderWidth: 0,
      borderRadius: 0,
      backgroundColor: 'transparent',
      paddingVertical: 18,
    },
    icon: {width: 24, alignItems: 'center'},
    label: {flex: 1, gap: 3},
    description: {fontSize: 12, lineHeight: 18, color: tokens.color.textMuted},
    statusPill: {
      paddingVertical: 6,
      paddingHorizontal: 10,
      borderRadius: 12,
      backgroundColor: 'rgba(255,255,255,0.5)',
    },
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
