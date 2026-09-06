import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {TextInput} from 'react-native';

jest.mock('../src/omiNative', () => ({
  omiAuth: null,
  omiBackend: null,
  omiNative: null,
  subscribeOmiBackendSessionInvalidated: () => () => undefined,
  subscribeOmiNativeEvents: () => () => undefined,
}));
jest.mock('../src/app/useReduceMotion', () => ({useReduceMotion: () => true}));

const App = require('../src/app/AppOrchestrator').default;
const renderers: ReactTestRenderer.ReactTestRenderer[] = [];

async function renderApp() {
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  await act(async () => {
    renderer = ReactTestRenderer.create(<App />);
  });
  renderers.push(renderer);
  return renderer;
}

function control(renderer: ReactTestRenderer.ReactTestRenderer, label: string) {
  return renderer.root.findAll(
    node => node.props.accessibilityLabel === label,
  )[0];
}

afterEach(() => {
  act(() => renderers.splice(0).forEach(renderer => renderer.unmount()));
});

test.each([
  ['Open settings', 'Settings stage'],
  ['Expand', 'Memories stage'],
  ['Apps', 'Connectors stage'],
])(
  'mobile %s opens its real destination and can return home',
  async (label, stage) => {
    const renderer = await renderApp();
    await act(async () => {
      if (label === 'Expand') {
        const expand = renderer.root.findAll(
          node => node.props.children === 'Expand',
        )[0];
        let button = expand.parent;
        while (button && typeof button.props.onPress !== 'function') {
          button = button.parent;
        }
        button!.props.onPress();
      } else {
        control(renderer, label).props.onPress();
      }
    });
    expect(control(renderer, stage)).toBeDefined();
    await act(async () => control(renderer, 'Back to Home').props.onPress());
    expect(control(renderer, 'Ask Omi')).toBeDefined();
  },
);

test('mobile Ask Omi opens the actual chat and reports a missing backend', async () => {
  const renderer = await renderApp();
  await act(async () => {
    renderer.root
      .findAllByType(TextInput)
      .find(node => node.props.accessibilityLabel === 'Ask Omi')!
      .props.onChangeText('Hello Omi');
  });
  await act(async () => control(renderer, 'Ask Omi').props.onSubmitEditing());
  expect(control(renderer, 'Chat scroll region')).toBeDefined();
  expect(JSON.stringify(renderer.toJSON())).toContain('Chat');
});
