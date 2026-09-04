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
  navFrameMoved,
  type DesktopNavFrame,
  type DesktopNavItem,
} from './desktopChrome';
import {desktopEaseSmoothOut} from './desktopMotion';
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
  activeGenerationId: string | null;
  route: DesktopRoute;
  onNavigate: (route: DesktopRoute) => void;
  draft: string;
  onDraftChange: (value: string) => void;
  onSend: () => void;
  onStop: () => void;
  chatNotice: string | null;
  omnibarRef: React.RefObject<TextInput | null>;
};

export function DesktopChrome({
  activeGenerationId,
  chatNotice,
  draft,
  omnibarRef,
  onDraftChange,
  onNavigate,
  onSend,
  onStop,
  route,
}: Props) {
  const reduceMotion = useReduceMotion();
  const [frames, setFrames] = useState<
    Partial<Record<DesktopNavItem, DesktopNavFrame>>
  >({});
  const pillX = useRef(new Animated.Value(0)).current;
  const pillW = useRef(new Animated.Value(0)).current;
  const pillOpacity = useRef(new Animated.Value(0)).current;
  const placed = useRef(false);
  const animating = useRef(false);
  const lastTarget = useRef({x: -1, width: -1});
  const activeNav = route === 'Settings' ? null : route;
  const activeFrame = activeNav === null ? undefined : frames[activeNav];
  const activeX = activeFrame?.x;
  const activeWidth = activeFrame?.width;

  useEffect(() => {
    if (activeNav === null) {
      pillOpacity.setValue(0);
      return;
    }
    if (activeX === undefined || activeWidth === undefined) {
      return;
    }
    const target = {x: activeX, width: activeWidth};
    const same = !navFrameMoved(lastTarget.current, target);
    if (same) {
      pillOpacity.setValue(1);
      return;
    }
    lastTarget.current = target;
    if (!placed.current || reduceMotion) {
      pillX.setValue(target.x);
      pillW.setValue(target.width);
      pillOpacity.setValue(1);
      placed.current = true;
      return;
    }
    animating.current = true;
    const ease = desktopEaseSmoothOut();
    Animated.parallel([
      Animated.timing(pillX, {
        duration: desktopMotion.navMs,
        easing: ease,
        toValue: target.x,
        useNativeDriver: false,
      }),
      Animated.timing(pillW, {
        duration: desktopMotion.navMs,
        easing: ease,
        toValue: target.width,
        useNativeDriver: false,
      }),
      Animated.timing(pillOpacity, {
        duration: desktopMotion.quickMs,
        easing: ease,
        toValue: 1,
        useNativeDriver: false,
      }),
    ]).start(() => {
      animating.current = false;
    });
  }, [
    activeNav,
    activeWidth,
    activeX,
    pillOpacity,
    pillW,
    pillX,
    reduceMotion,
  ]);

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
          {desktopNavItems.map((label, index) => {
            const Icon = navIcons[label];
            const active = route === label;
            return (
              <View
                key={label}
                onLayout={event => {
                  if (animating.current) {
                    return;
                  }
                  const {x, width} = event.nativeEvent.layout;
                  setFrames(current => {
                    const next = {width, x};
                    if (!navFrameMoved(current[label], next)) {
                      return current;
                    }
                    return {...current, [label]: next};
                  });
                }}
                style={[
                  styles.navItem,
                  index < desktopNavItems.length - 1 && styles.navItemFollow,
                ]}>
                <FocusPressable
                  accessibilityLabel={label}
                  accessibilityRole="button"
                  accessibilityState={{selected: active}}
                  onPress={() => onNavigate(label)}
                  style={({pressed}) => [
                    styles.navHit,
                    pressed && styles.pressed,
                  ]}>
                  <View style={styles.navIcon}>
                    <Icon color={token.color.ink} size={14} />
                  </View>
                  <Text
                    style={[styles.navText, active && styles.navTextActive]}>
                    {label}
                  </Text>
                </FocusPressable>
              </View>
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
          accessibilityLabel={activeGenerationId === null ? 'Send' : 'Stop'}
          accessibilityRole="button"
          onPress={activeGenerationId === null ? onSend : onStop}
          style={({pressed}) => [styles.send, pressed && styles.pressed]}>
          <Text style={styles.sendText}>
            {activeGenerationId === null ? 'Ask' : 'Stop'}
          </Text>
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
    position: 'relative',
  },
  navPill: {
    backgroundColor: token.color.glassSelected,
    borderRadius: token.radius.chip,
    bottom: 6,
    left: 0,
    position: 'absolute',
    top: 6,
  },
  navItem: {
    height: 40,
    paddingHorizontal: 16,
    zIndex: 1,
  },
  navItemFollow: {
    marginRight: 6,
  },
  navHit: {
    alignItems: 'center',
    flex: 1,
    flexDirection: 'row',
    height: 40,
    justifyContent: 'center',
  },
  navIcon: {
    marginRight: 7,
  },
  navText: {
    color: token.color.inkMuted,
    fontFamily: token.font,
    fontSize: token.type.nav,
    fontWeight: '500',
  },
  navTextActive: {
    color: token.color.ink,
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
