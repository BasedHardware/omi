import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';

const mockReact = React;
let mockPlatformOS = 'macos';

jest.mock('react-native', () => {
  const ReactRuntime = require('react');
  const component =
    (name: string) =>
    ({children, ...props}: {children?: React.ReactNode}) =>
      ReactRuntime.createElement(name, props, children);

  return {
    Platform: {
      get OS() {
        return mockPlatformOS;
      },
    },
    Pressable: component('Pressable'),
    StyleSheet: {create: <T,>(styles: T) => styles},
    Text: component('Text'),
    TextInput: component('TextInput'),
    View: component('View'),
  };
});

jest.mock('../native-component', () => ({
  requireNativeComponent: (name: string) => (props: Record<string, unknown>) =>
    mockReact.createElement(name, props),
}));

import {Button} from './Button';
import {Field} from './Field';
import {Icon} from './Icon';
import {FocusPressable} from './Pressable';
import {tokens} from './tokens';

function render(element: React.ReactElement) {
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(element);
  });
  return renderer;
}

function findHost(renderer: ReactTestRenderer.ReactTestRenderer, type: string) {
  return renderer.root.find(node => String(node.type) === type);
}

describe('UI primitives', () => {
  beforeEach(() => {
    mockPlatformOS = 'macos';
  });

  test('FocusPressable composes its focus state with caller behavior', () => {
    const onFocus = jest.fn();
    const renderer = render(
      <FocusPressable
        accessibilityLabel="Focus target"
        onFocus={onFocus}
        style={{opacity: 0.8}}
      />,
    );
    const pressable = findHost(renderer, 'Pressable');

    act(() => pressable.props.onFocus({}));

    expect(onFocus).toHaveBeenCalledTimes(1);
    expect(pressable.props.style({pressed: false})).toEqual(
      expect.arrayContaining([
        {opacity: 0.8},
        {
          borderColor: tokens.color.focus,
          borderWidth: tokens.border.width,
        },
      ]),
    );
  });

  test('Icon uses an SF Symbol on macOS without rendering its fallback', () => {
    const Fallback = jest.fn((props: Record<string, unknown>) =>
      mockReact.createElement('FallbackIcon', props),
    );
    const renderer = render(<Icon fallback={Fallback} symbolName="house" />);

    const symbol = renderer.toJSON() as ReactTestRenderer.ReactTestRendererJSON;
    expect(symbol.type).toBe('OmiSFSymbol');
    expect(symbol.props.symbolName).toBe('house');
    expect(Fallback).not.toHaveBeenCalled();
  });

  test('Icon uses lucide-compatible fallback props off macOS', () => {
    mockPlatformOS = 'ios';
    const Fallback = jest.fn((props: Record<string, unknown>) =>
      mockReact.createElement('FallbackIcon', props),
    );
    const renderer = render(
      <Icon
        accessibilityLabel="Fallback home"
        fallback={Fallback}
        symbolName="house"
      />,
    );

    const fallback =
      renderer.toJSON() as ReactTestRenderer.ReactTestRendererJSON;
    expect(fallback.type).toBe('FallbackIcon');
    expect(fallback.props).toMatchObject({
      accessibilityLabel: 'Fallback home',
      color: tokens.color.text,
      size: tokens.size.icon,
      strokeWidth: tokens.icon.strokeWidth,
    });
  });

  test('Button and Field expose accessible native control contracts', () => {
    const renderer = render(
      <>
        <Button accessibilityLabel="Continue">Continue</Button>
        <Field
          accessibilityLabel="Email"
          error="Enter a valid email"
          label="Email"
        />
      </>,
    );
    const button = findHost(renderer, 'Pressable');
    const input = findHost(renderer, 'TextInput');

    expect(button.props.accessibilityRole).toBe('button');
    expect(input.props.accessibilityLabel).toBe('Email');
    expect(input.props['aria-invalid']).toBe(true);
    expect(JSON.stringify(renderer.toJSON())).toContain('Continue');
    expect(JSON.stringify(renderer.toJSON())).toContain('Email');
    expect(JSON.stringify(renderer.toJSON())).toContain('Enter a valid email');
  });
});
