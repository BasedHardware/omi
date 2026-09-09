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
    ScrollView: component('ScrollView'),
    Linking: {openURL: jest.fn(async () => undefined)},
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
import {
  OutcomeStatus,
  ReadStatus,
  coverageStatusCopy,
  emptyLibraryCopy,
  homeSearchBannerPhase,
  homeSearchPhaseCopy,
  savedDataEmptyTitle,
} from './ReadStatus';
import {Field} from './Field';
import {Icon} from './Icon';
import {FocusPressable} from './Pressable';
import {ProjectionRow} from './ProjectionList';
import {clockLabel, projectionClockLabel} from '../desktopReadClient';
import {tokens} from './tokens';
import {Onboarding} from './Onboarding';
import {
  OMI_MARK_INK,
  omiDotColor,
  omiMarkBrightness,
  omiMarkDotCenter,
  omiMarkGeometry,
} from './OmiAvatar';
import {ChatMessageRow} from './ChatTranscript';

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
    expect(output).toContain(
      'Sign in to access your conversations and memories.',
    );
    expect(output).not.toContain('calm workspace');
    expect(output).not.toContain('Search Omi');
    expect(output).not.toContain('Home search dock');
    expect(output).not.toContain('Home navigation');
    expect(output).not.toContain('Desktop application chrome');
  });

  test('Onboarding renders the Omi dots above Welcome to Omi', () => {
    mockPlatformOS = 'ios';
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
    mockPlatformOS = 'ios';
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

  test('browser setup continues without offering unavailable wearable capture', () => {
    mockPlatformOS = 'web';
    const complete = jest.fn();
    const renderer = render(
      <Onboarding
        onSignIn={() => undefined}
        signingIn={false}
        setupRequired
        onCompleteSetup={complete}
      />,
    );
    expect(
      renderer.root.findAll(
        node => node.props.accessibilityLabel === 'Agree and connect Omi',
      ),
    ).toHaveLength(0);
    const action = renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Agree and continue',
    )[0];
    act(() => action.props.onPress());
    expect(complete).toHaveBeenCalledWith(false);
  });

  test('macOS onboarding renders dark ink on the light native window', () => {
    mockPlatformOS = 'macos';
    const renderer = render(
      <Onboarding
        onSignIn={() => undefined}
        signingIn={false}
        error="Try again"
      />,
    );
    const title = renderer.root.find(
      node => node.props.accessibilityRole === 'header',
    );
    expect(Object.assign({}, ...flattenStyle(title.props.style)).color).toBe(
      'rgba(0, 0, 0, 0.92)',
    );
    const dots = findOmiDots(renderer);
    expect(dots.props.inkColor).toBe('rgba(0, 0, 0, 0.92)');
    const hosts = dots.findAll(node => String(node.type) === 'Animated.View');
    expect(hosts).toHaveLength(8);
    for (const host of hosts) {
      expect(
        Object.assign({}, ...flattenStyle(host.props.style)).backgroundColor,
      ).toBe('rgba(0, 0, 0, 0.92)');
    }
    const error = renderer.root.find(
      node => node.props.accessibilityLabel === 'Sign-in error',
    );
    expect(Object.assign({}, ...flattenStyle(error.props.style)).color).toBe(
      'rgba(0, 0, 0, 0.64)',
    );
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
      ...flattenStyle(
        surface.props.contentContainerStyle ?? surface.props.style,
      ),
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
      flexGrow: 1,
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
      /const result = await auth\.signOut\(\);[^]*setOnboardingRequired\(true\)/,
    );
    // A failed confirmation probe must not strand a signed-out session in
    // the product shell: the gate falls back to Welcome either way.
    expect(gate).toMatch(
      /try \{[^]*hasSession = await auth\.hasCloudSession\(\);[^]*\} catch \{[^]*hasSession = false;/,
    );
  });
});

test('legacy unknown completeness is not presented as a known incomplete read', () => {
  const page = {
    windowStatus: 'unknown' as const,
    complete: false,
    hasMore: false,
    nextCursor: null,
    completenessStatus: 'unknown' as const,
    reasons: [],
  };
  const renderer = render(<ReadStatus label="Conversations" page={page} />);
  expect(renderer.toJSON()).toBeNull();
  act(() =>
    renderer.update(
      <ReadStatus
        label="Conversations"
        page={{...page, completenessStatus: 'incomplete'}}
      />,
    ),
  );
  expect(JSON.stringify(renderer.toJSON())).toContain(
    'Conversations are incomplete.',
  );
  act(() =>
    renderer.update(
      <ReadStatus
        label="Memories"
        page={{...page, completenessStatus: 'partial'}}
      />,
    ),
  );
  expect(JSON.stringify(renderer.toJSON())).toContain(
    'Memories are a partial view.',
  );
});

test('ReadStatus does not claim more pages when the continue door is unavailable', () => {
  const page = {
    windowStatus: 'more' as const,
    complete: false,
    hasMore: true,
    nextCursor: 'next-page',
    completenessStatus: 'complete' as const,
    reasons: [],
  };
  const renderer = render(
    <ReadStatus continueUnavailable label="Conversations" page={page} />,
  );
  expect(JSON.stringify(renderer.toJSON())).toBe('null');
  act(() => renderer.update(<ReadStatus label="Conversations" page={page} />));
  expect(JSON.stringify(renderer.toJSON())).toContain(
    'More conversations are available.',
  );
});

test('OutcomeStatus omits more-available after a closed later page', () => {
  const page = {
    windowStatus: 'more' as const,
    complete: false,
    hasMore: true,
    nextCursor: 'next-page',
    completenessStatus: 'complete' as const,
    reasons: [],
  };
  const renderer = render(
    <OutcomeStatus
      continueUnavailable
      label="Conversations"
      outcome={{status: 'success', value: {items: [], page}}}
    />,
  );
  expect(JSON.stringify(renderer.toJSON())).toBe('null');
  act(() =>
    renderer.update(
      <OutcomeStatus
        label="Conversations"
        outcome={{status: 'success', value: {items: [], page}}}
      />,
    ),
  );
  expect(JSON.stringify(renderer.toJSON())).toContain(
    'More conversations are available.',
  );
});

test('OutcomeStatus uses mapped library copy instead of a generic unavailable claim', () => {
  const mapped =
    'This saved data is not available from the selected Omi service yet.';
  const renderer = render(
    <OutcomeStatus
      label="Conversations"
      outcome={{status: 'error', error: mapped}}
    />,
  );
  const tree = JSON.stringify(renderer.toJSON());
  expect(tree).toContain(mapped);
  expect(tree).not.toContain('Conversations are unavailable.');
});

test('homeSearchPhaseCopy uses mapped copy instead of a generic unavailable claim', () => {
  const mapped =
    'This saved data is not available from the selected Omi service yet.';
  expect(homeSearchPhaseCopy('unavailable', mapped)).toBe(mapped);
  expect(homeSearchPhaseCopy('unavailable', null)).toBe(
    'Saved data is unavailable.',
  );
  expect(homeSearchPhaseCopy('initial-loading', mapped)).toBe(
    'Loading saved data…',
  );
  expect(homeSearchPhaseCopy('saved-but-refresh-failed', mapped)).toBe(
    'Showing saved data. Could not refresh.',
  );
});

test('homeSearchBannerPhase does not claim showing saved data when conversation and memory doors failed', () => {
  const mapped =
    'This saved data is not available from the selected Omi service yet.';
  expect(homeSearchBannerPhase('saved-but-refresh-failed', true)).toBe(
    'unavailable',
  );
  expect(homeSearchBannerPhase('saved-but-refresh-failed', false)).toBe(
    'saved-but-refresh-failed',
  );
  expect(homeSearchBannerPhase('unavailable', true)).toBe('unavailable');
  expect(homeSearchBannerPhase('ready', true)).toBe('unavailable');
  expect(homeSearchBannerPhase('refreshing', true)).toBe('refreshing');
  expect(
    homeSearchPhaseCopy(
      homeSearchBannerPhase('saved-but-refresh-failed', true),
      mapped,
    ),
  ).toBe(mapped);
  expect(
    homeSearchPhaseCopy(
      homeSearchBannerPhase('saved-but-refresh-failed', false),
      mapped,
    ),
  ).toBe('Showing saved data. Could not refresh.');
});

test('empty library copy keeps completeness instead of claiming emptiness', () => {
  const incomplete = {
    windowStatus: 'incomplete' as const,
    complete: false,
    hasMore: false,
    nextCursor: null,
    completenessStatus: 'incomplete' as const,
    reasons: ['accepted_work_pending'],
  };
  const complete = {
    ...incomplete,
    windowStatus: 'complete' as const,
    complete: true,
    completenessStatus: 'complete' as const,
    reasons: [],
  };
  expect(
    emptyLibraryCopy(
      'Memories',
      incomplete,
      false,
      'No loaded memories match.',
      'No memories yet.',
    ),
  ).toBe('Memories are incomplete.');
  expect(
    emptyLibraryCopy(
      'Memories',
      incomplete,
      true,
      'No loaded memories match.',
      'No memories yet.',
    ),
  ).toBe('Memories are incomplete.');
  expect(
    emptyLibraryCopy(
      'Memories',
      complete,
      true,
      'No loaded memories match.',
      'No memories yet.',
    ),
  ).toBe('No loaded memories match.');
  expect(
    emptyLibraryCopy(
      'Memories',
      complete,
      false,
      'No loaded memories match.',
      'No memories yet.',
    ),
  ).toBe('No memories yet.');
  expect(
    emptyLibraryCopy(
      'Memories',
      null,
      false,
      'No loaded memories match.',
      'No memories yet.',
    ),
  ).toBe('No memories yet.');
  expect(
    emptyLibraryCopy(
      'Memories',
      {
        ...incomplete,
        completenessStatus: 'degraded',
        reasons: ['projection_unavailable'],
      },
      false,
      'No loaded memories match.',
      'No memories yet.',
    ),
  ).toBe('Memories may be temporarily incomplete.');
  const more = {
    windowStatus: 'more' as const,
    complete: false,
    hasMore: true,
    nextCursor: 'next-page',
    completenessStatus: 'complete' as const,
    reasons: [],
  };
  expect(
    emptyLibraryCopy(
      'Tasks',
      more,
      true,
      'No loaded tasks match.',
      'No tasks yet.',
      true,
    ),
  ).toBe('No loaded tasks match.');
  expect(
    emptyLibraryCopy(
      'Tasks',
      more,
      true,
      'No loaded tasks match.',
      'No tasks yet.',
    ),
  ).toBe('More tasks are available.');
  expect(
    emptyLibraryCopy(
      'Tasks',
      more,
      false,
      'No loaded tasks match.',
      'No tasks yet.',
      true,
    ),
  ).toBe('More tasks are available.');
});

test('coverage copy wins over a complete Home search miss', () => {
  const incomplete = {
    windowStatus: 'incomplete' as const,
    complete: false,
    hasMore: false,
    nextCursor: null,
    completenessStatus: 'incomplete' as const,
    reasons: ['accepted_work_pending'],
  };
  const complete = {
    ...incomplete,
    windowStatus: 'complete' as const,
    complete: true,
    completenessStatus: 'complete' as const,
    reasons: [],
  };
  expect(coverageStatusCopy(incomplete, complete)).toBe(
    'Conversations are incomplete.',
  );
  expect(coverageStatusCopy(complete, incomplete)).toBe(
    'Memories are incomplete.',
  );
  expect(coverageStatusCopy(complete, complete)).toBeNull();
  expect(coverageStatusCopy(complete, complete, incomplete)).toBe(
    'Tasks are incomplete.',
  );
  expect(coverageStatusCopy(null, null)).toBeNull();
  expect(coverageStatusCopy(null, incomplete)).toBe('Memories are incomplete.');
  expect(coverageStatusCopy(complete, complete, null)).toBeNull();
  expect(
    coverageStatusCopy(complete, {
      ...incomplete,
      completenessStatus: 'degraded',
      reasons: ['projection_unavailable'],
    }),
  ).toBe('Memories may be temporarily incomplete.');
  expect(savedDataEmptyTitle(complete, complete, incomplete, true)).toBe(
    'Tasks are incomplete.',
  );
  expect(savedDataEmptyTitle(complete, complete, complete, true)).toBe(
    'No results',
  );
  expect(savedDataEmptyTitle(complete, complete, complete, false)).toBe(
    'Nothing saved yet',
  );
  const morePage = {
    windowStatus: 'more' as const,
    complete: false,
    hasMore: true,
    nextCursor: 'next-page',
    completenessStatus: 'complete' as const,
    reasons: [],
  };
  expect(
    savedDataEmptyTitle(morePage, complete, complete, true, {
      conversations: true,
    }),
  ).toBe('No results');
  expect(
    savedDataEmptyTitle(morePage, complete, complete, false, {
      conversations: true,
    }),
  ).toBe('More conversations are available.');
  expect(
    savedDataEmptyTitle(complete, morePage, complete, true, {
      memories: true,
    }),
  ).toBe('No results');
  expect(
    savedDataEmptyTitle(complete, complete, morePage, true, {tasks: true}),
  ).toBe('No results');
  expect(
    coverageStatusCopy(morePage, complete, complete, {conversations: true}),
  ).toBeNull();
  const orchestrator = readFileSync(
    resolve(__dirname, '../app/AppOrchestrator.tsx'),
    'utf8',
  );
  expect(orchestrator).toContain('homeSearchEmptyTitle');
  expect(orchestrator).toContain('savedDataEmptyTitle(');
  expect(orchestrator).toContain('homeSearchItems(');
  expect(orchestrator).toContain('conversationRecapTitle(');
  expect(orchestrator).toContain('homeSearchBannerPhase(');
  expect(orchestrator).toContain("readOutcomes.tasks.status === 'success'");
  expect(orchestrator).toContain(
    'conversations: conversationNotice === desktopBackendUnavailableCopy',
  );
  expect(orchestrator).toContain(
    'memories: memoryNotice === desktopBackendUnavailableCopy',
  );
  expect(orchestrator).toContain(
    'tasks: taskNotice === desktopBackendUnavailableCopy',
  );
  expect(orchestrator).toContain(
    'conversationNotice ===\n                                        desktopBackendUnavailableCopy',
  );
  expect(orchestrator).toContain(
    'memoryNotice ===\n                                        desktopBackendUnavailableCopy',
  );
  expect(orchestrator).toContain(
    'taskNotice === desktopBackendUnavailableCopy',
  );
  expect(orchestrator).toContain('<OutcomeStatus');
  expect(orchestrator).toContain('label="Tasks"');
  expect(orchestrator).toContain('outcome={readOutcomes.tasks}');
  const unavailableGate = orchestrator.indexOf('!allHomeReadsUnavailable && (');
  const tasksBlock = orchestrator.indexOf(
    '{readOutcomes !== null && (\n                                <OutcomeStatus',
  );
  expect(unavailableGate).toBeGreaterThan(-1);
  expect(tasksBlock).toBeGreaterThan(unavailableGate);
  expect(orchestrator.slice(unavailableGate, tasksBlock)).toContain(
    'label="Conversations"',
  );
  expect(orchestrator.slice(unavailableGate, tasksBlock)).toContain(
    'label="Memories"',
  );
  expect(orchestrator.slice(unavailableGate, tasksBlock)).not.toContain(
    'label="Tasks"',
  );
  expect(orchestrator.slice(tasksBlock, tasksBlock + 400)).toContain(
    'label="Tasks"',
  );
  expect(orchestrator.slice(tasksBlock, tasksBlock + 400)).not.toContain(
    'allHomeReadsUnavailable',
  );
  expect(orchestrator).toContain('recapCoverageCopy=');
  expect(orchestrator).toContain('taskCoverageCopy=');
  expect(orchestrator).toContain("readStatusCopy(\n                'Recaps'");
  expect(orchestrator).toContain("readStatusCopy(\n                'Tasks'");
  expect(orchestrator).toContain('mindMapCoverageCopy=');
  expect(orchestrator).toContain('mindMapHasItems=');
  expect(orchestrator).toContain('mindMapEmptyCopy=');
  expect(orchestrator).toContain("emptyLibraryCopy(\n          'Memories'");
  expect(orchestrator).toContain('onOpenRecap=');
  expect(orchestrator).toContain('starred: item.starred');
  expect(orchestrator).toContain('locked: item.locked');
  expect(orchestrator).toContain('discarded: item.discarded');
  expect(orchestrator).not.toContain('onOpenCalls=');
  expect(orchestrator).toContain('conversationDayLabel(');
  expect(orchestrator).not.toContain("weekday: 'long'");
  expect(orchestrator).toContain(
    'requestedConversationId={requestedConversationId}',
  );
  const transcript = readFileSync(
    resolve(__dirname, 'ChatTranscript.tsx'),
    'utf8',
  );
  expect(transcript).toContain('chatClockLabel(');
  expect(transcript).not.toContain('function formatChatTime');
  const conversationHistory = readFileSync(
    resolve(__dirname, 'ChatConversationHistory.tsx'),
    'utf8',
  );
  expect(conversationHistory).toContain('chatClockLabel(');
  expect(conversationHistory).not.toContain('function formatChatTime');
  const desktopHome = readFileSync(
    resolve(__dirname, '../desktop/DesktopHome.tsx'),
    'utf8',
  );
  expect(desktopHome).toContain('chatClockLabel(');
  expect(desktopHome).not.toContain('function formatChatTime');
});

test('chat message timestamps date older days instead of time only', () => {
  const now = new Date(2026, 7, 14, 12, 0);
  jest.useFakeTimers();
  jest.setSystemTime(now);
  const time = (value: Date) =>
    value.toLocaleTimeString(undefined, {
      hour: 'numeric',
      minute: '2-digit',
    });
  const message = (createdAt: number) => ({
    id: 'chat-1',
    text: 'Hello',
    sender: 'human' as const,
    createdAt,
    generationOutcome: null,
  });
  try {
    const today = new Date(2026, 7, 14, 8, 0);
    const todayTree = JSON.stringify(
      render(
        <ChatMessageRow
          animate={false}
          compact
          message={message(today.getTime())}
          reduceMotion
        />,
      ).toJSON(),
    );
    expect(todayTree).toContain(time(today));
    expect(todayTree).not.toContain('Yesterday');
    expect(todayTree).not.toContain(' · ');
    const yesterday = new Date(2026, 7, 13, 23, 0);
    expect(
      JSON.stringify(
        render(
          <ChatMessageRow
            animate={false}
            compact
            message={message(yesterday.getTime())}
            reduceMotion
          />,
        ).toJSON(),
      ),
    ).toContain(`Yesterday · ${time(yesterday)}`);
    const older = new Date(2026, 7, 10, 12, 0);
    expect(
      JSON.stringify(
        render(
          <ChatMessageRow
            animate={false}
            compact
            message={message(older.getTime())}
            reduceMotion
          />,
        ).toJSON(),
      ),
    ).toContain(
      `${older.toLocaleDateString(undefined, {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      })} · ${time(older)}`,
    );
  } finally {
    jest.useRealTimers();
  }
});

test('a zero chat timestamp says Time unavailable instead of 1970', () => {
  const tree = JSON.stringify(
    render(
      <ChatMessageRow
        animate={false}
        compact
        message={{
          id: 'chat-1',
          text: 'Hello',
          sender: 'human',
          createdAt: 0,
          generationOutcome: null,
        }}
        reduceMotion
      />,
    ).toJSON(),
  );
  expect(tree).toContain('Time unavailable');
  expect(tree).not.toContain('1970');
});

test('a cancelled empty chat message says Response stopped instead of a blank bubble', () => {
  const renderer = render(
    <ChatMessageRow
      animate={false}
      compact
      message={{
        id: 'chat-cancelled',
        text: '',
        sender: 'ai',
        createdAt: Date.now(),
        generationOutcome: 'cancelled',
      }}
      reduceMotion
    />,
  );
  const copies = renderer.root
    .findAll(node => String(node.type) === 'Text')
    .flatMap(node => {
      const children = node.props.children;
      if (typeof children === 'string') {
        return [children];
      }
      if (Array.isArray(children)) {
        return children.filter(
          (child): child is string => typeof child === 'string',
        );
      }
      return [];
    });
  expect(copies).toContain('Response stopped');
  expect(copies).not.toContain('');
  act(() => {
    renderer.unmount();
  });
});

test('a cancelled whitespace-only chat message says Response stopped instead of a blank bubble', () => {
  const renderer = render(
    <ChatMessageRow
      animate={false}
      compact
      message={{
        id: 'chat-cancelled-whitespace',
        text: ' \t\n',
        sender: 'ai',
        createdAt: Date.now(),
        generationOutcome: 'cancelled',
      }}
      reduceMotion
    />,
  );
  const copies = renderer.root
    .findAll(node => String(node.type) === 'Text')
    .flatMap(node => {
      const children = node.props.children;
      if (typeof children === 'string') {
        return [children];
      }
      if (Array.isArray(children)) {
        return children.filter(
          (child): child is string => typeof child === 'string',
        );
      }
      return [];
    });
  expect(copies).toContain('Response stopped');
  expect(copies).not.toContain(' \t\n');
  act(() => {
    renderer.unmount();
  });
});

test('a cancelled NEXT LINE-only chat message says Response stopped instead of a blank bubble', () => {
  const renderer = render(
    <ChatMessageRow
      animate={false}
      compact
      message={{
        id: 'chat-cancelled-next-line',
        text: '\u0085',
        sender: 'ai',
        createdAt: Date.now(),
        generationOutcome: 'cancelled',
      }}
      reduceMotion
    />,
  );
  const copies = renderer.root
    .findAll(node => String(node.type) === 'Text')
    .flatMap(node => {
      const children = node.props.children;
      if (typeof children === 'string') {
        return [children];
      }
      if (Array.isArray(children)) {
        return children.filter(
          (child): child is string => typeof child === 'string',
        );
      }
      return [];
    });
  expect(copies).toContain('Response stopped');
  expect(copies).not.toContain('\u0085');
  expect(copies.filter(copy => copy === 'Response stopped')).toHaveLength(1);
  act(() => {
    renderer.unmount();
  });
});

test('an empty chat bubble keeps history attachment names instead of Message text unavailable', () => {
  const renderer = render(
    <ChatMessageRow
      animate={false}
      compact
      message={{
        id: 'chat-human-attachment',
        text: ' \t\n',
        sender: 'human',
        createdAt: Date.now(),
        generationOutcome: null,
        attachments: [
          {
            id: 'att-notes',
            displayName: 'notes.txt',
            mediaType: 'text/plain',
            sizeBytes: 12,
          },
        ],
      }}
      reduceMotion
    />,
  );
  const copies = renderer.root
    .findAll(node => String(node.type) === 'Text')
    .flatMap(node => {
      const children = node.props.children;
      if (typeof children === 'string') {
        return [children];
      }
      if (Array.isArray(children)) {
        return children.filter(
          (child): child is string => typeof child === 'string',
        );
      }
      return [];
    });
  expect(copies).toContain('notes.txt · Text · 12 B');
  expect(copies).not.toContain('Message text unavailable');
  expect(copies).not.toContain(' \t\n');
  act(() => {
    renderer.unmount();
  });
});

test('a whitespace-only human chat message says Message text unavailable instead of a blank bubble', () => {
  const renderer = render(
    <ChatMessageRow
      animate={false}
      compact
      message={{
        id: 'chat-human-whitespace',
        text: ' \t\n',
        sender: 'human',
        createdAt: Date.now(),
        generationOutcome: null,
      }}
      reduceMotion
    />,
  );
  const copies = renderer.root
    .findAll(node => String(node.type) === 'Text')
    .flatMap(node => {
      const children = node.props.children;
      if (typeof children === 'string') {
        return [children];
      }
      if (Array.isArray(children)) {
        return children.filter(
          (child): child is string => typeof child === 'string',
        );
      }
      return [];
    });
  expect(copies).toContain('Message text unavailable');
  expect(copies).not.toContain(' \t\n');
  expect(copies).not.toContain('Response stopped');
  act(() => {
    renderer.unmount();
  });
});

test('a completed whitespace-only chat message says Message text unavailable instead of a blank bubble', () => {
  const renderer = render(
    <ChatMessageRow
      animate={false}
      compact
      message={{
        id: 'chat-completed-whitespace',
        text: ' \t\n',
        sender: 'ai',
        createdAt: Date.now(),
        generationOutcome: 'completed',
      }}
      reduceMotion
    />,
  );
  const copies = renderer.root
    .findAll(node => String(node.type) === 'Text')
    .flatMap(node => {
      const children = node.props.children;
      if (typeof children === 'string') {
        return [children];
      }
      if (Array.isArray(children)) {
        return children.filter(
          (child): child is string => typeof child === 'string',
        );
      }
      return [];
    });
  expect(copies).toContain('Message text unavailable');
  expect(copies).not.toContain(' \t\n');
  expect(copies).not.toContain('Response stopped');
  act(() => {
    renderer.unmount();
  });
});

test('a cancelled chat message with text still says Response stopped', () => {
  const renderer = render(
    <ChatMessageRow
      animate={false}
      compact
      message={{
        id: 'chat-cancelled-text',
        text: 'Partial answer',
        sender: 'ai',
        createdAt: Date.now(),
        generationOutcome: 'cancelled',
      }}
      reduceMotion
    />,
  );
  const copies = renderer.root
    .findAll(node => String(node.type) === 'Text')
    .flatMap(node => {
      const children = node.props.children;
      if (typeof children === 'string') {
        return [children];
      }
      if (Array.isArray(children)) {
        return children.filter(
          (child): child is string => typeof child === 'string',
        );
      }
      return [];
    });
  expect(copies).toContain('Partial answer');
  expect(copies).toContain('Response stopped');
  act(() => {
    renderer.unmount();
  });
});

test('an unknown chat sender says Sender unavailable instead of looking like a quiet AI turn', () => {
  const renderer = render(
    <ChatMessageRow
      animate={false}
      compact
      message={{
        id: 'chat-unknown',
        text: 'stored without a known sender',
        sender: 'unknown',
        createdAt: Date.now(),
        generationOutcome: null,
      }}
      reduceMotion
    />,
  );
  const copies = renderer.root
    .findAll(node => String(node.type) === 'Text')
    .flatMap(node => {
      const children = node.props.children;
      if (typeof children === 'string') {
        return [children];
      }
      if (Array.isArray(children)) {
        return children.filter(
          (child): child is string => typeof child === 'string',
        );
      }
      return [];
    });
  expect(copies).toContain('Sender unavailable');
  expect(copies).toContain('stored without a known sender');
  expect(copies).not.toContain('You');
  expect(copies).not.toContain('Omi');
  act(() => {
    renderer.unmount();
  });
});

test('wide Home search rows keep untitled processing conversations visible', () => {
  const renderer = render(
    <ProjectionRow
      item={{
        kind: 'conversation',
        id: 'listen:processing-home-search',
        title: '',
        summary: '',
        searchableText:
          'Processing conversation…\nConversation summary is not ready yet.',
        createdAt: '2026-09-07T00:00:00.000Z',
        updatedAt: '2026-09-07T00:01:00.000Z',
        startedAt: '2026-09-07T00:00:00.000Z',
        finishedAt: '2026-09-07T00:01:00.000Z',
        starred: false,
        status: 'processing',
        source: 'listen',
        visibility: 'private',
        folderId: null,
        locked: false,
        discarded: false,
      }}
    />,
  );
  const tree = JSON.stringify(renderer.toJSON());
  expect(tree).toContain('Processing conversation…');
  expect(tree).toContain('Conversation summary is not ready yet.');
});

test('wide Home search rows keep empty completed conversation copy visible', () => {
  const renderer = render(
    <ProjectionRow
      item={{
        kind: 'conversation',
        id: 'recording:completed-home-search',
        title: '',
        summary: '',
        searchableText:
          'Conversation title unavailable\nConversation summary unavailable',
        createdAt: '2026-09-07T00:00:00.000Z',
        updatedAt: '2026-09-07T00:01:00.000Z',
        startedAt: '2026-09-07T00:00:00.000Z',
        finishedAt: '2026-09-07T00:01:00.000Z',
        starred: false,
        status: 'completed',
        source: 'omi',
        visibility: 'private',
        folderId: null,
        locked: false,
        discarded: false,
      }}
    />,
  );
  const tree = JSON.stringify(renderer.toJSON());
  expect(tree).toContain('Conversation title unavailable');
  expect(tree).toContain('Conversation summary unavailable');
});

test('wide Home search rows keep supplied conversation title and summary', () => {
  const renderer = render(
    <ProjectionRow
      item={{
        kind: 'conversation',
        id: 'recording:named-home-search',
        title: 'Morning walk',
        summary: 'Discussed the launch.',
        searchableText: 'Morning walk\nDiscussed the launch.',
        createdAt: '2026-09-07T00:00:00.000Z',
        updatedAt: '2026-09-07T00:01:00.000Z',
        startedAt: '2026-09-07T00:00:00.000Z',
        finishedAt: '2026-09-07T00:01:00.000Z',
        starred: false,
        status: 'completed',
        source: 'omi',
        visibility: 'private',
        folderId: null,
        locked: false,
        discarded: false,
      }}
    />,
  );
  const tree = JSON.stringify(renderer.toJSON());
  expect(tree).toContain('Morning walk');
  expect(tree).toContain('Discussed the launch.');
  expect(tree).not.toContain('Processing conversation…');
  expect(tree).not.toContain('Conversation title unavailable');
});

test('wide Home search rows keep listen overview speech on the title', () => {
  const title = 'a'.repeat(80);
  const summary = `${title} later speech`;
  const renderer = render(
    <ProjectionRow
      item={{
        kind: 'conversation',
        id: 'conversation-one',
        title,
        summary,
        searchableText: `${title}\n${summary}`,
        createdAt: '2026-09-07T00:00:00.000Z',
        updatedAt: '2026-09-07T00:01:00.000Z',
        startedAt: '2026-09-07T00:00:00.000Z',
        finishedAt: '2026-09-07T00:01:00.000Z',
        starred: false,
        status: 'completed',
        source: 'listen',
        visibility: 'private',
        folderId: null,
        locked: false,
        discarded: false,
      }}
    />,
  );
  const tree = JSON.stringify(renderer.toJSON());
  expect(tree).toContain(summary);
  expect(tree).not.toContain('Conversation title unavailable');
  expect(
    renderer.root.findAll(
      node => node.props.numberOfLines === 3 && node.props.children === summary,
    ).length,
  ).toBeGreaterThan(0);
});

test('wide Home search rows keep GET duration instead of title-only', () => {
  const renderer = render(
    <ProjectionRow
      item={{
        kind: 'conversation',
        id: 'listen:quick-home-search',
        title: 'Quick note',
        summary: 'Twenty seconds.',
        searchableText: 'Quick note\nTwenty seconds.',
        createdAt: '2026-09-07T12:00:00.000Z',
        updatedAt: '2026-09-07T12:00:20.000Z',
        startedAt: '2026-09-07T12:00:00.000Z',
        finishedAt: '2026-09-07T12:00:20.000Z',
        starred: false,
        status: 'completed',
        source: 'listen',
        visibility: 'private',
        folderId: null,
        locked: false,
        discarded: false,
      }}
    />,
  );
  const tree = JSON.stringify(renderer.toJSON());
  expect(tree).toContain('Quick note');
  expect(tree).toContain('< 1 min');
  expect(tree).not.toContain('0 min');
  expect(
    renderer.root.findAll(
      node =>
        node.props.numberOfLines === 1 &&
        typeof node.props.children === 'string' &&
        node.props.children.includes('< 1 min'),
    ).length,
  ).toBe(0);
});

test('wide Home search in-progress chats omit Duration unavailable', () => {
  const renderer = render(
    <ProjectionRow
      item={{
        kind: 'conversation',
        id: 'chat:session-alpha',
        title: 'Hi',
        summary: 'Later independent turn',
        searchableText: 'Hi\nLater independent turn',
        createdAt: '2026-09-07T00:00:00.000Z',
        updatedAt: '2026-09-07T00:01:00.000Z',
        startedAt: '2026-09-07T00:00:00.000Z',
        finishedAt: null,
        starred: false,
        status: 'in_progress',
        source: 'chat',
        visibility: 'private',
        folderId: null,
        locked: false,
        discarded: false,
      }}
    />,
  );
  const tree = JSON.stringify(renderer.toJSON());
  expect(tree).toContain('Hi');
  expect(tree).toContain('Later independent turn');
  expect(tree).not.toContain('Duration unavailable');
});

test('wide Home search rows with a zero start time say Duration unavailable', () => {
  const renderer = render(
    <ProjectionRow
      item={{
        kind: 'conversation',
        id: 'listen:epoch-duration-home-search',
        title: 'Missing start',
        summary: 'Finished without a real start time.',
        searchableText: 'Missing start\nFinished without a real start time.',
        createdAt: new Date(0).toISOString(),
        updatedAt: '2026-09-07T12:00:00.000Z',
        startedAt: new Date(0).toISOString(),
        finishedAt: '2026-09-07T12:00:00.000Z',
        starred: false,
        status: 'completed',
        source: 'listen',
        visibility: 'private',
        folderId: null,
        locked: false,
        discarded: false,
      }}
    />,
  );
  const tree = JSON.stringify(renderer.toJSON());
  expect(tree).toContain('Duration unavailable');
  expect(tree).not.toContain('hr');
});

test('wide Home search rows keep GET conversation clock instead of title-only', () => {
  const item = {
    kind: 'conversation' as const,
    id: 'listen:quick-home-search-clock',
    title: 'Quick note',
    summary: 'Twenty seconds.',
    searchableText: 'Quick note\nTwenty seconds.',
    createdAt: '2026-09-07T12:00:00.000Z',
    updatedAt: '2026-09-07T12:00:20.000Z',
    startedAt: '2026-09-07T12:00:00.000Z',
    finishedAt: '2026-09-07T12:00:20.000Z',
    starred: false,
    status: 'completed',
    source: 'listen',
    visibility: 'private' as const,
    folderId: null,
    locked: false,
    discarded: false,
  };
  const renderer = render(<ProjectionRow item={item} />);
  const expected = projectionClockLabel(item, Date.now());
  const tree = JSON.stringify(renderer.toJSON());
  expect(tree).toContain('Quick note');
  expect(tree).toContain(expected);
  expect(tree).not.toContain('Time unavailable');
  expect(
    renderer.root.findAll(
      node =>
        node.props.numberOfLines === 1 &&
        typeof node.props.children === 'string' &&
        node.props.children.includes(expected),
    ).length,
  ).toBe(0);
});

test('wide Home search memory rows keep GET timestamps instead of citation-only', () => {
  const item = {
    kind: 'memory' as const,
    id: 'memory-dated-home-search',
    title: 'A walk.',
    summary: 'A walk.',
    searchableText: 'A walk.',
    citations: ['citation-v1:launch'],
    timestamp: 1_788_492_408,
    provenance: {
      label: null,
      synthesisVersion: null,
      inputDigest: null,
      outputDigest: null,
    },
  };
  const renderer = render(<ProjectionRow item={item} />);
  const expected = projectionClockLabel(item, Date.now());
  const tree = JSON.stringify(renderer.toJSON());
  expect(tree).toContain('A walk.');
  expect(tree).toContain('1 citation');
  expect(tree).toContain(expected);
  expect(tree).not.toContain('Time unavailable');
});

test('wide Home search memory rows keep GET synthesized-memory chrome instead of citation-only', () => {
  const renderer = render(
    <ProjectionRow
      item={{
        kind: 'memory',
        id: 'memory-synthesized-home-search',
        title: 'A walk.',
        summary: 'A walk.',
        searchableText: 'A walk.',
        citations: ['citation-v1:launch'],
        timestamp: 1_788_492_408,
        provenance: {
          label: null,
          synthesisVersion: '1',
          inputDigest: null,
          outputDigest: null,
        },
      }}
    />,
  );
  const tree = JSON.stringify(renderer.toJSON());
  expect(tree).toContain('A walk.');
  expect(tree).toContain('1 citation');
  expect(tree).toContain('Synthesized memory');
});

test('compact Home current memory rows keep GET synthesized-memory chrome', () => {
  const renderer = render(
    <ProjectionRow
      home
      item={{
        kind: 'memory',
        id: 'memory-synthesized-home-current',
        title: 'A walk.',
        summary: 'A walk.',
        searchableText: 'A walk.',
        citations: ['citation-v1:launch'],
        timestamp: 1_788_492_408,
        provenance: {
          label: null,
          synthesisVersion: '1',
          inputDigest: null,
          outputDigest: null,
        },
      }}
    />,
  );
  const tree = JSON.stringify(renderer.toJSON());
  expect(tree).toContain('A walk.');
  expect(tree).toContain('1 citation');
  expect(tree).toContain('Synthesized memory');
});

test('a zero wide Home search conversation timestamp says Time unavailable', () => {
  const item = {
    kind: 'conversation' as const,
    id: 'listen:epoch-clock-home-search',
    title: 'Missing start',
    summary: 'Finished without a real start time.',
    searchableText: 'Missing start\nFinished without a real start time.',
    createdAt: new Date(0).toISOString(),
    updatedAt: '2026-09-07T12:00:00.000Z',
    startedAt: new Date(0).toISOString(),
    finishedAt: '2026-09-07T12:00:00.000Z',
    starred: false,
    status: 'completed',
    source: 'listen',
    visibility: 'private' as const,
    folderId: null,
    locked: false,
    discarded: false,
  };
  const renderer = render(<ProjectionRow item={item} />);
  const tree = JSON.stringify(renderer.toJSON());
  expect(tree).toContain('Time unavailable');
  expect(tree).not.toContain('1970');
});

test('wide Home search rows keep empty memory text visible', () => {
  const renderer = render(
    <ProjectionRow
      item={{
        kind: 'memory',
        id: 'memory-blank-home-search',
        title: '',
        summary: '',
        searchableText: 'Memory text unavailable',
        citations: [],
        timestamp: null,
        provenance: {
          label: null,
          synthesisVersion: '1',
          inputDigest: 'a',
          outputDigest: 'b',
        },
      }}
    />,
  );
  const tree = JSON.stringify(renderer.toJSON());
  expect(tree).toContain('Memory text unavailable');
  expect(tree).toContain('0 citations');
  expect(tree).not.toContain('Synthesized memory with source citations');
});

test('wide Home search rows strip namespaced memory prefixes', () => {
  const renderer = render(
    <ProjectionRow
      item={{
        kind: 'memory',
        id: 'memory-entity-home-search',
        title:
          'entity:qa:000008 qa_memory (observed 2026-07-30T12:00:00.000Z).',
        summary:
          'entity:qa:000008 qa_memory (observed 2026-07-30T12:00:00.000Z).',
        searchableText: 'qa_memory (observed 2026-07-30T12:00:00.000Z).',
        citations: [],
        timestamp: null,
        provenance: {
          label: 'entity:qa:000008',
          synthesisVersion: null,
          inputDigest: null,
          outputDigest: null,
        },
      }}
    />,
  );
  const tree = JSON.stringify(renderer.toJSON());
  expect(tree).toContain('qa_memory (observed 2026-07-30T12:00:00.000Z).');
  expect(tree).not.toContain('entity:qa:000008');
  expect(tree).toContain('0 citations');
  expect(tree).not.toContain('Synthesized memory with source citations');
});

test('wide Home search rows strip namespaced memory prefixes separated by NEXT LINE', () => {
  const renderer = render(
    <ProjectionRow
      item={{
        kind: 'memory',
        id: 'memory-entity-home-search-nel',
        title:
          'entity:qa:000008\u0085qa_memory (observed 2026-07-30T12:00:00.000Z).',
        summary:
          'entity:qa:000008\u0085qa_memory (observed 2026-07-30T12:00:00.000Z).',
        searchableText: 'qa_memory (observed 2026-07-30T12:00:00.000Z).',
        citations: [],
        timestamp: null,
        provenance: {
          label: null,
          synthesisVersion: null,
          inputDigest: null,
          outputDigest: null,
        },
      }}
    />,
  );
  const tree = JSON.stringify(renderer.toJSON());
  expect(tree).toContain('qa_memory (observed 2026-07-30T12:00:00.000Z).');
  expect(tree).not.toContain('entity:qa:000008');
  expect(tree).not.toContain('\u0085');
});

test('wide Home search rows report a single memory citation', () => {
  const renderer = render(
    <ProjectionRow
      item={{
        kind: 'memory',
        id: 'memory-one-citation-home-search',
        title: 'Prefers concise release notes',
        summary: 'Release notes should lead with the outcome.',
        searchableText:
          'Prefers concise release notes\nRelease notes should lead with the outcome.',
        citations: ['citation-v1:launch'],
        timestamp: null,
        provenance: {
          label: null,
          synthesisVersion: '1',
          inputDigest: 'a',
          outputDigest: 'b',
        },
      }}
    />,
  );
  const tree = JSON.stringify(renderer.toJSON());
  expect(tree).toContain('Prefers concise release notes');
  expect(tree).toContain('1 citation');
  expect(tree).not.toContain('Synthesized memory with source citations');
});

test('wide Home search rows omit whitespace-only memory citations from the count', () => {
  const renderer = render(
    <ProjectionRow
      item={{
        kind: 'memory',
        id: 'memory-whitespace-citation-home-search',
        title: 'Prefers concise release notes',
        summary: 'Release notes should lead with the outcome.',
        searchableText:
          'Prefers concise release notes\nRelease notes should lead with the outcome.',
        citations: [' \t\n', ''],
        timestamp: null,
        provenance: {
          label: null,
          synthesisVersion: '1',
          inputDigest: 'a',
          outputDigest: 'b',
        },
      }}
    />,
  );
  const tree = JSON.stringify(renderer.toJSON());
  expect(tree).toContain('0 citations');
  expect(tree).not.toContain('2 citations');
  expect(tree).not.toContain('"1 citation"');
});

test('wide Home search rows date task dues instead of a raw epoch', () => {
  const dueAt = 1786000000;
  const expected = `Due ${new Date(dueAt * 1000).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  })}`;
  const renderer = render(
    <ProjectionRow
      item={{
        kind: 'task',
        id: 'task-due-home-search',
        title: 'Prepare launch notes',
        summary: `Due ${dueAt}`,
        searchableText: 'Prepare launch notes',
        completed: false,
        completedAt: null,
        dueAt,
        owner: null,
        source: 'assistant',
        provenance: [],
        sortOrder: 1,
        indentLevel: 0,
        createdAt: 1785900000,
        updatedAt: 1785900100,
        revision: null,
      }}
    />,
  );
  const tree = JSON.stringify(renderer.toJSON());
  expect(tree).toContain('Prepare launch notes');
  expect(tree).toContain(expected);
  expect(tree).not.toContain('Due 1786000000');
});

test('wide Home search rows with no due date say No due date instead of Pending', () => {
  const renderer = render(
    <ProjectionRow
      item={{
        kind: 'task',
        id: 'task-missing-due-home-search',
        title: 'Prepare launch notes',
        summary: 'Pending',
        searchableText: 'Prepare launch notes',
        completed: false,
        completedAt: null,
        dueAt: null,
        owner: null,
        source: 'assistant',
        provenance: [],
        sortOrder: 1,
        indentLevel: 0,
        createdAt: 1785900000,
        updatedAt: 1785900100,
        revision: null,
      }}
    />,
  );
  const tree = JSON.stringify(renderer.toJSON());
  expect(tree).toContain('Prepare launch notes');
  expect(tree).toContain('No due date');
  expect(tree).not.toContain('Pending');
  const currents = render(
    <ProjectionRow
      home
      item={{
        kind: 'task',
        id: 'task-missing-due-home-current',
        title: 'Prepare launch notes',
        summary: 'Pending',
        searchableText: 'Prepare launch notes',
        completed: false,
        completedAt: null,
        dueAt: null,
        owner: null,
        source: 'assistant',
        provenance: [],
        sortOrder: 1,
        indentLevel: 0,
        createdAt: 1785900000,
        updatedAt: 1785900100,
        revision: null,
      }}
    />,
  );
  const currentsTree = JSON.stringify(currents.toJSON());
  expect(currentsTree).toContain('No due date');
  expect(currentsTree).not.toContain('Pending');
});

test('wide Home search rows keep GET capture time instead of started-only', () => {
  const captured = new Date(2025, 7, 10, 12, 0);
  const expected = `Captured (device time) · ${clockLabel(
    captured.getTime(),
    Date.now(),
  )}`;
  const renderer = render(
    <ProjectionRow
      item={{
        kind: 'conversation',
        id: 'recording:captured-home-search',
        title: 'Device capture',
        summary: 'Recorded on the wearable.',
        searchableText: 'Device capture\nRecorded on the wearable.',
        createdAt: captured.toISOString(),
        updatedAt: captured.toISOString(),
        startedAt: captured.toISOString(),
        finishedAt: captured.toISOString(),
        capturedAtMs: captured.getTime(),
        starred: false,
        status: 'completed',
        source: 'omi',
        visibility: 'private',
        folderId: null,
        locked: false,
        discarded: false,
      }}
    />,
  );
  const tree = JSON.stringify(renderer.toJSON());
  expect(tree).toContain('Device capture');
  expect(tree).toContain(expected);
  expect(tree).not.toContain('1970');
  const compact = render(
    <ProjectionRow
      home
      item={{
        kind: 'conversation',
        id: 'recording:captured-home-search',
        title: 'Device capture',
        summary: 'Recorded on the wearable.',
        searchableText: 'Device capture\nRecorded on the wearable.',
        createdAt: captured.toISOString(),
        updatedAt: captured.toISOString(),
        startedAt: captured.toISOString(),
        finishedAt: captured.toISOString(),
        capturedAtMs: captured.getTime(),
        starred: false,
        status: 'completed',
        source: 'omi',
        visibility: 'private',
        folderId: null,
        locked: false,
        discarded: false,
      }}
    />,
  );
  expect(JSON.stringify(compact.toJSON())).toContain(expected);
  const plain = render(
    <ProjectionRow
      item={{
        kind: 'conversation',
        id: 'recording:plain-home-search',
        title: 'Untimed recording',
        summary: 'Recorded on the wearable.',
        searchableText: 'Untimed recording\nRecorded on the wearable.',
        createdAt: captured.toISOString(),
        updatedAt: captured.toISOString(),
        startedAt: captured.toISOString(),
        finishedAt: captured.toISOString(),
        starred: false,
        status: 'completed',
        source: 'omi',
        visibility: 'private',
        folderId: null,
        locked: false,
        discarded: false,
      }}
    />,
  );
  expect(JSON.stringify(plain.toJSON())).not.toContain(
    'Captured (device time)',
  );
});

test('wide Home search rows keep GET locked and discarded flags instead of title-only', () => {
  const renderer = render(
    <ProjectionRow
      item={{
        kind: 'conversation',
        id: 'listen:locked-home-search',
        title: 'Kept recording',
        summary: 'Saved words',
        searchableText: 'Kept recording\nSaved words',
        createdAt: '2026-09-07T12:00:00.000Z',
        updatedAt: '2026-09-07T12:00:20.000Z',
        startedAt: '2026-09-07T12:00:00.000Z',
        finishedAt: '2026-09-07T12:00:20.000Z',
        starred: false,
        status: 'processing',
        source: 'listen',
        visibility: 'private',
        folderId: null,
        locked: true,
        discarded: true,
      }}
    />,
  );
  const tree = JSON.stringify(renderer.toJSON());
  expect(tree).toContain('Kept recording');
  expect(tree).toContain('Locked');
  expect(tree).toContain('Discarded');
  const plain = render(
    <ProjectionRow
      item={{
        kind: 'conversation',
        id: 'listen:plain-home-search',
        title: 'Open recording',
        summary: 'Saved words',
        searchableText: 'Open recording\nSaved words',
        createdAt: '2026-09-07T12:00:00.000Z',
        updatedAt: '2026-09-07T12:00:20.000Z',
        startedAt: '2026-09-07T12:00:00.000Z',
        finishedAt: '2026-09-07T12:00:20.000Z',
        starred: false,
        status: 'completed',
        source: 'listen',
        visibility: 'private',
        folderId: null,
        locked: false,
        discarded: false,
      }}
    />,
  );
  const plainTree = JSON.stringify(plain.toJSON());
  expect(plainTree).not.toContain('Locked');
  expect(plainTree).not.toContain('Discarded');
});

test('wide Home search rows keep GET failed status instead of title-only', () => {
  const renderer = render(
    <ProjectionRow
      item={{
        kind: 'conversation',
        id: 'recording:failed-home-search',
        title: '',
        summary: '',
        searchableText: '',
        createdAt: '2026-09-07T12:00:00.000Z',
        updatedAt: '2026-09-07T12:00:20.000Z',
        startedAt: '2026-09-07T12:00:00.000Z',
        finishedAt: '2026-09-07T12:00:20.000Z',
        starred: false,
        status: 'failed',
        source: 'listen',
        visibility: 'private',
        folderId: null,
        locked: false,
        discarded: false,
      }}
    />,
  );
  const tree = JSON.stringify(renderer.toJSON());
  expect(tree).toContain('Conversation title unavailable');
  expect(tree).toContain('Failed');
  const plain = render(
    <ProjectionRow
      item={{
        kind: 'conversation',
        id: 'chat:chat-main',
        title: 'Hello',
        summary: 'Later turn',
        searchableText: 'Hello\nLater turn',
        createdAt: '2026-09-07T12:00:00.000Z',
        updatedAt: '2026-09-07T12:00:20.000Z',
        startedAt: '2026-09-07T12:00:00.000Z',
        finishedAt: null,
        starred: false,
        status: 'in_progress',
        source: 'chat',
        visibility: 'private',
        folderId: null,
        locked: false,
        discarded: false,
      }}
    />,
  );
  const plainTree = JSON.stringify(plain.toJSON());
  expect(plainTree).toContain('Hello');
  expect(plainTree).not.toContain('Failed');
  expect(plainTree).not.toContain('In progress');
});

test('wide Home search completed tasks keep GET due dates instead of Completed-only', () => {
  const dueAt = 1786000000;
  const expected = `Completed · ${new Date(dueAt * 1000).toLocaleDateString(
    undefined,
    {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      timeZone: 'UTC',
    },
  )}`;
  const renderer = render(
    <ProjectionRow
      item={{
        kind: 'task',
        id: 'task-completed-home-search',
        title: 'Prepare launch notes',
        summary: 'Completed',
        searchableText: 'Prepare launch notes',
        completed: true,
        completedAt: dueAt,
        dueAt,
        owner: null,
        source: 'assistant',
        provenance: [],
        sortOrder: 1,
        indentLevel: 0,
        createdAt: 1785900000,
        updatedAt: 1785900100,
        revision: null,
      }}
    />,
  );
  const tree = JSON.stringify(renderer.toJSON());
  expect(tree).toContain('Prepare launch notes');
  expect(tree).toContain(expected);
  expect(tree).not.toContain('"Completed"');
});
