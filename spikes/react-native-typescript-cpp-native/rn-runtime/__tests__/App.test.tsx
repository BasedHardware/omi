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
    View,
  };
});

import App from '../App';

test('renders an honest unavailable-native state', async () => {
  let renderer: ReactTestRenderer.ReactTestRenderer;

  await ReactTestRenderer.act(async () => {
    renderer = ReactTestRenderer.create(<App />);
    await Promise.resolve();
  });

  expect(JSON.stringify(renderer!.toJSON())).toContain('This platform has no Omi native adapter yet.');
});
