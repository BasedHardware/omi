import React from 'react';
import {StyleSheet} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {useOmiTheme} from '../design/OmiTheme';

/** Safe-area page on the theme canvas, for mobile screens outside the shell. */
export function MobileCanvas({children}: {children?: React.ReactNode}) {
  const theme = useOmiTheme();
  return (
    <SafeAreaView style={[styles.fill, {backgroundColor: theme.color.canvas}]}>
      {children}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({fill: {flex: 1}});
