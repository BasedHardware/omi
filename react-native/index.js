/**
 * @format
 */

/**
 * macOS Release/JS runtime may lack a Performance API; RN startup timing
 * and some deps call performance.now during AppRegistry.runApplication.
 */
(() => {
  const g = typeof globalThis !== 'undefined' ? globalThis : global;
  const origin = Date.now();
  let lastElapsed = 0;
  const now = () => {
    lastElapsed = Math.max(lastElapsed, Date.now() - origin);
    return lastElapsed;
  };
  if (!g.performance) {
    g.performance = {now};
  } else if (typeof g.performance.now !== 'function') {
    g.performance.now = now;
  }
})();

import React from 'react';
import {AppRegistry} from 'react-native';
import {SafeAreaProvider} from 'react-native-safe-area-context';
import App from './App';
import {name as appName} from './app.json';

const Root = props =>
  React.createElement(SafeAreaProvider, null, React.createElement(App, props));

AppRegistry.registerComponent(appName, () => Root);
