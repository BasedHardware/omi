/**
 * @format
 */

import React from 'react';
import ReactTestRenderer from 'react-test-renderer';
import App from '../App';

test('renders correctly and settles the host-native snapshot', async () => {
  await ReactTestRenderer.act(async () => {
    ReactTestRenderer.create(<App />);
    await Promise.resolve();
  });
});
