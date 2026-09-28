import React from 'react';
import {Platform, View, type ViewProps} from 'react-native';
import {requireNativeComponent} from '../native-component';

export type GlassPanelProps = ViewProps & {glassCornerRadius?: number};

export const GlassPanel =
  Platform.OS === 'macos'
    ? requireNativeComponent<GlassPanelProps>('OmiGlassPanel')
    : (View as unknown as React.ComponentType<GlassPanelProps>);
