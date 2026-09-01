import React, {useEffect, useRef, useState} from 'react';
import {Animated, StyleSheet, Text, TextInput, View} from 'react-native';
import House from 'lucide-react-native/icons/house';
import MessageCircle from 'lucide-react-native/icons/message-circle';
import ListFilter from 'lucide-react-native/icons/list-filter';
import Puzzle from 'lucide-react-native/icons/puzzle';
import Search from 'lucide-react-native/icons/search';
import Settings from 'lucide-react-native/icons/settings';
import {FocusPressable} from '../ui/Pressable';
import {useReduceMotion} from '../app/useReduceMotion';
import {
  desktopMotion,
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

type ItemFrame = {x: number; width: number};

export function DesktopChrome({
  chatNotice,
  draft,
  omnibarRef,
  onDraftChange,
  onNavigate,
  onSend,
  route,
}: Props) {
  const reduceMotion = useReduceMotion();
  const [frames, setFrames] = useState<
    Partial<Record<DesktopNavItem, ItemFrame>>
  >({});
  const pillX = useRef(new Animated.Value(0)).current;
  const pillW = useRef(new Animated.Value(0)).current;
  const pillOpacity = useRef(new Animated.Value(0)).current;
  const activeNav = route === 'Settings' ? null : route;
  const activeFrame = activeNav === null ? undefined : frames[activeNav];

  useEffect(() => {
    if (activeFrame === undefined) {
      if (reduceMotion) {
        pillOpacity.setValue(0);
        return;
      }
      const hide = Animated.timing(pillOpacity, {
        duration: desktopMotion.navMs,
        toValue: 0,
        useNativeDriver: false,
      });
      hide.start();
      return () => hide.stop();
    }
    const moves = [
      Animated.timing(pillX, {
        duration: reduceMotion ? 0 : desktopMotion.stepMs,
        toValue: activeFrame.x,
        useNativeDriver: false,
      }),
      Animated.timing(pillW, {
        duration: reduceMotion ? 0 : desktopMotion.stepMs,
        toValue: activeFrame.width,
        useNativeDriver: false,
      }),
      Animated.timing(pillOpacity, {
        duration: reduceMotion ? 0 : desktopMotion.navMs,
        toValue: 1,
        useNativeDriver: false,
      }),
    ];
    const animation = Animated.parallel(moves);
    animation.start();
    return () => animation.stop();
  }, [activeFrame, pillOpacity, pillW, pillX, reduceMotion]);

  return (
    <View accessibilityLabel="Omi desktop chrome" style={styles.chrome}>
      <View style={styles.row}>
        <View
          accessibilityLabel="Window controls"
          pointerEvents="none"
          style={styles.windowControls}
        />
        <View style={styles.nav}>
          <Animated.View
            pointerEvents="none"
            style={[
              styles.navPill,
              {
                opacity: pillOpacity,
                transform: [{translateX: pillX}],
                width: pillW,
              },
            ]}
          />
          {desktopNavItems.map(label => {
            const Icon = navIcons[label];
            const active = route === label;
            return (
              <FocusPressable
                accessibilityLabel={label}
                accessibilityRole="button"
                accessibilityState={{selected: active}}
                key={label}
                onLayout={event => {
                  const {x, width} = event.nativeEvent.layout;
                  setFrames(current => {
                    const previous = current[label];
                    if (previous?.x === x && previous.width === width) {
                      return current;
                    }
                    return {...current, [label]: {width, x}};
                  });
                }}
                onPress={() => onNavigate(label)}
                style={({pressed}) => [
                  styles.navItem,
                  pressed && styles.pressed,
                ]}>
                <Icon color={token.color.ink} size={14} />
                <Text style={[styles.navText, active && styles.navTextActive]}>
                  {label}
                </Text>
              </FocusPressable>
            );
          })}
        </View>
        <ShippingPressable
          accessibilityLabel="Settings"
          accessibilityRole="button"
          accessibilityState={{selected: route === 'Settings'}}
          active={route === 'Settings'}
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
    position: 'relative',
  },
  navPill: {
    backgroundColor: token.color.glassSelected,
    borderRadius: token.radius.chip,
    bottom: 9,
    left: 0,
    position: 'absolute',
    top: 9,
  },
  navItem: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 6,
    height: 34,
    justifyContent: 'center',
    paddingHorizontal: 10,
    zIndex: 1,
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
  },
  omnibar: {
    alignItems: 'center',
    alignSelf: 'stretch',
    backgroundColor: token.color.glassQuiet,
    borderRadius: 20,
    flexDirection: 'row',
    gap: 8,
    height: desktopOmnibarHeight,
    minWidth: 220,
    paddingHorizontal: 14,
  },
  omnibarInput: {
    color: token.color.ink,
    flex: 1,
    flexGrow: 1,
    flexShrink: 1,
    fontFamily: token.font,
    fontSize: token.type.search,
    fontWeight: '400',
    lineHeight: 20,
    minWidth: 0,
    paddingVertical: 10,
    textAlignVertical: 'center',
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
    borderRadius: 17,
    flexShrink: 0,
    height: 34,
    justifyContent: 'center',
    overflow: 'hidden',
    width: 34,
  },
  pressed: {opacity: 0.78},
});
