import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {TextInput} from 'react-native';

jest.mock('../omiNative', () => ({
  omiBackend: {request: jest.fn()},
}));

import {Composer} from './Composer';

function renderComposer(sendUnavailable: boolean) {
  const onSend = jest.fn();
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <Composer
        activeGenerationId={null}
        chatBusy={false}
        compact={false}
        composerFocused={false}
        composerMaxWidth={640}
        composerRef={{current: null}}
        draft=""
        onDraftChange={jest.fn()}
        onFocusChange={jest.fn()}
        onSend={onSend}
        onStop={jest.fn()}
        sendUnavailable={sendUnavailable}
      />,
    );
  });
  return {renderer, onSend};
}

test('composer stays askable when send is available', () => {
  const {renderer} = renderComposer(false);
  const input = renderer.root.findByType(TextInput);
  expect(input.props.placeholder).toBe('Ask anything...');
  expect(input.props.editable).toBe(true);
  expect(
    renderer.root.find(node => node.props.accessibilityLabel === 'Send message')
      .props.disabled,
  ).toBe(true);
});

test('composer does not keep an Ask anything door when send is unusable', () => {
  const {renderer} = renderComposer(true);
  const input = renderer.root.findByType(TextInput);
  expect(input.props.placeholder).toBe(
    'Sending messages is not available on this backend yet.',
  );
  expect(input.props.editable).toBe(false);
  expect(
    renderer.root.find(
      node => node.props.accessibilityLabel === 'Send message unavailable',
    ).props.disabled,
  ).toBe(true);
});
