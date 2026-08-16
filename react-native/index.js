/**
 * @format
 */

import React from 'react';
import {AppRegistry} from 'react-native';
import {SafeAreaProvider} from 'react-native-safe-area-context';
import App from './App';
import {name as appName} from './app.json';

const Root = props =>
  React.createElement(SafeAreaProvider, null, React.createElement(App, props));

AppRegistry.registerComponent(appName, () => Root);
