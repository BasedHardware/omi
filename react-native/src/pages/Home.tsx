import React from 'react';
import {StyleSheet, View} from 'react-native';
import {tokens} from '../ui/tokens';

export function HomeSurface({
  children,
  footer,
}: {
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <View
      accessibilityLabel="Home desktop timeline surface"
      style={styles.surface}>
      <View accessibilityLabel="Home timeline lane" style={styles.lane}>
        {children}
        {footer}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  surface: {
    alignSelf: 'stretch',
    backgroundColor: tokens.color.transparent,
    borderRadius: tokens.radius.none,
    flex: 1,
    position: 'relative',
  },
  lane: {
    flex: 1,
    gap: tokens.space.sm,
    paddingBottom: 18,
    paddingHorizontal: tokens.space.lg,
    paddingTop: tokens.space.md,
    width: '100%',
  },
});
