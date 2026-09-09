import React, {useEffect, useRef, useState} from 'react';
import {
  Animated,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from 'react-native';
import Search from 'lucide-react-native/icons/search';
import ArrowUp from 'lucide-react-native/icons/arrow-up';
import Square from 'lucide-react-native/icons/square';
import House from 'lucide-react-native/icons/house';
import MessageCircle from 'lucide-react-native/icons/message-circle';
import MessageSquare from 'lucide-react-native/icons/message-square';
import ListFilter from 'lucide-react-native/icons/list-filter';
import Puzzle from 'lucide-react-native/icons/puzzle';
import History from 'lucide-react-native/icons/rotate-ccw-clock';
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

const navIcons: Record<DesktopNavItem, typeof House> = {
  Home: House,
  Chat: MessageSquare,
  Conversations: MessageCircle,
  Rewind: History,
  Tasks: ListFilter,
  Apps: Puzzle,
};

export type OmnibarMode = 'Ask' | 'Search' | 'Recall';

type Props = {
  chatBusy?: boolean;
  capture?: ReturnType<
    typeof import('../app/useRewindCapture').useRewindCapture
  >;
  mode?: OmnibarMode;
  onModeChange?: (mode: OmnibarMode) => void;
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
  chatBusy = false,
  capture,
  mode = 'Ask',
  onModeChange,
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
  const canStop = mode === 'Ask' && activeGenerationId !== null;
  const sending = mode === 'Ask' && chatBusy && !canStop;
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
    const animation = Animated.parallel([
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
    ]);
    animation.start(() => {
      animating.current = false;
    });
    return () => {
      animation.stop();
      animating.current = false;
    };
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
                  accessibilityLabel={label === 'Rewind' ? 'Recall' : label}
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
                    {label === 'Rewind' ? 'Recall' : label}
                  </Text>
                </FocusPressable>
              </View>
            );
          })}
        </View>
        {capture ? (
          <View style={styles.captureControl}>
            <Text style={styles.captureLabel}>
              {capture.busy ? 'Waiting…' : 'Capture'}
            </Text>
            <Switch
              accessibilityLabel="Screen capture"
              accessibilityHint={
                capture.available
                  ? 'Start or stop screen capture on this Mac'
                  : 'Capture is available in the native Mac app'
              }
              disabled={!capture.available}
              value={capture.capturing || capture.busy}
              onValueChange={value => {
                if (value) {
                  capture.start();
                } else {
                  capture.stop();
                }
              }}
              trackColor={{
                false: token.color.glassSelected,
                true: token.color.inkMuted,
              }}
            />
          </View>
        ) : null}
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
      {capture?.error ? (
        <Text accessibilityRole="alert" style={styles.notice}>
          {capture.error}
        </Text>
      ) : null}
      <View style={styles.omnibar}>
        <View style={styles.modes}>
          {(['Ask', 'Search', 'Recall'] as const).map(value => {
            const Icon =
              value === 'Ask'
                ? MessageCircle
                : value === 'Search'
                ? Search
                : History;
            return (
              <FocusPressable
                key={value}
                accessibilityRole="button"
                accessibilityLabel={`Use ${value} mode`}
                accessibilityState={{selected: mode === value}}
                onPress={() => onModeChange?.(value)}
                style={[
                  styles.modeButton,
                  mode === value && styles.modeActive,
                ]}>
                <Icon
                  size={15}
                  color={
                    mode === value ? token.color.ink : token.color.inkMuted
                  }
                />
              </FocusPressable>
            );
          })}
        </View>
        <TextInput
          accessibilityLabel={
            mode === 'Ask'
              ? 'Ask Omi'
              : mode === 'Recall'
              ? 'Search Recall'
              : 'Search history'
          }
          blurOnSubmit={false}
          onChangeText={onDraftChange}
          onSubmitEditing={() => {
            if (mode !== 'Ask' || (!chatBusy && draft.trim())) {
              onSend();
            }
          }}
          placeholder={
            mode === 'Recall'
              ? 'Find a moment on your screen…'
              : mode === 'Ask'
              ? 'Ask about your day…'
              : desktopSearchPlaceholder
          }
          placeholderTextColor={token.color.inkMuted}
          ref={omnibarRef}
          style={styles.omnibarInput}
          value={draft}
        />
        <FocusPressable
          accessibilityLabel={
            canStop
              ? 'Stop'
              : sending
              ? 'Sending…'
              : mode === 'Ask'
              ? 'Send'
              : 'Search'
          }
          accessibilityRole="button"
          disabled={mode === 'Ask' && !canStop && (chatBusy || !draft.trim())}
          onPress={() => {
            if (canStop) {
              onStop();
            } else if (mode !== 'Ask' || (!chatBusy && draft.trim())) {
              onSend();
            }
          }}
          style={({pressed}) => [styles.send, pressed && styles.pressed]}>
          {canStop ? (
            <Square size={15} color={token.color.ink} />
          ) : mode === 'Ask' ? (
            <ArrowUp size={17} color={token.color.ink} />
          ) : (
            <Search size={16} color={token.color.ink} />
          )}
        </FocusPressable>
      </View>
      {mode === 'Ask' ? (
        <Text style={styles.submitHint}>Enter to submit</Text>
      ) : null}
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
  captureControl: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginHorizontal: 8,
  },
  captureLabel: {fontSize: 12, color: token.color.inkMuted},
  modes: {flexDirection: 'row', alignItems: 'center', gap: 2},
  modeButton: {
    width: 32,
    height: 32,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 12,
  },
  modeActive: {backgroundColor: token.color.glassSelected},
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
    borderRadius: 22,
    flexDirection: 'row',
    gap: 8,
    height: desktopOmnibarHeight,
    minWidth: 220,
    paddingHorizontal: 8,
    paddingVertical: 6,
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
    height: 32,
    paddingHorizontal: 4,
    paddingVertical: 6,
    textAlignVertical: 'center',
  },
  submitHint: {color: token.color.inkMuted, fontSize: 11, paddingHorizontal: 4},
  notice: {
    color: token.color.inkMuted,
    fontFamily: token.font,
    fontSize: token.type.meta,
    paddingHorizontal: 4,
  },
  send: {
    alignItems: 'center',
    flexShrink: 0,
    height: 32,
    width: 32,
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
