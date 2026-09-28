import React, {useEffect, useRef, useState} from 'react';
import {Animated, Easing, Text, View} from 'react-native';
import {MaterialIcon, type MaterialIconName} from './MaterialIcon';

import type {Route} from '../app/routes';
import {FocusPressable} from './Pressable';
import {styles} from './styles';

const navigation: Array<{label: string; icon: MaterialIconName}> = [
  {label: 'Home', icon: 'home'},
  {label: 'Conversations', icon: 'view_timeline'},
  {label: 'Memories', icon: 'neurology'},
  {label: 'Tasks', icon: 'checklist'},
  {label: 'Connectors', icon: 'extension'},
  {label: 'Settings', icon: 'settings'},
];

function NavItem({
  label,
  icon,
  compact,
  active,
  expanded,
  onPress,
}: {
  label: string;
  icon: MaterialIconName;
  compact: boolean;
  active: boolean;
  expanded: boolean;
  onPress: () => void;
}) {
  return (
    <FocusPressable
      accessibilityRole="tab"
      accessibilityLabel={label}
      accessibilityState={{selected: active}}
      onPress={onPress}
      style={({pressed}) => [
        styles.navItem,
        compact && styles.navItemCompact,
        active && styles.navItemActive,
        pressed && styles.pressed,
      ]}>
      <View style={styles.navIcon}>
        <MaterialIcon
          accessible={false}
          color={active ? '#141414' : '#888888'}
          name={icon}
          size={20}
        />
      </View>
      {(compact || expanded) && (
        <Text
          numberOfLines={1}
          style={[styles.navText, active && styles.navTextActive]}>
          {label}
        </Text>
      )}
    </FocusPressable>
  );
}

export function AppNav({
  compact,
  reduceMotion,
  route,
  onNavigate,
}: {
  compact: boolean;
  reduceMotion: boolean;
  route: Route;
  onNavigate: (destination: Route) => void;
}) {
  const mobileNavOpacity = useRef(new Animated.Value(0)).current;
  const mobileNavTranslateY = useRef(new Animated.Value(100)).current;
  const railWidth = useRef(new Animated.Value(72)).current;
  const [railExpanded, setRailExpanded] = useState(false);
  useEffect(() => {
    if (!compact) {
      mobileNavOpacity.setValue(1);
      mobileNavTranslateY.setValue(0);
      return;
    }
    mobileNavOpacity.setValue(0);
    mobileNavTranslateY.setValue(reduceMotion ? 0 : 100);
    Animated.parallel([
      Animated.timing(mobileNavOpacity, {
        duration: reduceMotion ? 1 : 200,
        easing: Easing.out(Easing.cubic),
        toValue: 1,
        useNativeDriver: true,
      }),
      Animated.timing(mobileNavTranslateY, {
        duration: reduceMotion ? 1 : 200,
        easing: Easing.out(Easing.cubic),
        toValue: 0,
        useNativeDriver: true,
      }),
    ]).start();
  }, [compact, mobileNavOpacity, mobileNavTranslateY, reduceMotion]);

  useEffect(() => {
    const value = railExpanded ? 280 : 72;
    if (reduceMotion) {
      railWidth.setValue(value);
      return;
    }
    Animated.timing(railWidth, {
      duration: 200,
      easing: Easing.bezier(0.42, 0, 0.58, 1),
      toValue: value,
      useNativeDriver: false,
    }).start();
  }, [railExpanded, railWidth, reduceMotion]);

  return (
    <Animated.View
      accessibilityRole="tablist"
      style={[
        styles.navigation,
        compact ? styles.bottomNav : styles.rail,
        !compact && {width: railWidth},
        compact && {
          opacity: mobileNavOpacity,
          transform: [{translateY: mobileNavTranslateY}],
        },
      ]}>
      {!compact && (
        <View
          style={[
            styles.railHeader,
            railExpanded && styles.railHeaderExpanded,
          ]}>
          <Text style={styles.wordmark}>omi</Text>
          <FocusPressable
            accessibilityLabel={
              railExpanded ? 'Collapse sidebar' : 'Expand sidebar'
            }
            accessibilityRole="button"
            onPress={() => setRailExpanded(current => !current)}
            style={({pressed}) => [
              styles.railToggle,
              pressed && styles.pressed,
            ]}>
            {railExpanded ? (
              <MaterialIcon name="left_panel_close" color="#888888" size={20} />
            ) : (
              <MaterialIcon name="left_panel_open" color="#888888" size={20} />
            )}
          </FocusPressable>
        </View>
      )}
      <View style={[styles.navItems, compact && styles.navItemsCompact]}>
        {navigation.map(item => (
          <NavItem
            active={route === item.label}
            compact={compact}
            icon={item.icon}
            key={item.label}
            expanded={railExpanded}
            label={item.label}
            onPress={() => onNavigate(item.label as Route)}
          />
        ))}
      </View>
    </Animated.View>
  );
}
