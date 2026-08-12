/**
 * @format
 */

import React from 'react';
import ReactTestRenderer from 'react-test-renderer';

jest.mock('react-native', () => {
  const ReactRuntime = require('react');
  const component = (name: string) => ({children, ...props}: {children?: React.ReactNode}) => ReactRuntime.createElement(name, props, children);
  const Text = component('Text');
  const View = component('View');
  const FlatList = ({ListEmptyComponent, ListFooterComponent, ListHeaderComponent}: {ListEmptyComponent: React.ReactNode; ListFooterComponent: React.ReactNode; ListHeaderComponent: React.ReactNode}) => (
    <View>
      {ListHeaderComponent}
      {ListEmptyComponent}
      {ListFooterComponent}
    </View>
  );

  return {
    ActivityIndicator: component('ActivityIndicator'),
    FlatList,
    NativeModules: {},
    Pressable: component('Pressable'),
    SafeAreaView: component('SafeAreaView'),
    StyleSheet: {create: <T,>(styles: T) => styles},
    Text,
    useWindowDimensions: () => ({fontScale: 1, height: 900, scale: 1, width: 1200}),
    View,
  };
});

jest.mock('../src/omiNative', () => ({
  isNativeModuleInstalled: true,
  omiNative: {
    connectDevice: jest.fn(),
    disconnectDevice: jest.fn(),
    getSnapshot: jest.fn(),
    requestPermissions: jest.fn(),
    startScan: jest.fn(),
    stopScan: jest.fn(),
  },
}));

import App from '../App';
import {omiNative} from '../src/omiNative';

const mockNativeModule = omiNative! as unknown as jest.Mocked<Pick<NonNullable<typeof omiNative>, 'connectDevice' | 'disconnectDevice' | 'getSnapshot' | 'requestPermissions' | 'startScan' | 'stopScan'>>;

beforeEach(() => {
  jest.clearAllMocks();
});

test('renders the current native platform state', async () => {
  mockNativeModule.getSnapshot.mockResolvedValue({
    audioRoute: 'phone-mic',
    bluetooth: 'poweredOn',
    capture: 'idle',
    captureMode: 'stream',
    devices: [],
    lastEvent: 'Ready to find Omi devices',
    microphone: 'granted',
    notifications: 'granted',
    background: 'active',
  });
  let renderer: ReactTestRenderer.ReactTestRenderer;

  await ReactTestRenderer.act(async () => {
    renderer = ReactTestRenderer.create(<App />);
    await Promise.resolve();
  });

  expect(JSON.stringify(renderer!.toJSON())).toContain('Ready to find Omi devices');
  expect(JSON.stringify(renderer!.toJSON())).toContain('No moments yet. Connect a real Omi to begin.');
});

test('waits for discovery before refreshing the native device list', async () => {
  jest.useFakeTimers();
  mockNativeModule.getSnapshot.mockResolvedValue({
    audioRoute: 'phone-mic',
    bluetooth: 'poweredOn',
    capture: 'idle',
    captureMode: 'stream',
    devices: [],
    lastEvent: 'Ready to find Omi devices',
    microphone: 'granted',
    notifications: 'granted',
    background: 'active',
  });
  mockNativeModule.startScan.mockResolvedValue([]);
  mockNativeModule.stopScan.mockResolvedValue();
  let renderer: ReactTestRenderer.ReactTestRenderer;

  await ReactTestRenderer.act(async () => {
    renderer = ReactTestRenderer.create(<App />);
    await Promise.resolve();
  });

  const findMyOmi = renderer!.root.findAll((node) => node.props.accessibilityRole === 'button').find((node) => node.props.children.props.children === 'Find my Omi')!;
  await ReactTestRenderer.act(async () => {
    findMyOmi.props.onPress();
    await Promise.resolve();
  });
  expect(mockNativeModule.startScan).toHaveBeenCalledWith(5, []);
  expect(mockNativeModule.stopScan).not.toHaveBeenCalled();

  await ReactTestRenderer.act(async () => {
    jest.advanceTimersByTime(5_000);
    await Promise.resolve();
  });
  expect(mockNativeModule.stopScan).toHaveBeenCalledTimes(1);
  expect(mockNativeModule.getSnapshot).toHaveBeenCalledTimes(2);
  jest.useRealTimers();
});
