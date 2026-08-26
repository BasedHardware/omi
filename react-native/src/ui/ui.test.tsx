import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';

const mockReact = React;
let mockPlatformOS = 'macos';
let mockReduceMotion = false;

jest.mock('react-native', () => {
  const ReactRuntime = require('react');
  const component =
    (name: string) =>
    ({children, ...props}: {children?: React.ReactNode}) =>
      ReactRuntime.createElement(name, props, children);
  const animation = () => ({
    start: jest.fn(),
    stop: jest.fn(),
  });

  return {
    Platform: {
      get OS() {
        return mockPlatformOS;
      },
    },
    AccessibilityInfo: {
      addEventListener: jest.fn(() => ({remove: jest.fn()})),
      isReduceMotionEnabled: jest.fn(() => Promise.resolve(false)),
    },
    Animated: {
      View: component('Animated.View'),
      Value: class {
        constructor(value: number) {
          this.value = value;
        }
        interpolate() {
          return 0;
        }
        setValue(value: number) {
          this.value = value;
        }
        value = 0;
      },
      loop: jest.fn(animation),
      parallel: jest.fn(animation),
      sequence: jest.fn(animation),
      spring: jest.fn(animation),
      timing: jest.fn(animation),
    },
    Easing: {
      bezier: () => undefined,
      cubic: {},
      inOut: (value: unknown) => value,
      linear: (value: unknown) => value,
      out: (value: unknown) => value,
    },
    Image: component('Image'),
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

jest.mock('../app/useReduceMotion', () => ({
  useReduceMotion: () => mockReduceMotion,
}));

import {Animated} from 'react-native';
import {Button} from './Button';
import {Field} from './Field';
import {Icon} from './Icon';
import {FocusPressable} from './Pressable';
import {tokens} from './tokens';
import {Onboarding} from './Onboarding';
import {
  OMI_MARK_INK,
  omiDotColor,
  omiMarkBrightness,
  omiMarkDotCenter,
  omiMarkGeometry,
} from './OmiAvatar';

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

function findOmiDots(renderer: ReactTestRenderer.ReactTestRenderer) {
  return renderer.root.find(
    node =>
      node.props.identity === 'omi' &&
      node.props.size === 104 &&
      node.props.animate !== undefined,
  );
}

function flattenStyle(style: unknown): Array<Record<string, unknown>> {
  return ([] as Array<unknown>)
    .concat(style)
    .filter(
      (entry): entry is Record<string, unknown> =>
        entry != null && typeof entry === 'object',
    );
}

function isWhiteInk(color: unknown): boolean {
  const value = String(color).trim().toLowerCase().replace(/\s+/g, '');
  return (
    value === '#fff' ||
    value === '#ffffff' ||
    value === 'white' ||
    value === 'rgb(255,255,255)' ||
    value === 'rgba(255,255,255,1)'
  );
}

function omiInkDotHosts(renderer: ReactTestRenderer.ReactTestRenderer) {
  return renderer.root.findAll(node => {
    if (String(node.type) !== 'Animated.View') {
      return false;
    }
    return flattenStyle(node.props.style).some(entry =>
      isWhiteInk(entry.backgroundColor),
    );
  });
}

describe('UI primitives', () => {
  beforeEach(() => {
    mockPlatformOS = 'macos';
    mockReduceMotion = false;
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

describe('Onboarding chrome', () => {
  beforeEach(() => {
    mockReduceMotion = false;
    (Animated.loop as jest.Mock).mockClear();
    (Animated.parallel as jest.Mock).mockClear();
    (Animated.sequence as jest.Mock).mockClear();
    (Animated.spring as jest.Mock).mockClear();
    (Animated.timing as jest.Mock).mockClear();
  });

  test('first-run onboarding is Welcome and Sign in only', () => {
    const renderer = render(
      <Onboarding onSignIn={() => undefined} signingIn={false} />,
    );
    const output = JSON.stringify(renderer.toJSON());

    expect(output).toContain('Welcome to Omi');
    expect(output).toContain('Sign in');
    expect(output).not.toContain('Search Omi');
    expect(output).not.toContain('Home search dock');
    expect(output).not.toContain('Home navigation');
    expect(output).not.toContain('Desktop application chrome');
  });

  test('Onboarding renders the Omi dots above Welcome to Omi', () => {
    const renderer = render(
      <Onboarding onSignIn={() => undefined} signingIn={false} />,
    );
    const output = JSON.stringify(renderer.toJSON());
    const title = renderer.root.find(
      node => node.props.accessibilityRole === 'header',
    );
    const dots = findOmiDots(renderer);

    expect(dots.props).toMatchObject({
      animate: true,
      identity: 'omi',
      reduceMotion: false,
      size: 104,
      tone: 'ink',
    });
    expect(omiInkDotHosts(renderer)).toHaveLength(8);
    const rainbow = Array.from({length: 8}, (_, index) =>
      omiDotColor('omi', index),
    );
    for (const color of rainbow) {
      expect(output).not.toContain(color);
    }
    expect(output.toLowerCase()).toContain('#ffffff');
    expect(
      renderer.root.findAll(node => String(node.type) === 'Image'),
    ).toHaveLength(0);
    expect(title.props.children).toBe('Welcome to Omi');
    const siblings = title.parent?.children ?? [];
    const dotsSlot = dots.parent;
    expect(dotsSlot).toBeTruthy();
    expect(
      siblings.indexOf(dotsSlot as (typeof siblings)[number]),
    ).toBeLessThan(siblings.indexOf(title));
    expect(output).toContain('Sign in');
    expect(output).not.toContain('Search Omi');
    expect(Animated.timing).toHaveBeenCalled();
    expect(Animated.loop).toHaveBeenCalled();
  });

  test('reduce-motion skips onboarding dots animation', () => {
    mockReduceMotion = true;
    const renderer = render(
      <Onboarding onSignIn={() => undefined} signingIn={false} />,
    );
    const dots = findOmiDots(renderer);

    expect(dots.props).toMatchObject({
      animate: false,
      identity: 'omi',
      reduceMotion: true,
      size: 104,
      tone: 'ink',
    });
    expect(Animated.timing).not.toHaveBeenCalled();
    expect(Animated.loop).not.toHaveBeenCalled();
    expect(Animated.parallel).not.toHaveBeenCalled();
    expect(Animated.sequence).not.toHaveBeenCalled();
    expect(Animated.spring).not.toHaveBeenCalled();
    const hosts = omiInkDotHosts(renderer);
    expect(hosts).toHaveLength(8);
    for (const host of hosts) {
      const style = Object.assign({}, ...flattenStyle(host.props.style));
      expect(isWhiteInk(style.backgroundColor)).toBe(true);
      expect(style.opacity).toBe(1);
    }
    expect(
      renderer.root.findAll(node => String(node.type) === 'Image'),
    ).toHaveLength(0);
  });

  test('first-run onboarding sits on the shared glass, not a nested card', () => {
    const renderer = render(
      <Onboarding onSignIn={() => undefined} signingIn={false} />,
    );
    const surface = renderer.root.find(
      node => node.props.accessibilityLabel === 'First-run onboarding',
    );
    const surfaceStyle = Object.assign(
      {},
      ...flattenStyle(surface.props.style),
    );
    const content = renderer.root.find(node =>
      flattenStyle(node.props.style).some(
        style => style.gap === tokens.space.sm && style.width === '100%',
      ),
    );
    const contentStyle = Object.assign(
      {},
      ...flattenStyle(content.props.style),
    );
    const dotsStyle = Object.assign(
      {},
      ...flattenStyle(findOmiDots(renderer).parent?.props.style),
    );

    expect(surfaceStyle).toMatchObject({
      alignSelf: 'stretch',
      flex: 1,
      paddingHorizontal: tokens.space.xxl,
      paddingVertical: tokens.space.xl,
    });
    expect(surfaceStyle.padding).toBeUndefined();
    expect(Number(surfaceStyle.paddingVertical)).toBeLessThan(
      tokens.space.xxxl,
    );
    expect(
      renderer.root.findAll(
        node =>
          node.props.accessibilityLabel === 'First-run onboarding material',
      ),
    ).toHaveLength(0);
    expect(contentStyle.gap).toBe(tokens.space.sm);
    expect(Number(contentStyle.gap)).toBeLessThan(tokens.space.lg);
    expect(dotsStyle.marginBottom ?? tokens.space.none).toBe(tokens.space.none);
  });

  test("welcome mark geometry is main's white ring, not a rainbow smile", () => {
    expect(OMI_MARK_INK).toBe('#ffffff');
    expect(omiMarkGeometry).toMatchObject({
      canvas: 260,
      axisRadius: 86.71,
      diagonalRadius: 91.92,
      idleBrightness: 0.5,
      pulseWidth: 0.18,
      lapMs: 900,
    });
    expect(omiMarkDotCenter(0)).toEqual({
      x: omiMarkGeometry.centre,
      y: omiMarkGeometry.centre - omiMarkGeometry.axisRadius,
    });
    expect(omiMarkBrightness(0, null)).toBe(1);
    expect(omiMarkBrightness(0, 0)).toBe(1);
    expect(omiMarkBrightness(4, 0.5)).toBe(1);
    expect(omiMarkBrightness(0, 0.5)).toBe(omiMarkGeometry.idleBrightness);
  });
});

describe('extracted modules', () => {
  test('omiDotColor stays in the avatar module', () => {
    expect(omiDotColor('omi', 0)).toBe(omiDotColor('omi', 0));
    expect(omiDotColor('omi', 0)).not.toBe(omiDotColor('other', 0));
  });
});

describe('signed-out Settings and first-run', () => {
  test('Account exposes Sign out and first-run stays the session-empty surface', () => {
    const settings = readFileSync(
      resolve(__dirname, '../pages/Settings.tsx'),
      'utf8',
    );
    const onboarding = readFileSync(
      resolve(__dirname, './Onboarding.tsx'),
      'utf8',
    );
    const gate = readFileSync(
      resolve(__dirname, '../app/useOnboarding.ts'),
      'utf8',
    );

    expect(settings).toContain('actionLabel="Sign out"');
    expect(settings).toContain('onSignOut');
    expect(settings).toContain('auth.signOut()');
    expect(settings).toContain('if (!result.signedOut)');
    expect(settings).not.toContain('Sign out is not exposed');
    expect(onboarding).toContain('First-run onboarding');
    expect(onboarding).toContain('Welcome to Omi');
    expect(gate).toContain('signOutAndRefresh');
    expect(gate).toMatch(
      /const hasSession = await auth\.hasCloudSession\(\);[^]*setOnboardingRequired\(true\)/,
    );
    expect(gate).toMatch(
      /const result = await auth\.signOut\(\);[^]*const hasSession = await auth\.hasCloudSession\(\)/,
    );
  });
});
