'use strict';

// Test shim for react-native-svg (mirrors test/react-native-webrtc.js).
// MaterialIcon renders Material Symbols geometry through react-native-svg;
// under jest the native svg views do not exist, so every element stands up
// as an inert host component.
const React = require('react');

function makeHost(displayName) {
  const component = props => {
    const {children, ...rest} = props ?? {};
    return React.createElement(`RN-Svg-${displayName}`, rest, children);
  };
  component.displayName = displayName;
  return component;
}

module.exports = {
  __esModule: true,
  default: makeHost('Svg'),
  Svg: makeHost('Svg'),
  Path: makeHost('Path'),
  Defs: makeHost('Defs'),
  LinearGradient: makeHost('LinearGradient'),
  Rect: makeHost('Rect'),
  Stop: makeHost('Stop'),
};
