import React from 'react';
import {StyleSheet, View} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {GlassPanel} from './GlassPanel';
import {tokens} from './tokens';

export function PageShell({
  children,
  desktopOverlay,
  macDesktop,
  workspaceMaterial = true,
}: {
  children: React.ReactNode;
  desktopOverlay?: React.ReactNode;
  macDesktop: boolean;
  workspaceMaterial?: boolean;
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
      {workspaceMaterial ? (
        <GlassPanel
          accessibilityLabel="Desktop workspace material"
          glassCornerRadius={tokens.radius.none}
          pointerEvents="none"
          style={styles.glass}
        />
      ) : null}
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
