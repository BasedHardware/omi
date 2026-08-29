import React, {useEffect, useRef, useState} from 'react';
import {Animated, Easing, Text, View} from 'react-native';
import Brain from 'lucide-react-native/icons/brain';
import GanttChartSquare from 'lucide-react-native/icons/square-chart-gantt';
import House from 'lucide-react-native/icons/house';
import ListChecks from 'lucide-react-native/icons/list-checks';
import PanelLeft from 'lucide-react-native/icons/panel-left';
import PanelLeftClose from 'lucide-react-native/icons/panel-left-close';
import type {Route} from '../app/routes';
import {FocusPressable} from './Pressable';
import {styles} from './styles';

type NavigationIcon = React.ComponentType<{
  accessible?: boolean;
  color?: string;
  size?: number;
  strokeWidth?: number;
}>;

const navigation: Array<{label: string; icon: NavigationIcon}> = [
  {label: 'Home', icon: House},
  {label: 'Conversations', icon: GanttChartSquare},
  {label: 'Memories', icon: Brain},
  {label: 'Tasks', icon: ListChecks},
  {label: 'Connectors', icon: PanelLeftClose},
  {label: 'Settings', icon: PanelLeft},
];

function NavItem({
  label,
  icon: Icon,
  compact,
  active,
  expanded,
  onPress,
}: {
  label: string;
  icon: NavigationIcon;
  compact: boolean;
  active: boolean;
  expanded: boolean;
  onPress: () => void;
}) {
  return (
    <FocusPressable
      accessibilityRole="tab"
      accessibilityState={{selected: active}}
      onPress={onPress}
      style={({pressed}) => [
        styles.navItem,
        compact && styles.navItemCompact,
        active && styles.navItemActive,
        pressed && styles.pressed,
      ]}>
      <Icon
        accessible={false}
        color={active ? '#141414' : '#888888'}
        size={20}
        strokeWidth={2}
      />
      <Text
        numberOfLines={1}
        style={[
          styles.navText,
          !compact && !expanded && styles.navTextCollapsed,
          active && styles.navTextActive,
        ]}>
        {label}
      </Text>
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
              <PanelLeftClose color="#888888" size={20} strokeWidth={2} />
            ) : (
              <PanelLeft color="#888888" size={20} strokeWidth={2} />
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
