import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  type ViewStyle,
  type StyleProp,
} from 'react-native';
import { OmiColors, OmiRadius, OmiSpacing, OmiType } from './tokens';

export function SectionHeader({
  title,
  action,
  onPressAction,
}: {
  title: string;
  action?: string;
  onPressAction?: () => void;
}) {
  return (
    <View style={styles.sectionHeader}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {action ? (
        <TouchableOpacity onPress={onPressAction} disabled={!onPressAction} activeOpacity={0.8}>
          <Text style={styles.sectionAction}>{action}</Text>
        </TouchableOpacity>
      ) : null}
    </View>
  );
}

export function Card({
  children,
  style,
  onPress,
}: {
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
  onPress?: () => void;
}) {
  if (onPress) {
    return (
      <TouchableOpacity style={[styles.card, style]} onPress={onPress} activeOpacity={0.85}>
        {children}
      </TouchableOpacity>
    );
  }
  return <View style={[styles.card, style]}>{children}</View>;
}

export function Pill({
  label,
  tone = 'neutral',
  style,
}: {
  label: string;
  tone?: 'neutral' | 'accent' | 'success' | 'warning' | 'danger';
  style?: StyleProp<ViewStyle>;
}) {
  const toneStyle =
    tone === 'accent'
      ? styles.pillAccent
      : tone === 'success'
        ? styles.pillSuccess
        : tone === 'warning'
          ? styles.pillWarning
          : tone === 'danger'
            ? styles.pillDanger
            : styles.pillNeutral;
  const textTone =
    tone === 'accent' ? styles.pillTextAccent : styles.pillText;
  return (
    <View style={[styles.pill, toneStyle, style]}>
      <Text style={[styles.pillTextBase, textTone]}>{label}</Text>
    </View>
  );
}

export function EmptyState({ text }: { text: string }) {
  return <Text style={styles.empty}>{text}</Text>;
}

const styles = StyleSheet.create({
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: OmiSpacing.xl,
    marginBottom: OmiSpacing.sm,
  },
  sectionTitle: {
    ...OmiType.title3,
    color: OmiColors.textPrimary,
  },
  sectionAction: {
    ...OmiType.subhead,
    color: OmiColors.textSecondary,
  },
  card: {
    backgroundColor: OmiColors.conversationCard,
    borderRadius: OmiRadius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: OmiColors.border,
    padding: OmiSpacing.md,
  },
  pill: {
    alignSelf: 'flex-start',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: OmiRadius.pill,
  },
  pillNeutral: { backgroundColor: OmiColors.surface2 },
  pillAccent: { backgroundColor: OmiColors.accent },
  pillSuccess: { backgroundColor: OmiColors.successSurface },
  pillWarning: { backgroundColor: 'rgba(255,159,10,0.18)' },
  pillDanger: { backgroundColor: OmiColors.dangerSurface },
  pillTextBase: { ...OmiType.caption, fontWeight: '600' },
  pillText: { color: OmiColors.textSecondary },
  pillTextAccent: { color: OmiColors.onAccent },
  empty: {
    ...OmiType.subhead,
    color: OmiColors.textTertiary,
    marginBottom: OmiSpacing.xs,
  },
});
