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
  homeSearchPhaseCopy,
  savedDataEmptyTitle,
} from './ReadStatus';
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
    'taskNotice ===\n                                        desktopBackendUnavailableCopy',
  );
  expect(orchestrator).toContain('<OutcomeStatus');
  expect(orchestrator).toContain('label="Tasks"');
  expect(orchestrator).toContain('outcome={readOutcomes.tasks}');
  expect(orchestrator).toContain('recapCoverageCopy=');
  expect(orchestrator).toContain('taskCoverageCopy=');
  expect(orchestrator).toContain("readStatusCopy(\n                'Recaps'");
  expect(orchestrator).toContain("readStatusCopy(\n                'Tasks'");
});
