import React from 'react';
import {Platform, StyleSheet, View, type ViewProps} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {requireNativeComponent} from '../native-component';
import {tokens} from './tokens';

type GlassPanelProps = ViewProps & {glassCornerRadius?: number};

const GlassPanel =
  Platform.OS === 'macos'
    ? requireNativeComponent<GlassPanelProps>('OmiGlassPanel')
    : (View as unknown as React.ComponentType<GlassPanelProps>);

export function PageShell({
  children,
  desktopOverlay,
  macDesktop,
}: {
  children: React.ReactNode;
  desktopOverlay?: React.ReactNode;
  macDesktop: boolean;
}) {
  const content = (
    <SafeAreaView style={[styles.safe, macDesktop && styles.macSafe]}>
      {children}
    </SafeAreaView>
  );
  if (!macDesktop) {
    return content;
  }
  return (
    <View pointerEvents="box-none" style={styles.macRoot}>
      <GlassPanel
        accessibilityLabel="Desktop workspace material"
        glassCornerRadius={tokens.radius.none}
        pointerEvents="none"
        style={styles.glass}
      />
      {content}
      {desktopOverlay}
    </View>
  );
}

const styles = StyleSheet.create({
  safe: {backgroundColor: tokens.color.canvas, flex: 1},
  macSafe: {backgroundColor: tokens.color.transparent},
  macRoot: {flex: 1, position: 'relative'},
  glass: {
    bottom: tokens.space.none,
    left: tokens.space.none,
    position: 'absolute',
    right: tokens.space.none,
    top: tokens.space.none,
  },
});
