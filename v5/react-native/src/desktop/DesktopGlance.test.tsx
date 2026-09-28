import React from 'react';
import {Text} from 'react-native';
import ReactTestRenderer, {act} from 'react-test-renderer';

const mockBackend: {
  getApiContract: jest.Mock;
  request: jest.Mock;
} = {getApiContract: jest.fn(), request: jest.fn()};

jest.mock('../omiNative', () => ({
  get omiBackend() {
    return mockBackend;
  },
}));

import {GlanceCard} from './DesktopGlance';

const texts = (renderer: ReactTestRenderer.ReactTestRenderer) =>
  renderer.root.findAllByType(Text).map(node => node.props.children);

async function render() {
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  await act(async () => {
    renderer = ReactTestRenderer.create(<GlanceCard outcomes={null} />);
  });
  // Let the contract probe and the worker request settle.
  await act(async () => {
    await Promise.resolve();
  });
  return renderer;
}

beforeEach(() => {
  mockBackend.getApiContract.mockReset();
  mockBackend.request.mockReset();
});

test('the legacy backend shows no glance, fun fact or request', async () => {
  mockBackend.getApiContract.mockResolvedValue('omi');
  const renderer = await render();
  expect(renderer.toJSON()).toBeNull();
  expect(mockBackend.request).not.toHaveBeenCalled();
  act(() => renderer.unmount());
});

test('the v5 backend shows the worker glance line', async () => {
  mockBackend.getApiContract.mockResolvedValue('canonical');
  mockBackend.request.mockResolvedValue({
    id: 'desktop-glance',
    status: 200,
    body: JSON.stringify({title: 'Quiet morning', copy: 'Two meetings later.'}),
  });
  const renderer = await render();
  expect(mockBackend.request).toHaveBeenCalledWith(
    expect.objectContaining({
      path: '/v1/desktop/glance',
      expectedApiContract: 'canonical',
    }),
  );
  expect(texts(renderer)).toEqual(['Quiet morning', 'Two meetings later.']);
  act(() => renderer.unmount());
});

test('the v5 backend keeps a local line when the worker fails', async () => {
  mockBackend.getApiContract.mockResolvedValue('canonical');
  mockBackend.request.mockResolvedValue({
    id: 'desktop-glance',
    status: 503,
    body: null,
  });
  const renderer = await render();
  const [title, copy] = texts(renderer);
  expect(typeof title).toBe('string');
  expect((title as string).length).toBeGreaterThan(0);
  expect((copy as string).length).toBeGreaterThan(0);
  act(() => renderer.unmount());
});
