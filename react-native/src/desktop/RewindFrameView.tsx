import React from 'react';
import {Platform, View, type ViewProps} from 'react-native';
import {requireNativeComponent} from '../native-component';

// Rewind previews render through this native view instead of RN's <Image>:
// on this react-native-macOS, every data:/file: URI image load goes through
// RCTNetworking, whose data and file request handlers pass a nil request
// token (upstream bug), tripping the fatal "Unrecognized request token"
// dev assert and failing in release. The native view decodes the base64
// JPEG payload directly.
type NativeProps = ViewProps & {
  imageBase64?: string;
};

const NativeRewindFrame =
  Platform.OS === 'macos'
    ? requireNativeComponent<NativeProps>('OmiRewindFrame')
    : null;

export function RewindFrameView(props: NativeProps) {
  if (NativeRewindFrame === null) {
    // Non-macOS surfaces never render Rewind previews; keep a benign
    // placeholder so tests and type-checks stay simple.
    return <View style={props.style} />;
  }
  return <NativeRewindFrame {...props} />;
}
