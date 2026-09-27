import React, {useEffect, useMemo, useRef, useState} from 'react';
import {
  Animated,
  Easing,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import {MaterialIcon, type MaterialIconName} from '../ui/MaterialIcon';

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
import {
  type DesktopTokens,
  useDesktopTheme,
  useDesktopStyleSheets,
} from './DesktopTheme';

export type DesktopRoute = DesktopNavItem | 'Settings';

const navIcons: Record<DesktopNavItem, MaterialIconName> = {
  Home: 'home',
  Chat: 'chat',
  Conversations: 'chat_bubble',
  Rewind: 'history',
  Tasks: 'checklist',
};

export type OmnibarMode = 'Ask' | 'Search';

type Props = {
  chatBusy?: boolean;
  mode?: OmnibarMode;
  onModeChange?: (mode: OmnibarMode) => void;
  liveControl?: React.ReactNode;
  activeGenerationId: string | null;
  route: DesktopRoute;
  onNavigate: (route: DesktopRoute) => void;
  // Screen-capture toggle shown in the nav row when capture is available.
  captureActive?: boolean;
  captureAvailable?: boolean;
  captureBusy?: boolean;
  onToggleCapture?: (() => void) | null;
  draft: string;
  onDraftChange: (value: string) => void;
  onSend: () => void;
  onStop: () => void;
  chatNotice: string | null;
  omnibarRef: React.RefObject<TextInput | null>;
  // When set, a decorative fake cursor travels to this destination in the
  // chrome (nav pill or the settings gear) and nudges it until dismissed.
  guideTarget?: DesktopRoute | null;
};

export function DesktopChrome({
  chatBusy = false,
  mode = 'Ask',
  onModeChange,
  liveControl,
  activeGenerationId,
  chatNotice,
  draft,
  omnibarRef,
  onDraftChange,
  onNavigate,
  onSend,
  onStop,
  route,
  captureActive = false,
  captureAvailable = false,
  captureBusy = false,
  onToggleCapture = null,
  guideTarget = null,
}: Props) {
  const styles = useDesktopStyleSheets(createStyles);
  const {tokens: token} = useDesktopTheme();
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

  // Sliding selection pill for the omnibar mode switcher, mirroring the nav
  // pill above so the two controls feel like one system.
  const [modeFrames, setModeFrames] = useState<
    Partial<Record<OmnibarMode, {x: number; width: number}>>
  >({});
  const modePillX = useRef(new Animated.Value(0)).current;
  const modePillW = useRef(new Animated.Value(0)).current;
  const modePillOpacity = useRef(new Animated.Value(0)).current;
  const modePlaced = useRef(false);
  const activeModeFrame = modeFrames[mode];
  useEffect(() => {
    if (activeModeFrame === undefined) {
      return;
    }
    if (!modePlaced.current || reduceMotion) {
      modePillX.setValue(activeModeFrame.x);
      modePillW.setValue(activeModeFrame.width);
      modePillOpacity.setValue(1);
      modePlaced.current = true;
      return;
    }
    const ease = desktopEaseSmoothOut();
    const animation = Animated.parallel([
      Animated.timing(modePillX, {
        duration: desktopMotion.navMs,
        easing: ease,
        toValue: activeModeFrame.x,
        useNativeDriver: false,
      }),
      Animated.timing(modePillW, {
        duration: desktopMotion.navMs,
        easing: ease,
        toValue: activeModeFrame.width,
        useNativeDriver: false,
      }),
      Animated.timing(modePillOpacity, {
        duration: desktopMotion.quickMs,
        easing: ease,
        toValue: 1,
        useNativeDriver: false,
      }),
    ]);
    animation.start();
    return () => animation.stop();
  }, [activeModeFrame, modePillOpacity, modePillW, modePillX, reduceMotion]);

  // Decorative guide cursor: it flies from the omnibar to the destination the
  // checklist is pointing at and gently nudges it until the user arrives.
  const [chromeBox, setChromeBox] = useState<{
    width: number;
    height: number;
  } | null>(null);
  const [rowBox, setRowBox] = useState<{
    x: number;
    y: number;
    width: number;
    height: number;
  } | null>(null);
  const [navBox, setNavBox] = useState<{
    x: number;
    y: number;
    width: number;
    height: number;
  } | null>(null);
  const [gearBox, setGearBox] = useState<{
    x: number;
    y: number;
    width: number;
    height: number;
  } | null>(null);
  const guideTravel = useRef(new Animated.Value(0)).current;
  const guideNudge = useRef(new Animated.Value(0)).current;
  const guideRect = useMemo(() => {
    if (guideTarget === null || rowBox === null) {
      return null;
    }
    if (guideTarget === 'Settings') {
      if (gearBox === null) {
        return null;
      }
      return {
        x: rowBox.x + gearBox.x,
        y: rowBox.y + gearBox.y,
        width: gearBox.width,
        height: gearBox.height,
      };
    }
    const frame = frames[guideTarget];
    if (frame === undefined || navBox === null) {
      return null;
    }
    return {
      x: rowBox.x + navBox.x + frame.x,
      y: rowBox.y + navBox.y,
      width: frame.width,
      height: navBox.height,
    };
  }, [frames, gearBox, guideTarget, navBox, rowBox]);
  const guidePoint = useMemo(() => {
    if (guideRect === null) {
      return null;
    }
    return {
      x: guideRect.x + guideRect.width / 2,
      y: guideRect.y + guideRect.height / 2,
    };
  }, [guideRect]);
  useEffect(() => {
    if (guideTarget === null || guidePoint === null) {
      return;
    }
    guideTravel.setValue(reduceMotion ? 1 : 0);
    guideNudge.setValue(0);
    if (reduceMotion) {
      return;
    }
    const travel = Animated.timing(guideTravel, {
      duration: desktopMotion.slowMs,
      easing: desktopEaseSmoothOut(),
      toValue: 1,
      useNativeDriver: false,
    });
    const nudge = Animated.loop(
      Animated.sequence([
        Animated.timing(guideNudge, {
          duration: 300,
          easing: Easing.inOut(Easing.quad),
          toValue: 1,
          useNativeDriver: false,
        }),
        Animated.timing(guideNudge, {
          duration: 300,
          easing: Easing.inOut(Easing.quad),
          toValue: 0,
          useNativeDriver: false,
        }),
      ]),
    );
    travel.start(() => nudge.start());
    return () => {
      travel.stop();
      nudge.stop();
    };
  }, [guideNudge, guidePoint, guideTarget, guideTravel, reduceMotion]);
  const guideFrom =
    chromeBox === null
      ? {x: 0, y: 0}
      : {x: chromeBox.width / 2, y: chromeBox.height - 10};

  return (
    <View
      accessibilityLabel="Omi desktop chrome"
      onLayout={event => {
        const {width, height} = event.nativeEvent.layout;
        setChromeBox(current =>
          current !== null &&
          current.width === width &&
          current.height === height
            ? current
            : {width, height},
        );
      }}
      style={styles.chrome}>
      <View
        onLayout={event => {
          const {x, y, width, height} = event.nativeEvent.layout;
          setRowBox({height, width, x, y});
        }}
        style={styles.row}>
        <View
          accessibilityLabel="Window controls"
          pointerEvents="none"
          style={styles.windowControls}
        />
        <View
          onLayout={event => {
            const {x, y, width, height} = event.nativeEvent.layout;
            setNavBox({height, width, x, y});
          }}
          style={styles.nav}>
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
            const iconName = navIcons[label];
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
                    <MaterialIcon
                      color={token.color.ink}
                      name={iconName}
                      size={14}
                    />
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
        {onToggleCapture !== null && captureAvailable ? (
          <ShippingPressable
            accessibilityLabel={
              captureActive ? 'Stop screen capture' : 'Start screen capture'
            }
            accessibilityRole="button"
            accessibilityState={{
              busy: captureBusy,
              selected: captureActive,
            }}
            active={captureActive}
            disabled={captureBusy}
            onPress={onToggleCapture}
            style={[
              styles.settingsButton,
              captureActive && styles.settingsButtonActive,
            ]}>
            <MaterialIcon
              color={captureActive ? token.color.red : token.color.ink}
              name="monitor"
              size={17}
            />
          </ShippingPressable>
        ) : null}
        <ShippingPressable
          accessibilityLabel="Settings"
          accessibilityRole="button"
          accessibilityState={{selected: route === 'Settings'}}
          active={route === 'Settings'}
          onLayout={event => {
            const {x, y, width, height} = event.nativeEvent.layout;
            setGearBox({height, width, x, y});
          }}
          onPress={() => onNavigate('Settings')}
          style={[
            styles.settingsButton,
            route === 'Settings' && styles.settingsButtonActive,
          ]}>
          <MaterialIcon name="settings" color={token.color.ink} size={17} />
        </ShippingPressable>
      </View>
      <View style={styles.omnibar}>
        <View style={styles.modes}>
          <Animated.View
            pointerEvents="none"
            style={{
              position: 'absolute',
              top: 4,
              bottom: 4,
              left: 0,
              borderRadius: 10,
              backgroundColor: token.color.glassSelected,
              transform: [{translateX: modePillX}],
              width: modePillW,
              opacity: modePillOpacity,
            }}
          />
          {(['Ask', 'Search'] as const).map(value => {
            const iconName = value === 'Ask' ? 'chat_bubble' : 'search';
            return (
              <FocusPressable
                key={value}
                accessibilityRole="button"
                accessibilityLabel={`Use ${value} mode`}
                accessibilityState={{selected: mode === value}}
                onLayout={event => {
                  const {x, width} = event.nativeEvent.layout;
                  setModeFrames(current => ({
                    ...current,
                    [value]: {x, width},
                  }));
                }}
                onPress={() => onModeChange?.(value)}
                style={styles.modeButton}>
                <MaterialIcon
                  name={iconName}
                  size={15}
                  color={
                    mode === value ? token.color.ink : token.color.inkMuted
                  }
                />
                <Text
                  style={[
                    styles.modeText,
                    mode === value && styles.navTextActive,
                  ]}>
                  {value}
                </Text>
              </FocusPressable>
            );
          })}
        </View>
        <TextInput
          accessibilityLabel={mode === 'Ask' ? 'Ask Omi' : 'Search Recall'}
          blurOnSubmit={false}
          onChangeText={onDraftChange}
          onSubmitEditing={() => {
            if (mode !== 'Ask' || (!chatBusy && draft.trim())) {
              onSend();
            }
          }}
          placeholder={
            mode === 'Search' ? desktopSearchPlaceholder : 'Ask about your day…'
          }
          placeholderTextColor={token.color.inkMuted}
          ref={omnibarRef}
          style={styles.omnibarInput}
          value={draft}
        />
        {liveControl ? (
          <View style={styles.liveSlot}>{liveControl}</View>
        ) : null}
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
          style={({pressed}) => [
            styles.send,
            mode === 'Ask' &&
              !canStop &&
              (chatBusy || !draft.trim()) &&
              styles.sendDisabled,
            pressed && styles.pressed,
          ]}>
          {canStop ? (
            <MaterialIcon name="stop" size={14} color={token.color.dark} />
          ) : mode === 'Ask' ? (
            <MaterialIcon
              name="arrow_upward"
              size={18}
              color={token.color.dark}
            />
          ) : (
            <MaterialIcon name="search" size={17} color={token.color.dark} />
          )}
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
      {guideTarget !== null && guideRect !== null ? (
        <Animated.View
          accessibilityLabel="Explore guide highlight"
          pointerEvents="none"
          style={[
            styles.guideHighlight,
            {
              left: guideRect.x - 7,
              top: guideRect.y - 6,
              width: guideRect.width + 14,
              height: guideRect.height + 12,
              opacity: guideTravel.interpolate({
                inputRange: [0, 1],
                outputRange: [0, 1],
              }),
              transform: [
                {
                  scale: guideNudge.interpolate({
                    inputRange: [0, 1],
                    outputRange: [1, 1.05],
                  }),
                },
              ],
            },
          ]}>
          <View pointerEvents="none" style={styles.guideHighlightRing} />
        </Animated.View>
      ) : null}
      {guideTarget !== null && guidePoint !== null ? (
        <Animated.View
          accessibilityLabel="Explore guide pointer"
          pointerEvents="none"
          style={[
            styles.guideCursor,
            {
              left: guideTravel.interpolate({
                inputRange: [0, 1],
                outputRange: [guideFrom.x, guidePoint.x - 2],
              }),
              top: guideTravel.interpolate({
                inputRange: [0, 1],
                outputRange: [guideFrom.y, guidePoint.y - 2],
              }),
              transform: [
                {
                  translateY: guideNudge.interpolate({
                    inputRange: [0, 1],
                    outputRange: [0, 3],
                  }),
                },
              ],
            },
          ]}>
          <MaterialIcon
            name="arrow_selector_tool"
            size={22}
            color={token.color.ink}
            fill={token.color.glass}
          />
        </Animated.View>
      ) : null}
    </View>
  );
}

const createStyles = (token: DesktopTokens) =>
  StyleSheet.create({
    modes: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 2,
      // Anchors the sliding mode pill behind the buttons.
      position: 'relative' as const,
    },
    liveSlot: {alignItems: 'center', flexShrink: 0},
    modeButton: {
      height: 32,
      flexDirection: 'row',
      gap: 6,
      paddingHorizontal: 10,
      alignItems: 'center',
      justifyContent: 'center',
      borderRadius: 12,
    },
    modeText: {fontSize: 12, color: token.color.inkMuted},
    chrome: {
      gap: 14,
      marginBottom: 4,
    },
    guideCursor: {
      position: 'absolute',
      zIndex: 4,
    },
    // RN macOS view shadows are unusable here: RCTView's didUpdateShadow runs
    // on any shadow prop change and calls colorWithCGColor: with a NULL color
    // whenever shadowColor did not land first, which throws inside the UI
    // batch and kills every later view update (settings stops opening). The
    // glow is a translucent border ring instead.
    guideHighlight: {
      position: 'absolute',
      zIndex: 3,
      borderRadius: 10,
      borderWidth: 2,
      borderColor: token.color.ink,
    },
    guideHighlightRing: {
      ...StyleSheet.absoluteFillObject,
      borderRadius: 12,
      borderWidth: 4,
      borderColor: token.color.ink,
      opacity: 0.22,
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
      paddingHorizontal: 10,
      zIndex: 1,
    },
    navItemFollow: {
      marginRight: 4,
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
      alignSelf: 'center',
      width: '100%',
      maxWidth: 992,
      backgroundColor: token.color.glassStrong,
      borderWidth: 1,
      borderColor: token.color.line,
      borderRadius: 14,
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
      borderRadius: 16,
      backgroundColor: token.color.ink,
    },
    sendDisabled: {opacity: 0.3},
    sendText: {
      color: token.color.ink,
      fontFamily: token.font,
      fontSize: token.type.caption,
      fontWeight: '600',
    },
    settingsButton: {
      alignItems: 'center',
      backgroundColor: 'rgba(0,0,0,0)',
      borderRadius: 17,
      flexShrink: 0,
      height: 34,
      justifyContent: 'center',
      overflow: 'hidden',
      width: 34,
    },
    settingsButtonActive: {
      backgroundColor: token.color.glassSelected,
      borderColor: token.color.line,
      borderWidth: 1,
    },
    pressed: {opacity: 0.78},
  });
