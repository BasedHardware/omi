// Core Omi primitives. Every surface builds from these instead of restyling
// the same job locally; see docs/design-language.md for when to use each.
import React from 'react';
import {
  ActivityIndicator,
  type PressableStateCallbackType,
  type StyleProp,
  Text,
  View,
  type ViewStyle,
} from 'react-native';
import {FocusPressable} from '../ui/Pressable';
import {MaterialIcon, type MaterialIconName} from '../ui/MaterialIcon';
import {useOmiStyles, useOmiTheme} from './OmiTheme';
import type {OmiTheme} from './tokens';

type PressState = PressableStateCallbackType & {hovered?: boolean};

/** Grows a visually smaller control's touch area to the density's hit target. */
function hitSlopFor(theme: OmiTheme, visual: number) {
  const extra = Math.max(0, (theme.size.hitTarget - visual) / 2);
  return extra > 0
    ? {top: extra, bottom: extra, left: extra, right: extra}
    : undefined;
}

export type OmiButtonVariant =
  | 'primary'
  | 'secondary'
  | 'destructive'
  | 'plain';

/**
 * Capsule button. Primary is an ink fill (black on light, white on dark),
 * never an accent colour. Press feedback is colour only.
 */
export function OmiButton({
  label,
  onPress,
  variant = 'secondary',
  compact = false,
  icon,
  disabled = false,
  busy = false,
  accessibilityLabel,
  style,
}: {
  label: string;
  onPress: () => void;
  variant?: OmiButtonVariant;
  compact?: boolean;
  icon?: MaterialIconName;
  disabled?: boolean;
  /** Keeps the button's size and swaps the label for a spinner. */
  busy?: boolean;
  accessibilityLabel?: string;
  style?: StyleProp<ViewStyle>;
}) {
  const theme = useOmiTheme();
  const styles = useOmiStyles(createButtonStyles);
  const inactive = disabled || busy;
  const labelColor = inactive
    ? theme.color.inkSecondary
    : variant === 'primary'
    ? theme.color.onInk
    : variant === 'destructive'
    ? '#FFFFFF'
    : theme.color.ink;
  return (
    <FocusPressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? label}
      accessibilityState={{disabled: inactive, busy}}
      disabled={inactive}
      onPress={onPress}
      style={state => [
        styles.base,
        compact ? styles.compact : styles.regular,
        inactive ? styles.disabled : styles[variant],
        !inactive && state.pressed && styles.pressed,
        !inactive &&
          (state as PressState).hovered &&
          variant !== 'primary' &&
          variant !== 'destructive' &&
          styles.hovered,
        style,
      ]}>
      {busy ? (
        <ActivityIndicator size="small" color={labelColor} />
      ) : (
        <>
          {icon ? (
            <MaterialIcon
              name={icon}
              size={compact ? theme.size.iconSmall : theme.size.icon}
              color={labelColor}
            />
          ) : null}
          <Text
            numberOfLines={1}
            style={[
              compact ? styles.labelCompact : styles.label,
              {color: labelColor},
            ]}>
            {label}
          </Text>
        </>
      )}
    </FocusPressable>
  );
}

const createButtonStyles = (t: OmiTheme) => ({
  base: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    justifyContent: 'center' as const,
    gap: t.space.xs + 2,
    borderRadius: t.radius.pill,
    borderWidth: 1,
    borderColor: 'transparent',
  },
  regular: {
    minHeight: t.size.control,
    paddingHorizontal: t.density === 'desktop' ? t.space.lg : t.space.xxl,
  },
  compact: {minHeight: t.size.controlCompact, paddingHorizontal: t.space.md},
  primary: {backgroundColor: t.color.ink},
  secondary: {backgroundColor: 'transparent', borderColor: t.color.hairline},
  destructive: {backgroundColor: t.color.danger},
  plain: {backgroundColor: 'transparent'},
  disabled: {backgroundColor: t.color.fill, borderColor: t.color.separator},
  pressed: {opacity: t.motion.pressedOpacity},
  hovered: {backgroundColor: t.color.fill},
  label: {...t.type.headline},
  labelCompact: {...t.type.subhead, fontWeight: '600' as const},
});

/** Circular icon-only button. A label is required: it is the tooltip and the screen-reader name. */
export function OmiIconButton({
  icon,
  label,
  onPress,
  size = 'regular',
  selected = false,
  disabled = false,
}: {
  icon: MaterialIconName;
  label: string;
  onPress: () => void;
  size?: 'small' | 'regular';
  selected?: boolean;
  disabled?: boolean;
}) {
  const theme = useOmiTheme();
  const styles = useOmiStyles(createIconButtonStyles);
  const box = size === 'small' ? theme.size.controlCompact : theme.size.control;
  return (
    <FocusPressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{disabled, selected}}
      // react-native-web / macOS show this as the hover tooltip.
      {...({tooltip: label, title: label} as object)}
      disabled={disabled}
      onPress={onPress}
      hitSlop={hitSlopFor(theme, box)}
      style={state => [
        styles.base,
        {width: box, height: box},
        selected && styles.selected,
        (state as PressState).hovered && !selected && styles.hovered,
        state.pressed && styles.pressed,
      ]}>
      <MaterialIcon
        name={icon}
        size={size === 'small' ? theme.size.iconSmall : theme.size.icon}
        color={disabled ? theme.color.inkDisabled : theme.color.ink}
      />
    </FocusPressable>
  );
}

const createIconButtonStyles = (t: OmiTheme) => ({
  base: {
    alignItems: 'center' as const,
    justifyContent: 'center' as const,
    borderRadius: t.radius.pill,
  },
  hovered: {backgroundColor: t.color.fill},
  selected: {backgroundColor: t.color.fillSelected},
  pressed: {backgroundColor: t.color.fillPressed},
});

/** Filter / segment chip. Active is ink-weighted fill plus hairline; never accent. */
export function OmiChip({
  label,
  selected,
  onPress,
  icon,
  count,
  accessibilityLabel,
}: {
  label: string;
  selected: boolean;
  onPress: () => void;
  icon?: MaterialIconName;
  count?: number;
  accessibilityLabel?: string;
}) {
  const theme = useOmiTheme();
  const styles = useOmiStyles(createChipStyles);
  const ink = selected ? theme.color.ink : theme.color.inkSecondary;
  return (
    <FocusPressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? label}
      accessibilityState={{selected}}
      onPress={onPress}
      hitSlop={hitSlopFor(theme, theme.size.controlCompact)}
      style={state => [
        styles.base,
        selected
          ? styles.selected
          : (state as PressState).hovered && styles.hovered,
        state.pressed && styles.pressed,
      ]}>
      {icon ? (
        <MaterialIcon name={icon} size={theme.size.iconSmall} color={ink} />
      ) : null}
      <Text numberOfLines={1} style={[styles.label, {color: ink}]}>
        {label}
      </Text>
      {count !== undefined ? <Text style={styles.count}>{count}</Text> : null}
    </FocusPressable>
  );
}

const createChipStyles = (t: OmiTheme) => ({
  base: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    gap: t.space.xs + 2,
    minHeight: t.size.controlCompact,
    paddingHorizontal: t.space.md,
    borderRadius: t.radius.pill,
    borderWidth: 1,
    borderColor: 'transparent',
  },
  selected: {
    backgroundColor: t.color.fillSelected,
    borderColor: t.color.separator,
  },
  hovered: {backgroundColor: t.color.fill},
  pressed: {backgroundColor: t.color.fillPressed},
  label: {...t.type.subhead, fontWeight: '500' as const},
  count: {...t.type.caption, color: t.color.inkTertiary},
});

/**
 * Quiet section label (e.g. a day header). Sentence or title case, secondary
 * ink, no fill and no uppercase slab: lists read as rows, not stacked cards.
 */
export function OmiSectionLabel({
  label,
  trailing,
}: {
  label: string;
  trailing?: string;
}) {
  const styles = useOmiStyles(createSectionStyles);
  return (
    <View accessibilityRole="header" style={styles.row}>
      <Text style={styles.label}>{label}</Text>
      {trailing ? <Text style={styles.trailing}>{trailing}</Text> : null}
    </View>
  );
}

const createSectionStyles = (t: OmiTheme) => ({
  row: {
    flexDirection: 'row' as const,
    alignItems: 'baseline' as const,
    justifyContent: 'space-between' as const,
    paddingTop: t.space.xl,
    paddingBottom: t.space.sm,
    paddingHorizontal: t.space.sm,
  },
  label: {
    ...t.type.footnote,
    fontWeight: '600' as const,
    color: t.color.inkSecondary,
  },
  trailing: {...t.type.caption, color: t.color.inkTertiary},
});

/**
 * List row: clear at rest, fill on hover, ink-weighted fill when selected.
 * Leading is usually a small icon tile; trailing holds a value or actions.
 */
export function OmiRow({
  title,
  subtitle,
  meta,
  leadingIcon,
  trailing,
  selected = false,
  onPress,
  accessibilityLabel,
}: {
  title: string;
  subtitle?: string;
  meta?: string;
  leadingIcon?: MaterialIconName;
  trailing?: React.ReactNode;
  selected?: boolean;
  onPress?: () => void;
  accessibilityLabel?: string;
}) {
  const theme = useOmiTheme();
  const styles = useOmiStyles(createRowStyles);
  const body = (
    <>
      {leadingIcon ? (
        <View style={styles.tile}>
          <MaterialIcon
            name={leadingIcon}
            size={theme.size.iconSmall}
            color={theme.color.inkSecondary}
          />
        </View>
      ) : null}
      <View style={styles.text}>
        <Text numberOfLines={2} style={styles.title}>
          {title}
        </Text>
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
      {trailing}
    </>
  );
  if (!onPress) {
    return (
      <View style={[styles.row, selected && styles.selected]}>{body}</View>
    );
  }
  return (
    <FocusPressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? title}
      accessibilityState={{selected}}
      onPress={onPress}
      style={state => [
        styles.row,
        selected
          ? styles.selected
          : (state as PressState).hovered && styles.hovered,
        state.pressed && styles.pressed,
      ]}>
      {body}
    </FocusPressable>
  );
}

const createRowStyles = (t: OmiTheme) => ({
  row: {
    flexDirection: 'row' as const,
    alignItems: 'flex-start' as const,
    gap: t.space.md,
    paddingVertical: t.density === 'desktop' ? t.space.sm + 2 : t.space.md,
    paddingHorizontal: t.space.sm,
    borderRadius: t.radius.row,
    borderWidth: 1,
    borderColor: 'transparent',
  },
  hovered: {backgroundColor: t.color.fill},
  selected: {
    backgroundColor: t.color.fillSelected,
    borderColor: t.color.separator,
  },
  pressed: {backgroundColor: t.color.fillPressed},
  tile: {
    width: t.size.controlCompact,
    height: t.size.controlCompact,
    borderRadius: t.radius.row - 4,
    backgroundColor: t.color.fill,
    alignItems: 'center' as const,
    justifyContent: 'center' as const,
  },
  text: {flex: 1, minWidth: 0, gap: 2},
  title: {...t.type.headline, color: t.color.ink},
  subtitle: {...t.type.subhead, color: t.color.inkSecondary},
  meta: {
    ...t.type.caption,
    color: t.color.inkTertiary,
    fontWeight: '400' as const,
  },
});

/**
 * Whole-surface state. Loading: one spinner and a label. Error: says what
 * failed ("Couldn't Load Conversations") and offers Try Again. Empty: glyph,
 * Title Case title, one sentence, at most one action.
 */
export function OmiPageState(
  props:
    | {kind: 'loading'; label: string}
    | {kind: 'error'; title: string; message?: string; onRetry?: () => void}
    | {
        kind: 'empty';
        icon: MaterialIconName;
        title: string;
        message?: string;
        action?: {label: string; onPress: () => void};
      },
) {
  const theme = useOmiTheme();
  const styles = useOmiStyles(createPageStateStyles);
  if (props.kind === 'loading') {
    return (
      <View
        style={styles.root}
        accessibilityRole="progressbar"
        accessibilityLabel={props.label}>
        <ActivityIndicator size="small" color={theme.color.inkSecondary} />
        <Text style={styles.message}>{props.label}</Text>
      </View>
    );
  }
  if (props.kind === 'error') {
    return (
      <View style={styles.root}>
        <MaterialIcon name="info" size={28} color={theme.color.inkSecondary} />
        <Text style={styles.title}>{props.title}</Text>
        {props.message ? (
          <Text style={styles.message}>{props.message}</Text>
        ) : null}
        {props.onRetry ? (
          <OmiButton label="Try Again" compact onPress={props.onRetry} />
        ) : null}
      </View>
    );
  }
  return (
    <View style={styles.root}>
      <MaterialIcon
        name={props.icon}
        size={28}
        color={theme.color.inkTertiary}
      />
      <Text style={styles.title}>{props.title}</Text>
      {props.message ? (
        <Text style={styles.message}>{props.message}</Text>
      ) : null}
      {props.action ? (
        <OmiButton
          label={props.action.label}
          compact
          onPress={props.action.onPress}
        />
      ) : null}
    </View>
  );
}

const createPageStateStyles = (t: OmiTheme) => ({
  root: {
    alignItems: 'center' as const,
    justifyContent: 'center' as const,
    gap: t.space.sm,
    paddingVertical: t.space.section,
    paddingHorizontal: t.space.xxl,
  },
  title: {...t.type.headline, color: t.color.ink, textAlign: 'center' as const},
  message: {
    ...t.type.subhead,
    color: t.color.inkSecondary,
    textAlign: 'center' as const,
    maxWidth: 360,
  },
});
