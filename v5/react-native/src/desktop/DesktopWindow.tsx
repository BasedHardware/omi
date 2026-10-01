import React from 'react';
import {Platform, View, type ViewProps} from 'react-native';
import {requireNativeComponent} from '../native-component';

type Props = ViewProps & {presentation: 'onboarding' | 'permission-guide'};
const NativeWindow =
  Platform.OS === 'macos'
    ? requireNativeComponent<Props>('OmiDesktopWindow')
    : (View as unknown as React.ComponentType<Props>);

/** Window geometry only. The mounted React screen owns its content and lifetime. */
export function DesktopWindow({presentation}: Pick<Props, 'presentation'>) {
  return (
    <NativeWindow
      presentation={presentation}
      nativeID={`omi-window-${presentation}`}
      pointerEvents="none"
      accessible={false}
      style={{position: 'absolute', width: 0, height: 0}}
    />
  );
}
