import React from 'react';
import {StyleSheet, Text, TextInput, View} from 'react-native';
import Brain from 'lucide-react-native/icons/brain';
import GanttChartSquare from 'lucide-react-native/icons/square-chart-gantt';
import House from 'lucide-react-native/icons/house';
import ListChecks from 'lucide-react-native/icons/list-checks';
import PanelLeft from 'lucide-react-native/icons/panel-left';
import PanelLeftClose from 'lucide-react-native/icons/panel-left-close';
import type {Route} from '../app/routes';
import {HomeSearchField} from './SearchField';
import {Icon, type IconComponent} from './Icon';
import {FocusPressable} from './Pressable';
import {tokens} from './tokens';

const destinationIcons: Record<
  Route,
  {fallback: IconComponent; symbolName: string}
> = {
  Home: {fallback: House, symbolName: 'house'},
  Conversations: {
    fallback: GanttChartSquare,
    symbolName: 'bubble.left.and.bubble.right',
  },
  Memories: {fallback: Brain, symbolName: 'brain'},
  Tasks: {fallback: ListChecks, symbolName: 'checklist'},
  Connectors: {fallback: PanelLeftClose, symbolName: 'link'},
  Settings: {fallback: PanelLeft, symbolName: 'gearshape'},
};

export type ToolbarProps = {
  inputRef: React.RefObject<TextInput | null>;
  menuOpen: boolean;
  onOpenChat: () => void;
  onQueryChange: (value: string) => void;
  onSearchBlur: () => void;
  onSearchFocus: () => void;
  onSearchPress: () => void;
  onToggleMenu: () => void;
  query: string;
  route: Route;
  searchArmed: boolean;
  searchFocused: boolean;
};

export function Toolbar({
  inputRef,
  menuOpen,
  onOpenChat,
  onQueryChange,
  onSearchBlur,
  onSearchFocus,
  onSearchPress,
  onToggleMenu,
  query,
  route,
  searchArmed,
  searchFocused,
}: ToolbarProps) {
  const destination = destinationIcons[route];
  return (
    <View accessibilityLabel="Desktop application chrome" style={styles.frame}>
      <View accessibilityLabel="Desktop navigation" style={styles.row}>
        <HomeSearchField
          compact={false}
          desktop
          inputRef={inputRef}
          onBlur={onSearchBlur}
          onChangeText={onQueryChange}
          onFocus={onSearchFocus}
          onOpenChat={onOpenChat}
          onPressIn={onSearchPress}
          query={query}
          searchArmed={searchArmed}
          searchFocused={searchFocused}
        />
        <View pointerEvents="auto" style={styles.actions}>
          <FocusPressable
            accessibilityHint="Shows destinations"
            accessibilityLabel="Home navigation"
            accessibilityRole="button"
            accessibilityState={{expanded: menuOpen}}
            hitSlop={{
              bottom: tokens.space.sm,
              left: tokens.space.sm,
              right: tokens.space.sm,
              top: tokens.space.sm,
            }}
            onPress={onToggleMenu}
            style={({pressed}) => [styles.home, pressed && styles.pressed]}>
            <Icon
              color={tokens.color.text}
              fallback={destination.fallback}
              size={tokens.size.iconChrome}
              symbolColor={tokens.color.text}
              symbolName={destination.symbolName}
            />
            <Text style={styles.homeText}>{route}</Text>
          </FocusPressable>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  frame: {
    alignSelf: 'stretch',
    backgroundColor: tokens.color.chrome,
    borderRadius: tokens.radius.none,
    height: tokens.size.toolbar,
    marginHorizontal: tokens.space.none,
    marginTop: tokens.space.none,
    overflow: 'visible',
    paddingHorizontal: tokens.space.md,
    pointerEvents: 'auto',
    zIndex: tokens.size.iconLarge,
  },
  row: {
    alignItems: 'center',
    backgroundColor: tokens.color.transparent,
    flex: tokens.layout.grow,
    flexDirection: 'row',
    gap: tokens.space.md,
    height: tokens.size.toolbar,
    overflow: 'visible',
    pointerEvents: 'auto',
    position: 'relative',
  },
  actions: {
    alignItems: 'center',
    flexDirection: 'row',
    flexShrink: 0,
    gap: tokens.space.xxs,
    pointerEvents: 'auto',
  },
  home: {
    alignItems: 'center',
    backgroundColor: tokens.color.input,
    borderRadius: tokens.radius.lg,
    flexDirection: 'row',
    gap: tokens.space.sm,
    height: tokens.size.controlCompact,
    paddingHorizontal: tokens.space.md,
  },
  homeText: {...tokens.type.label, color: tokens.color.text},
  pressed: {opacity: tokens.opacity.pressed},
});
