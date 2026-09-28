// Mobile list building blocks. Lists are grouped surfaces with hairline
// separators (iOS grouped style), headed by quiet section labels, and every
// row in them has one shape whether it holds a task, a conversation, an app
// or a setting. See docs/design-language.md.
import React from 'react';
import {
  StyleSheet,
  Text,
  View,
  type StyleProp,
  type ViewStyle,
} from 'react-native';
import {useOmiStyles, useOmiTheme} from '../design/OmiTheme';
import type {OmiTheme} from '../design/tokens';
import {FocusPressable} from '../ui/Pressable';
import {MaterialIcon} from '../ui/MaterialIcon';

/** Quiet section label with an optional trailing text action (e.g. See All). */
export function MobileSectionHeader({
  title,
  action,
}: {
  title: string;
  action?: {label: string; accessibilityLabel?: string; onPress: () => void};
}) {
  const styles = useOmiStyles(createHeaderStyles);
  return (
    <View style={styles.row}>
      <Text accessibilityRole="header" style={styles.title}>
        {title}
      </Text>
      {action ? (
        <FocusPressable
          accessibilityRole="button"
          accessibilityLabel={action.accessibilityLabel ?? action.label}
          onPress={action.onPress}
          style={({pressed}) => [styles.action, pressed && styles.pressed]}>
          <Text style={styles.actionText}>{action.label}</Text>
        </FocusPressable>
      ) : null}
    </View>
  );
}

const createHeaderStyles = (t: OmiTheme) => ({
  row: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    justifyContent: 'space-between' as const,
    gap: t.space.sm,
    minHeight: t.size.hitTarget,
    paddingHorizontal: t.space.xs,
  },
  title: {
    ...t.type.subhead,
    fontWeight: '600' as const,
    color: t.color.inkSecondary,
    flexShrink: 1,
  },
  action: {
    minHeight: t.size.hitTarget,
    justifyContent: 'center' as const,
    paddingHorizontal: t.space.xs,
  },
  actionText: {
    ...t.type.subhead,
    color: t.color.inkSecondary,
  },
  pressed: {opacity: t.motion.pressedOpacity},
});

/**
 * Grouped surface: one surface step above the canvas, hairlines between its
 * rows, no border and no shadow.
 */
export function MobileGroup({
  children,
  inset = 16,
  style,
  accessibilityLabel,
}: {
  children: React.ReactNode;
  /** Leading inset of the separators, so they start under the row text. */
  inset?: number;
  style?: StyleProp<ViewStyle>;
  accessibilityLabel?: string;
}) {
  const styles = useOmiStyles(createGroupStyles);
  const rows = React.Children.toArray(children).filter(Boolean);
  return (
    <View accessibilityLabel={accessibilityLabel} style={[styles.group, style]}>
      {rows.map((row, index) => (
        <React.Fragment key={index}>
          {index > 0 ? (
            <View style={[styles.separator, {marginLeft: inset}]} />
          ) : null}
          {row}
        </React.Fragment>
      ))}
    </View>
  );
}

const createGroupStyles = (t: OmiTheme) => ({
  group: {
    backgroundColor: t.color.surface,
    borderRadius: t.radius.card,
    overflow: 'hidden' as const,
  },
  separator: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: t.color.separator,
  },
});

/** The one mobile row shape. */
export function MobileRow({
  title,
  titleStyle,
  subtitle,
  meta,
  trailingText,
  leading,
  accessory,
  trailing,
  onPress,
  disabled = false,
  accessibilityLabel,
  accessibilityRole,
  accessibilityState,
  titleLines = 2,
}: {
  title: string;
  titleStyle?: 'default' | 'done' | 'placeholder';
  subtitle?: string | null;
  meta?: string | null;
  /** Short trailing value aligned with the title, such as a time. */
  trailingText?: string | null;
  leading?: React.ReactNode;
  /** Inside the pressable, after the text (e.g. a chevron). */
  accessory?: React.ReactNode;
  /** Outside the pressable (e.g. a separate action button). */
  trailing?: React.ReactNode;
  onPress?: () => void;
  disabled?: boolean;
  accessibilityLabel?: string;
  accessibilityRole?: 'button' | 'checkbox' | 'text';
  accessibilityState?: {
    checked?: boolean;
    disabled?: boolean;
    busy?: boolean;
    selected?: boolean;
  };
  titleLines?: number;
}) {
  const styles = useOmiStyles(createRowStyles);
  const body = (
    <>
      {leading !== undefined ? (
        <View style={styles.leading}>{leading}</View>
      ) : null}
      <View style={styles.text}>
        <View style={styles.titleLine}>
          <Text
            numberOfLines={titleLines}
            style={[
              styles.title,
              titleStyle === 'done' && styles.titleDone,
              titleStyle === 'placeholder' && styles.titlePlaceholder,
            ]}>
            {title}
          </Text>
          {trailingText ? (
            <Text numberOfLines={1} style={styles.trailingText}>
              {trailingText}
            </Text>
          ) : null}
        </View>
        {subtitle ? (
          <Text numberOfLines={2} style={styles.subtitle}>
            {subtitle}
          </Text>
        ) : null}
        {meta ? (
          <Text numberOfLines={1} style={styles.meta}>
            {meta}
          </Text>
        ) : null}
      </View>
      {accessory}
    </>
  );
  if (onPress === undefined && accessibilityRole === undefined) {
    return (
      <View style={styles.row}>
        <View style={styles.main}>{body}</View>
        {trailing}
      </View>
    );
  }
  return (
    <View style={styles.row}>
      <FocusPressable
        accessibilityRole={accessibilityRole ?? 'button'}
        accessibilityLabel={accessibilityLabel ?? title}
        accessibilityState={accessibilityState}
        disabled={disabled || onPress === undefined}
        onPress={onPress}
        style={({pressed}) => [
          styles.main,
          styles.pressable,
          pressed && styles.pressed,
        ]}>
        {body}
      </FocusPressable>
      {trailing}
    </View>
  );
}

const createRowStyles = (t: OmiTheme) => ({
  row: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    paddingRight: t.space.xs,
  },
  main: {
    flex: 1,
    minWidth: 0,
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    gap: t.space.md,
    minHeight: 52,
    paddingVertical: t.space.md,
    paddingLeft: t.space.lg,
    paddingRight: t.space.md,
  },
  pressable: {minHeight: 52},
  pressed: {backgroundColor: t.color.fillPressed},
  leading: {
    width: 24,
    alignItems: 'center' as const,
    justifyContent: 'center' as const,
  },
  text: {flex: 1, minWidth: 0, gap: 2},
  titleLine: {
    flexDirection: 'row' as const,
    alignItems: 'baseline' as const,
    gap: t.space.sm,
  },
  title: {...t.type.body, color: t.color.ink, flex: 1, minWidth: 0},
  titleDone: {
    color: t.color.inkTertiary,
    textDecorationLine: 'line-through' as const,
  },
  titlePlaceholder: {color: t.color.inkSecondary, fontStyle: 'italic' as const},
  trailingText: {
    ...t.type.footnote,
    color: t.color.inkTertiary,
    flexShrink: 0,
  },
  subtitle: {...t.type.footnote, color: t.color.inkSecondary},
  meta: {...t.type.footnote, color: t.color.inkTertiary},
});

/** Task completion mark: open = empty circle, done = filled circle with check. */
export function TaskMark({done}: {done: boolean}) {
  const theme = useOmiTheme();
  const styles = useOmiStyles(createMarkStyles);
  return (
    <View style={[styles.mark, done && styles.done]}>
      {done ? (
        <MaterialIcon name="check" size={15} color={theme.color.onInk} />
      ) : null}
    </View>
  );
}

const createMarkStyles = (t: OmiTheme) => ({
  mark: {
    width: 22,
    height: 22,
    borderRadius: 11,
    borderWidth: 1.5,
    borderColor: t.color.inkTertiary,
    alignItems: 'center' as const,
    justifyContent: 'center' as const,
  },
  done: {backgroundColor: t.color.ink, borderColor: t.color.ink},
});

/**
 * Equal-width segmented control (tab list). Active segment is an ink-weighted
 * fill with a separator edge, never an accent; inactive segments are clear.
 */
export function MobileSegmented<T extends string>({
  options,
  value,
  onChange,
  accessibilityLabel,
  optionLabel,
  role = 'tab',
  disabled = false,
}: {
  options: ReadonlyArray<{value: T; label: string}>;
  value: T;
  onChange: (value: T) => void;
  accessibilityLabel?: string;
  /** Screen-reader name for each segment; defaults to its label. */
  optionLabel?: (option: {value: T; label: string}) => string;
  role?: 'tab' | 'button';
  disabled?: boolean;
}) {
  const styles = useOmiStyles(createSegmentStyles);
  return (
    <View
      accessibilityLabel={accessibilityLabel}
      accessibilityRole={role === 'tab' ? 'tablist' : undefined}
      style={styles.track}>
      {options.map(option => {
        const selected = option.value === value;
        return (
          <FocusPressable
            key={option.value}
            accessibilityRole={role}
            accessibilityLabel={optionLabel?.(option) ?? option.label}
            accessibilityState={{selected, disabled}}
            disabled={disabled}
            hitSlop={2}
            onPress={() => onChange(option.value)}
            style={({pressed}) => [
              styles.segment,
              selected && styles.selected,
              pressed && !selected && styles.pressed,
            ]}>
            <Text
              numberOfLines={1}
              style={[styles.label, selected && styles.labelSelected]}>
              {option.label}
            </Text>
          </FocusPressable>
        );
      })}
    </View>
  );
}

const createSegmentStyles = (t: OmiTheme) => ({
  track: {
    flexDirection: 'row' as const,
    padding: 2,
    gap: 2,
    borderRadius: t.radius.pill,
    backgroundColor: t.color.fill,
  },
  segment: {
    flex: 1,
    minWidth: 0,
    minHeight: 40,
    paddingHorizontal: t.space.sm,
    alignItems: 'center' as const,
    justifyContent: 'center' as const,
    borderRadius: t.radius.pill,
    borderWidth: 1,
    borderColor: 'transparent',
  },
  selected: {
    // Light: a white thumb on the grey track (iOS); dark: one surface step up.
    backgroundColor:
      t.scheme === 'light' ? t.color.surface : t.color.surfacePressed,
    borderColor: t.color.separator,
  },
  pressed: {backgroundColor: t.color.fillPressed},
  label: {
    ...t.type.subhead,
    fontWeight: '500' as const,
    color: t.color.inkSecondary,
  },
  labelSelected: {color: t.color.ink, fontWeight: '600' as const},
});

/**
 * Inline section state for a list that shares a screen with others (Home).
 * Loading and failed reads say so; they never claim to be empty.
 */
export function MobileInlineState({
  label,
  tone = 'quiet',
  accessibilityLabel,
}: {
  label: string;
  tone?: 'quiet' | 'alert';
  accessibilityLabel?: string;
}) {
  const styles = useOmiStyles(createInlineStateStyles);
  return (
    <View
      accessibilityLabel={accessibilityLabel}
      accessibilityRole={tone === 'alert' ? 'alert' : undefined}
      style={styles.root}>
      <Text style={styles.text}>{label}</Text>
    </View>
  );
}

const createInlineStateStyles = (t: OmiTheme) => ({
  root: {
    minHeight: 52,
    justifyContent: 'center' as const,
    paddingHorizontal: t.space.lg,
    paddingVertical: t.space.md,
  },
  text: {...t.type.subhead, color: t.color.inkSecondary},
});
