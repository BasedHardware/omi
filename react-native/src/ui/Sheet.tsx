import React from 'react';
import {StyleSheet, Text, View} from 'react-native';
import Brain from 'lucide-react-native/icons/brain';
import GanttChartSquare from 'lucide-react-native/icons/square-chart-gantt';
import House from 'lucide-react-native/icons/house';
import ListChecks from 'lucide-react-native/icons/list-checks';
import PanelLeft from 'lucide-react-native/icons/panel-left';
import PanelLeftClose from 'lucide-react-native/icons/panel-left-close';
import type {Route} from '../app/routes';
import {Icon, type IconComponent} from './Icon';
import {FocusPressable} from './Pressable';
import {tokens} from './tokens';

const destinations: Array<{
  fallback: IconComponent;
  label: Route;
  symbolName: string;
}> = [
  {fallback: House, label: 'Home', symbolName: 'house'},
  {
    fallback: GanttChartSquare,
    label: 'Conversations',
    symbolName: 'bubble.left.and.bubble.right',
  },
  {fallback: Brain, label: 'Memories', symbolName: 'brain'},
  {fallback: ListChecks, label: 'Tasks', symbolName: 'checklist'},
  {fallback: PanelLeftClose, label: 'Connectors', symbolName: 'link'},
  {fallback: PanelLeft, label: 'Settings', symbolName: 'gearshape'},
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
            <Icon
              color={
                route === destination.label
                  ? tokens.color.text
                  : tokens.color.menuText
              }
              fallback={destination.fallback}
              size={16}
              symbolName={destination.symbolName}
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

const styles = StyleSheet.create({
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
    borderColor: tokens.color.transparent,
    borderRadius: tokens.radius.lg,
    borderWidth: tokens.space.none,
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
