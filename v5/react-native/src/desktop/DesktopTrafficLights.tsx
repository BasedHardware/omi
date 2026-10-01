import React, {useCallback, useState} from 'react';
import {NativeModules, StyleSheet, View} from 'react-native';
import {FocusPressable} from '../ui/Pressable';
import {
  desktopTrafficLightButton,
  desktopTrafficLightClusterWidth,
  desktopTrafficLightSpacing,
} from './desktopChrome';

// The native traffic lights are hidden (AppDelegate hides the standard
// buttons): hover and hit areas live in AppKit's own titlebar layout and kept
// desyncing from the chrome geometry. These virtual dots render inside the
// chrome row's window-controls spacer at the exact geometry desktopChrome.ts
// always reserved, and close/minimize/zoom go through the native
// performWindowCommand so the actions run the same AppKit paths as the real
// buttons (performClose: honors windowShouldClose and app teardown).

export type DesktopWindowCommand = 'close' | 'minimize' | 'zoom';

type DesktopCommandsNative = {
  performWindowCommand?(command: DesktopWindowCommand): Promise<boolean>;
};

function performWindowCommand(command: DesktopWindowCommand) {
  const commands = NativeModules.OmiDesktopCommands as
    | DesktopCommandsNative
    | undefined;
  // Outside macOS (tests, web) the module is absent and the dots are inert.
  commands?.performWindowCommand?.(command).catch(() => undefined);
}

const DOT_COLORS: Record<DesktopWindowCommand, string> = {
  close: '#ff5f57',
  minimize: '#febc2e',
  zoom: '#28c840',
};

const DOT_LABELS: Record<DesktopWindowCommand, string> = {
  close: 'Close window',
  minimize: 'Minimize window',
  zoom: 'Zoom window',
};

// macOS hover glyphs: hairline dark ink, shown for the whole cluster at once.
function Glyph({kind}: {kind: DesktopWindowCommand}) {
  if (kind === 'close') {
    return (
      <View style={styles.glyphBox}>
        <View style={[styles.glyphBar, styles.glyphDiagonal]} />
        <View style={[styles.glyphBar, styles.glyphDiagonal, styles.flip]} />
      </View>
    );
  }
  if (kind === 'minimize') {
    return (
      <View style={styles.glyphBox}>
        <View style={styles.glyphBar} />
      </View>
    );
  }
  return (
    <View style={styles.glyphBox}>
      <View style={styles.glyphBar} />
      <View style={[styles.glyphBar, styles.glyphVertical]} />
    </View>
  );
}

function TrafficDot({
  kind,
  showGlyph,
}: {
  kind: DesktopWindowCommand;
  showGlyph: boolean;
}) {
  const onPress = useCallback(() => performWindowCommand(kind), [kind]);
  return (
    <FocusPressable
      accessibilityLabel={DOT_LABELS[kind]}
      accessibilityRole="button"
      hitSlop={2}
      onPress={onPress}
      style={state => [
        styles.dot,
        {backgroundColor: DOT_COLORS[kind]},
        state.pressed && styles.dotPressed,
      ]}>
      {showGlyph ? <Glyph kind={kind} /> : null}
    </FocusPressable>
  );
}

export function DesktopTrafficLights() {
  const [hovered, setHovered] = useState(false);
  return (
    <View
      onPointerEnter={() => setHovered(true)}
      onPointerLeave={() => setHovered(false)}
      style={styles.cluster}>
      <TrafficDot kind="close" showGlyph={hovered} />
      <TrafficDot kind="minimize" showGlyph={hovered} />
      <TrafficDot kind="zoom" showGlyph={hovered} />
    </View>
  );
}

const styles = StyleSheet.create({
  cluster: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: desktopTrafficLightSpacing,
    height: desktopTrafficLightButton,
    width: desktopTrafficLightClusterWidth,
  },
  dot: {
    alignItems: 'center',
    borderRadius: desktopTrafficLightButton / 2,
    height: desktopTrafficLightButton,
    justifyContent: 'center',
    width: desktopTrafficLightButton,
  },
  dotPressed: {
    opacity: 0.72,
  },
  glyphBox: {
    alignItems: 'center',
    height: desktopTrafficLightButton,
    justifyContent: 'center',
    width: desktopTrafficLightButton,
  },
  glyphBar: {
    backgroundColor: 'rgba(0, 0, 0, 0.55)',
    borderRadius: 0.75,
    height: 1.5,
    width: 8,
  },
  glyphDiagonal: {
    position: 'absolute',
    transform: [{rotate: '45deg'}],
  },
  flip: {
    transform: [{rotate: '-45deg'}],
  },
  glyphVertical: {
    position: 'absolute',
    transform: [{rotate: '90deg'}],
  },
});
