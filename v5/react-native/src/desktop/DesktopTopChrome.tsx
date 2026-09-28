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
  desktopActivityFilters,
  desktopFilterLabel,
  desktopFilterRowHeight,
  desktopMotion,
  desktopOmnibarHeight,
  desktopSearchPlaceholder,
  desktopTimelineGroupings,
  desktopTrafficLightButton,
  desktopTrafficLightRowWidth,
  type ActivityFilterId,
  type TimelineGrouping,
} from './desktopChrome';
import {desktopEaseSmoothOut} from './desktopMotion';
import {ShippingPressable} from './ShippingPressable';
import {DesktopTrafficLights} from './DesktopTrafficLights';
import {
  type DesktopTokens,
  useDesktopTheme,
  useDesktopStyleSheets,
} from './DesktopTheme';

// v5.1 routes: Home is the Activity page, Rewind is the capture-detail viewer
// reached from timeline entries or Search. Chat is a page destination;
// Conversations and Tasks remain Activity filters.
export type DesktopRoute = 'Home' | 'Rewind' | 'Settings' | 'Chat';

const filterIcons: Record<ActivityFilterId, MaterialIconName> = {
  all: 'view_timeline',
  conversations: 'chat_bubble',
  recall: 'history',
  tasks: 'checklist',
};

export type OmnibarMode = 'Ask' | 'Search';

type Props = {
  hostMode?: boolean;
  chatBusy?: boolean;
  chatActive?: boolean;
  mode?: OmnibarMode;
  onModeChange?: (mode: OmnibarMode) => void;
  liveControl?: React.ReactNode;
  activeGenerationId: string | null;
  route: DesktopRoute;
  onNavigate: (route: DesktopRoute) => void;
  // The Activity filters that replace the old page switcher. Selecting one
  // filters the timeline on Home.
  filter: ActivityFilterId;
  onFilterChange: (filter: ActivityFilterId) => void;
  // Timeline grouping shown beside the filters: by date, type, or topic.
  groupBy: TimelineGrouping;
  onGroupByChange: (grouping: TimelineGrouping) => void;
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
  // chrome (a filter chip or the settings gear) and nudges it until dismissed.
  guideTarget?: ActivityFilterId | 'Settings' | null;
};

export function DesktopChrome({
  hostMode = false,
  chatBusy = false,
  chatActive = false,
  mode = 'Ask',
  onModeChange,
  liveControl,
  activeGenerationId,
  chatNotice,
  draft,
  omnibarRef,
  onDraftChange,
  onSend,
  onStop,
  onNavigate,
  route,
  filter,
  onFilterChange,
  groupBy,
  onGroupByChange,
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

  // Sliding selection pill for the omnibar mode switcher.
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
  const [filtersBox, setFiltersBox] = useState<{
    x: number;
    y: number;
    width: number;
    height: number;
  } | null>(null);
  const [chipFrames, setChipFrames] = useState<
    Partial<Record<ActivityFilterId, {x: number; width: number}>>
  >({});
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
    if (filtersBox === null) {
      return null;
    }
    const frame = chipFrames[guideTarget];
    if (frame === undefined) {
      return null;
    }
    return {
      x: rowBox.x + filtersBox.x + frame.x,
      y: rowBox.y + filtersBox.y,
      width: frame.width,
      height: filtersBox.height,
    };
  }, [chipFrames, filtersBox, gearBox, guideTarget, rowBox]);
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
          style={styles.windowControls}>
          {!hostMode && <DesktopTrafficLights />}
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
                borderRadius: 16,
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
                      mode === value && styles.modeTextActive,
                    ]}>
                    {value}
                  </Text>
                </FocusPressable>
              );
            })}
          </View>
          {chatActive ? (
            <Text style={styles.chatDestination} accessibilityRole="header">
              Chat
            </Text>
          ) : (
            <TextInput
              accessibilityLabel={mode === 'Ask' ? 'Ask Omi' : 'Search Recall'}
              blurOnSubmit={false}
              onChangeText={onDraftChange}
              onKeyPress={event => {
                if (event.nativeEvent.key === 'Escape') {
                  onNavigate('Chat');
                }
              }}
              onSubmitEditing={() => {
                if (mode !== 'Ask' || (!chatBusy && draft.trim())) {
                  onSend();
                }
              }}
              placeholder={
                mode === 'Search'
                  ? desktopSearchPlaceholder
                  : 'Ask about your day…'
              }
              placeholderTextColor={token.color.inkMuted}
              ref={omnibarRef}
              style={styles.omnibarInput}
              value={draft}
            />
          )}
          {liveControl && !chatActive ? (
            <View style={styles.liveSlot}>{liveControl}</View>
          ) : null}
          {!chatActive && (
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
              disabled={
                mode === 'Ask' && !canStop && (chatBusy || !draft.trim())
              }
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
                <MaterialIcon
                  name="search"
                  size={17}
                  color={token.color.dark}
                />
              )}
            </FocusPressable>
          )}
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
          // The gear toggles: it opens Settings and also walks back Home.
          onPress={() => onNavigate(route === 'Settings' ? 'Home' : 'Settings')}
          style={[
            styles.settingsButton,
            route === 'Settings' && styles.settingsButtonActive,
          ]}>
          <MaterialIcon name="settings" color={token.color.ink} size={17} />
        </ShippingPressable>
      </View>
      {chatNotice === null ? null : (
        <Text
          accessibilityLabel="Chat transport notice"
          numberOfLines={1}
          style={styles.notice}>
          {chatNotice}
        </Text>
      )}
      <View
        accessibilityLabel="Activity filters"
        accessibilityRole="tablist"
        onLayout={event => {
          const {x, y, width, height} = event.nativeEvent.layout;
          setFiltersBox({height, width, x, y});
        }}
        style={styles.filterRow}>
        <FocusPressable
          accessibilityRole="button"
          accessibilityLabel="Open Chat"
          accessibilityState={{selected: chatActive}}
          onPress={() => onNavigate(chatActive ? 'Home' : 'Chat')}
          style={[styles.modeButton, chatActive && styles.chatSelected]}>
          <MaterialIcon name="chat_bubble" size={15} color={token.color.ink} />
          <Text style={styles.modeText}>Chat</Text>
        </FocusPressable>
        {desktopActivityFilters.map(id => {
          // Filters belong to the Activity page: away from it (Settings,
          // Recall search) no chip claims to be the current view.
          const selected = id === filter && route === 'Home';
          return (
            <FocusPressable
              key={id}
              accessibilityLabel={`Filter ${desktopFilterLabel(id)}`}
              accessibilityRole="button"
              accessibilityState={{selected}}
              onLayout={event => {
                const {x, width} = event.nativeEvent.layout;
                setChipFrames(current => {
                  const next = {x, width};
                  if (
                    current[id] !== undefined &&
                    Math.abs(current[id]!.x - next.x) < 0.5 &&
                    Math.abs(current[id]!.width - next.width) < 0.5
                  ) {
                    return current;
                  }
                  return {...current, [id]: next};
                });
              }}
              onPress={() => onFilterChange(id)}
              style={({pressed}) => [
                styles.filterHit,
                selected && styles.filterHitSelected,
                pressed && styles.pressed,
              ]}>
              <MaterialIcon
                name={filterIcons[id]}
                size={14}
                color={selected ? token.color.ink : token.color.inkMuted}
              />
              <Text
                style={[
                  styles.filterText,
                  selected && styles.filterTextActive,
                ]}>
                {desktopFilterLabel(id)}
              </Text>
            </FocusPressable>
          );
        })}
        <View style={styles.groupBySlot} />
        {chatActive ? null : (
          <View
            accessibilityLabel="Timeline grouping"
            accessibilityRole="tablist"
            style={styles.groupBy}>
            {desktopTimelineGroupings.map(value => {
              const selected = value === groupBy;
              return (
                <FocusPressable
                  key={value}
                  accessibilityLabel={`Group by ${value}`}
                  accessibilityRole="button"
                  accessibilityState={{selected}}
                  onPress={() => onGroupByChange(value)}
                  style={({pressed}) => [
                    styles.groupHit,
                    selected && styles.groupHitSelected,
                    pressed && styles.pressed,
                  ]}>
                  <Text
                    style={[
                      styles.groupText,
                      selected && styles.groupTextSelected,
                    ]}>
                    {value === 'date'
                      ? 'Date'
                      : value === 'type'
                      ? 'Type'
                      : 'Topic'}
                  </Text>
                </FocusPressable>
              );
            })}
          </View>
        )}
      </View>
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
      borderRadius: 16,
    },
    modeText: {fontSize: 12, color: token.color.inkMuted},
    modeTextActive: {color: token.color.ink},
    chatSelected: {backgroundColor: token.color.glassSelected},
    chatDestination: {
      color: token.color.ink,
      flex: 1,
      fontFamily: token.font,
      fontSize: token.type.search,
      fontWeight: '600',
    },
    chrome: {
      gap: 10,
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
      gap: 10,
      height: desktopOmnibarHeight,
    },
    windowControls: {
      alignSelf: 'center',
      height: desktopTrafficLightButton,
      width: desktopTrafficLightRowWidth,
    },
    omnibar: {
      alignItems: 'center',
      flex: 1,
      backgroundColor: token.color.glassStrong,
      borderWidth: 1,
      borderColor: token.color.line,
      // The composer is a capsule (design language).
      borderRadius: desktopOmnibarHeight / 2,
      flexDirection: 'row',
      gap: 8,
      height: desktopOmnibarHeight,
      maxWidth: 992,
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
    filterRow: {
      alignItems: 'center',
      flexDirection: 'row',
      gap: 6,
      height: desktopFilterRowHeight,
      maxWidth: 992,
      width: '100%',
      alignSelf: 'center',
    },
    filterHit: {
      alignItems: 'center',
      borderColor: 'transparent',
      borderRadius: 15,
      borderWidth: 1,
      flexDirection: 'row',
      gap: 7,
      height: 30,
      justifyContent: 'center',
      paddingHorizontal: 12,
    },
    filterHitSelected: {
      backgroundColor: token.color.glassSelected,
      borderColor: token.color.line,
    },
    filterText: {
      color: token.color.inkMuted,
      fontFamily: token.font,
      fontSize: token.type.nav,
      fontWeight: '500',
    },
    filterTextActive: {
      color: token.color.ink,
    },
    groupBySlot: {flex: 1},
    groupBy: {
      alignItems: 'center',
      borderRadius: 15,
      borderColor: token.color.line,
      borderWidth: 1,
      flexDirection: 'row',
      gap: 2,
      padding: 2,
    },
    groupHit: {
      alignItems: 'center',
      borderRadius: 12,
      height: 24,
      justifyContent: 'center',
      paddingHorizontal: 10,
    },
    groupHitSelected: {
      backgroundColor: token.color.glassSelected,
    },
    groupText: {
      color: token.color.inkMuted,
      fontFamily: token.font,
      fontSize: 11,
      fontWeight: '600',
    },
    groupTextSelected: {color: token.color.ink},
    pressed: {opacity: 0.78},
  });
