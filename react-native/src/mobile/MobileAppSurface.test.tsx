import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';

jest.mock('react-native', () => {
  const ReactRuntime = require('react');
  const component =
    (name: string) =>
    ({children, ...elementProps}: {children?: React.ReactNode}) =>
      ReactRuntime.createElement(name, elementProps, children);
  return {
    FlatList: ({data, renderItem, ...listProps}: any) =>
      ReactRuntime.createElement(
        'FlatList',
        listProps,
        data.map((item: any, index: number) =>
          ReactRuntime.cloneElement(renderItem({item, index}), {
            key: item.key ?? item.id,
          }),
        ),
      ),
    KeyboardAvoidingView: component('KeyboardAvoidingView'),
    Platform: {OS: 'ios'},
    Pressable: component('Pressable'),
    SafeAreaView: component('SafeAreaView'),
    StyleSheet: {
      create: <T,>(styles: T) => styles,
      hairlineWidth: 1,
    },
    Text: component('Text'),
    TextInput: component('TextInput'),
    View: component('View'),
  };
});

import {MobileAppSurface, type MobileAppSurfaceProps} from './MobileAppSurface';

function buildProps(
  overrides: Partial<MobileAppSurfaceProps> = {},
): MobileAppSurfaceProps {
  return {
    activeRoute: 'home',
    askValue: '',
    capture: {active: true, transcript: 'Preparing the product demo'},
    device: {connected: true, label: '100%'},
    mindMapStatus: 'ready',
    onAskChange: jest.fn(),
    onAskSubmit: jest.fn(),
    onExpandMindMap: jest.fn(),
    onOpenCalls: jest.fn(),
    onOpenDevice: jest.fn(),
    onOpenSettings: jest.fn(),
    onRouteChange: jest.fn(),
    onTaskToggle: jest.fn(),
    onViewRecaps: jest.fn(),
    onViewTasks: jest.fn(),
    recaps: [
      {id: 'recap-1', title: 'Omi gets simpler', dateLabel: 'Yesterday'},
    ],
    recapStatus: 'ready',
    tasks: [{id: 'task-1', title: 'Prepare product demo', completed: false}],
    taskStatus: 'ready',
    ...overrides,
  };
}

function render(overrides: Partial<MobileAppSurfaceProps> = {}) {
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <MobileAppSurface {...buildProps(overrides)} />,
    );
  });
  return renderer;
}

function renderedText(renderer: ReactTestRenderer.ReactTestRenderer): string {
  return renderer.root
    .findAll(node => String(node.type) === 'Text')
    .flatMap(node =>
      Array.isArray(node.props.children)
        ? node.props.children
        : [node.props.children],
    )
    .filter(
      (value): value is string | number =>
        typeof value === 'string' || typeof value === 'number',
    )
    .join(' ');
}

describe('MobileAppSurface', () => {
  test('renders the shipping mobile hierarchy from real projections', () => {
    const tree = JSON.stringify(render().toJSON());
    expect(tree).toContain('Listening');
    expect(tree).toContain('Today');
    expect(tree).toContain('Prepare product demo');
    expect(tree).toContain('Daily Recaps');
    expect(tree).toContain('Omi gets simpler');
    expect(tree).toContain('Mind Map');
    expect(tree).not.toContain('Saved data unavailable');
    expect(tree).not.toContain('Retry');
  });

  test.each(['loading', 'empty', 'offline', 'error'] as const)(
    'renders a named %s projection state',
    status => {
      const renderer = render({taskStatus: status, tasks: []});
      const panel = renderer.root.find(
        node => node.props.accessibilityLabel === `tasks ${status} state`,
      );
      expect(panel).toBeDefined();
    },
  );

  test('routes and toggles with accessible controls', () => {
    const onRouteChange = jest.fn();
    const onTaskToggle = jest.fn();
    const renderer = render({onRouteChange, onTaskToggle});
    const apps = renderer.root.find(
      node => node.props.accessibilityLabel === 'Apps',
    );
    const task = renderer.root.find(
      node => node.props.accessibilityLabel === 'Complete Prepare product demo',
    );
    act(() => apps.props.onPress());
    act(() => task.props.onPress());
    expect(onRouteChange).toHaveBeenCalledWith('apps');
    expect(onTaskToggle).toHaveBeenCalledWith('task-1', true);
  });

  test.each([
    ['chat', 'What can I help you find?'],
    ['tasks', 'Prepare product demo'],
    ['apps', 'Your connected apps'],
  ] as const)('renders the shipping %s destination', (route, copy) => {
    const tree = renderedText(render({activeRoute: route}));
    expect(tree).toContain(copy);
    expect(tree).not.toContain('Saved data unavailable');
  });
});
