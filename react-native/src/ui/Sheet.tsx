import React from 'react';
import {StyleSheet, Text, View} from 'react-native';
import {MaterialIcon, type MaterialIconName} from './MaterialIcon';

import type {Route} from '../app/routes';
import {FocusPressable} from './Pressable';
import {
  type KitTokens,
  useDesktopThemeKit,
  useKitStyleSheets,
} from '../desktop/DesktopTheme';

const destinations: Array<{
  icon: MaterialIconName;
  label: Route;
}> = [
  {icon: 'home', label: 'Home'},
  {icon: 'view_timeline', label: 'Conversations'},
  {icon: 'neurology', label: 'Memories'},
  {icon: 'checklist', label: 'Tasks'},
  {icon: 'extension', label: 'Connectors'},
  {icon: 'settings', label: 'Settings'},
];

export function Sheet({
  onDismiss,
  onSelect,
  route,
}: {
  onDismiss: () => void;
  onSelect: (route: Route) => void;
  route: Route;
}) {
  const styles = useKitStyleSheets(createStyles);
  const {tokens} = useDesktopThemeKit();
  return (
    <View pointerEvents="box-none" style={styles.layer}>
      <FocusPressable
        accessibilityLabel="Dismiss destination switcher"
        accessibilityRole="button"
        onPress={onDismiss}
        style={styles.dismiss}
      />
      <View
        accessibilityLabel="Home destination switcher"
        accessibilityRole="menu"
        pointerEvents="auto"
        style={styles.menu}>
        {destinations.map(destination => (
          <FocusPressable
            accessibilityLabel={`${destination.label} destination`}
            accessibilityRole="menuitem"
            accessibilityState={{selected: route === destination.label}}
            hitSlop={{bottom: 6, left: 8, right: 8, top: 6}}
            key={destination.label}
            onPress={() => onSelect(destination.label)}
            style={({pressed}) => [
              styles.item,
              route === destination.label && styles.itemActive,
              pressed && styles.pressed,
            ]}>
            <MaterialIcon
              color={
                route === destination.label
                  ? tokens.color.text
                  : tokens.color.menuText
              }
              name={destination.icon}
              size={16}
            />
            <Text
              style={[
                styles.itemText,
                route === destination.label && styles.itemTextActive,
              ]}>
              {destination.label}
            </Text>
            {route === destination.label && <View style={styles.selection} />}
          </FocusPressable>
        ))}
      </View>
    </View>
  );
}

const createStyles = (tokens: KitTokens) =>
  StyleSheet.create({
    layer: {
      bottom: tokens.space.none,
      left: tokens.space.none,
      position: 'absolute',
      right: tokens.space.none,
      top: tokens.space.none,
      zIndex: 40,
    },
    dismiss: {
      bottom: tokens.space.none,
      left: tokens.space.none,
      position: 'absolute',
      right: tokens.space.none,
      top: tokens.space.none,
    },
    menu: {
      backgroundColor: tokens.color.menu,
      borderColor: tokens.color.line,
      borderRadius: tokens.radius.md,
      borderWidth: tokens.border.width,
      gap: tokens.space.xxs,
      padding: 7,
      pointerEvents: 'auto',
      position: 'absolute',
      right: tokens.space.lg,
      top: tokens.size.sheetTop,
      width: tokens.size.sheet,
      zIndex: 41,
    },
    item: {
      alignItems: 'center',
      borderRadius: tokens.space.sm,
      flexDirection: 'row',
      gap: 10,
      minHeight: tokens.size.control,
      paddingHorizontal: tokens.space.md,
    },
    itemActive: {backgroundColor: tokens.color.input},
    itemText: {
      color: tokens.color.menuTextStrong,
      flex: 1,
      ...tokens.type.label,
    },
    itemTextActive: {color: tokens.color.text},
    selection: {
      backgroundColor: tokens.color.focus,
      borderRadius: 3,
      height: 6,
      width: 6,
    },
    pressed: {opacity: tokens.opacity.pressed},
  });
