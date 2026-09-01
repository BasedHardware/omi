import React from 'react';
import {StyleSheet, Text, TextInput, View} from 'react-native';
import House from 'lucide-react-native/icons/house';
import MessageCircle from 'lucide-react-native/icons/message-circle';
import ListFilter from 'lucide-react-native/icons/list-filter';
import Puzzle from 'lucide-react-native/icons/puzzle';
import Search from 'lucide-react-native/icons/search';
import Settings from 'lucide-react-native/icons/settings';
import {FocusPressable} from '../ui/Pressable';
import {
  desktopNavBarHeight,
  desktopNavItems,
  desktopOmnibarHeight,
  desktopSearchPlaceholder,
  desktopTrafficLightButton,
  desktopTrafficLightRowWidth,
  type DesktopNavItem,
} from './desktopChrome';
import {ShippingPressable} from './ShippingPressable';
import {desktopTokens as token} from './tokens';

export type DesktopRoute = DesktopNavItem | 'Settings';

const navIcons: Record<DesktopNavItem, typeof Search> = {
  Home: House,
  Conversations: MessageCircle,
  Tasks: ListFilter,
  Apps: Puzzle,
};

type Props = {
  route: DesktopRoute;
  onNavigate: (route: DesktopRoute) => void;
  draft: string;
  onDraftChange: (value: string) => void;
  onSend: () => void;
  chatNotice: string | null;
  omnibarRef: React.RefObject<TextInput | null>;
};

export function DesktopChrome({
  chatNotice,
  draft,
  omnibarRef,
  onDraftChange,
  onNavigate,
  onSend,
  route,
}: Props) {
  return (
    <View accessibilityLabel="Omi desktop chrome" style={styles.chrome}>
      <View style={styles.row}>
        <View
          accessibilityLabel="Window controls"
          pointerEvents="none"
          style={styles.windowControls}
        />
        <View style={styles.nav}>
          {desktopNavItems.map(label => {
            const Icon = navIcons[label];
            const active = route === label;
            return (
              <ShippingPressable
                accessibilityLabel={label}
                accessibilityRole="button"
                accessibilityState={{selected: active}}
                key={label}
                onPress={() => onNavigate(label)}
                style={styles.navItem}>
                <Icon color={token.color.ink} size={14} />
                <Text style={[styles.navText, active && styles.navTextActive]}>
                  {label}
                </Text>
              </ShippingPressable>
            );
          })}
        </View>
        <ShippingPressable
          accessibilityLabel="Settings"
          accessibilityRole="button"
          accessibilityState={{selected: route === 'Settings'}}
          onPress={() => onNavigate('Settings')}
          style={styles.settingsButton}>
          <Settings color={token.color.ink} size={15} />
        </ShippingPressable>
      </View>
      <View style={styles.omnibar}>
        <Search color={token.color.inkMuted} size={15} />
        <TextInput
          accessibilityLabel="Search what you have seen and heard"
          blurOnSubmit={false}
          onChangeText={onDraftChange}
          onSubmitEditing={onSend}
          placeholder={desktopSearchPlaceholder}
          placeholderTextColor={token.color.inkMuted}
          ref={omnibarRef}
          style={styles.omnibarInput}
          value={draft}
        />
        <FocusPressable
          accessibilityLabel="Send"
          accessibilityRole="button"
          onPress={onSend}
          style={({pressed}) => [styles.send, pressed && styles.pressed]}>
          <Text style={styles.sendText}>Ask</Text>
        </FocusPressable>
      </View>
      {chatNotice === null ? null : (
        <Text
          accessibilityLabel="Chat transport notice"
          numberOfLines={1}
          style={styles.notice}>
          {chatNotice}
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  chrome: {
    gap: 10,
    marginBottom: 8,
  },
  row: {
    alignItems: 'center',
    flexDirection: 'row',
    height: desktopNavBarHeight,
  },
  windowControls: {
    alignSelf: 'center',
    height: desktopTrafficLightButton,
    width: desktopTrafficLightRowWidth,
  },
  nav: {
    alignItems: 'center',
    flex: 1,
    flexDirection: 'row',
    flexShrink: 1,
    gap: 6,
  },
  navItem: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 6,
    height: 34,
    justifyContent: 'center',
    paddingHorizontal: 10,
  },
  navText: {
    color: token.color.inkMuted,
    fontFamily: token.font,
    fontSize: token.type.nav,
    fontWeight: '500',
  },
  navTextActive: {
    color: token.color.ink,
    fontWeight: '700',
    textDecorationLine: 'underline',
  },
  omnibar: {
    alignItems: 'center',
    alignSelf: 'stretch',
    backgroundColor: token.color.glassQuiet,
    borderRadius: 14,
    flexDirection: 'row',
    gap: 8,
    height: desktopOmnibarHeight,
    minWidth: 220,
    paddingHorizontal: 12,
  },
  omnibarInput: {
    color: token.color.ink,
    flex: 1,
    flexGrow: 1,
    flexShrink: 1,
    fontFamily: token.font,
    fontSize: token.type.search,
    fontWeight: '400',
    height: desktopOmnibarHeight,
    minWidth: 0,
    paddingVertical: 0,
  },
  notice: {
    color: token.color.inkMuted,
    fontFamily: token.font,
    fontSize: token.type.meta,
    paddingHorizontal: 4,
  },
  send: {
    alignItems: 'center',
    flexShrink: 0,
    height: 30,
    justifyContent: 'center',
    paddingHorizontal: 6,
  },
  sendText: {
    color: token.color.ink,
    fontFamily: token.font,
    fontSize: token.type.caption,
    fontWeight: '600',
  },
  settingsButton: {
    alignItems: 'center',
    flexShrink: 0,
    height: 34,
    justifyContent: 'center',
    width: 34,
  },
  pressed: {opacity: 0.78},
});
