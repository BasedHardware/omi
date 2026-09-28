import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {StyleSheet, Text} from 'react-native';
import {
  OmiButton,
  OmiChip,
  OmiIconButton,
  OmiPageState,
  OmiRow,
  OmiThemeProvider,
  omiPalettes,
  omiTheme,
  useOmiTheme,
} from './index';

function luminance(color: string, over = '#ffffff'): number {
  const parse = (value: string) => {
    const rgba = value.match(/rgba?\(([^)]+)\)/);
    if (rgba) {
      const [r, g, b, a = '1'] = rgba[1].split(',').map(part => part.trim());
      return [Number(r), Number(g), Number(b), Number(a)];
    }
    const hex = value.replace('#', '');
    return [0, 2, 4].map(i => parseInt(hex.slice(i, i + 2), 16)).concat(1);
  };
  const [r, g, b, a] = parse(color);
  const [br, bg, bb] = parse(over);
  const mix = (c: number, base: number) => (c * a + base * (1 - a)) / 255;
  const channel = (c: number) =>
    c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  return (
    0.2126 * channel(mix(r, br)) +
    0.7152 * channel(mix(g, bg)) +
    0.0722 * channel(mix(b, bb))
  );
}

function contrast(fg: string, bg: string): number {
  const a = luminance(fg, bg);
  const b = luminance(bg);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

function render(
  element: React.ReactElement,
  scheme: 'light' | 'dark' = 'light',
) {
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <OmiThemeProvider scheme={scheme} density="desktop">
        {element}
      </OmiThemeProvider>,
    );
  });
  return renderer;
}

// MaterialIcon renders its glyph as Text in the private-use area; skip it.
const texts = (renderer: ReactTestRenderer.ReactTestRenderer) =>
  renderer.root
    .findAllByType(Text)
    .map(node => node.props.children)
    .filter(
      child => typeof child !== 'string' || !/^[\uE000-\uF8FF]$/u.test(child),
    );

describe('Omi tokens', () => {
  test.each(['light', 'dark'] as const)(
    '%s ink hierarchy stays readable on its surfaces',
    scheme => {
      const palette = omiPalettes[scheme];
      for (const surface of [palette.canvas, palette.surface]) {
        expect(contrast(palette.ink, surface)).toBeGreaterThanOrEqual(12);
        expect(contrast(palette.inkSecondary, surface)).toBeGreaterThanOrEqual(
          4.5,
        );
        expect(contrast(palette.inkTertiary, surface)).toBeGreaterThanOrEqual(
          3,
        );
      }
      expect(
        contrast(
          palette.onInk,
          palette.ink.replace(/, 1\)$/, ')').replace('rgba', 'rgb'),
        ),
      ).toBeGreaterThanOrEqual(12);
    },
  );

  test('the brand stays neutral: no purple state colour', () => {
    for (const palette of Object.values(omiPalettes)) {
      for (const value of [
        palette.link,
        palette.danger,
        palette.live,
        palette.warning,
      ]) {
        const hex = value.replace('#', '');
        const [r, g, b] = [0, 2, 4].map(i => parseInt(hex.slice(i, i + 2), 16));
        const purple = r > g + 40 && b > g + 40;
        expect(purple).toBe(false);
      }
    }
  });

  test('desktop is denser than mobile but keeps the same roles', () => {
    const desktop = omiTheme('light', 'desktop');
    const mobile = omiTheme('light', 'mobile');
    expect(Object.keys(desktop.type)).toEqual(Object.keys(mobile.type));
    expect(desktop.type.body.fontSize).toBeLessThan(mobile.type.body.fontSize);
    expect(mobile.size.hitTarget).toBeGreaterThanOrEqual(44);
  });

  test('outside a provider the theme falls back to dark mobile', () => {
    let seen: ReturnType<typeof useOmiTheme> | null = null;
    function Probe() {
      seen = useOmiTheme();
      return null;
    }
    act(() => {
      ReactTestRenderer.create(<Probe />);
    });
    expect(seen!.scheme).toBe('dark');
    expect(seen!.density).toBe('mobile');
  });
});

describe('Omi primitives', () => {
  test('primary button is an ink fill with the on-ink label, not an accent', () => {
    const onPress = jest.fn();
    const renderer = render(
      <OmiButton label="Save" variant="primary" onPress={onPress} />,
    );
    const button = renderer.root.findByProps({accessibilityRole: 'button'});
    const style = StyleSheet.flatten(
      typeof button.props.style === 'function'
        ? button.props.style({pressed: false})
        : button.props.style,
    );
    expect(style.backgroundColor).toBe(omiPalettes.light.ink);
    const label = renderer.root.findByType(Text);
    expect(StyleSheet.flatten(label.props.style).color).toBe(
      omiPalettes.light.onInk,
    );
    act(() => button.props.onPress());
    expect(onPress).toHaveBeenCalledTimes(1);
  });

  test('busy button keeps its accessible name and blocks presses', () => {
    const onPress = jest.fn();
    const renderer = render(<OmiButton label="Send" busy onPress={onPress} />);
    const button = renderer.root.findByProps({accessibilityRole: 'button'});
    expect(button.props.accessibilityLabel).toBe('Send');
    expect(button.props.accessibilityState).toEqual({
      disabled: true,
      busy: true,
    });
  });

  test('icon buttons are named for screen readers and tooltips', () => {
    const renderer = render(
      <OmiIconButton icon="settings" label="Settings" onPress={() => {}} />,
    );
    const button = renderer.root.findByProps({accessibilityRole: 'button'});
    expect(button.props.accessibilityLabel).toBe('Settings');
    expect(button.props.title).toBe('Settings');
  });

  test('selected chip reports selection', () => {
    const renderer = render(
      <OmiChip label="Tasks" selected onPress={() => {}} count={3} />,
    );
    const chip = renderer.root.findByProps({accessibilityRole: 'button'});
    expect(chip.props.accessibilityState).toEqual({selected: true});
    expect(texts(renderer)).toEqual(['Tasks', 3]);
  });

  test('rows render title, subtitle and meta in order', () => {
    const renderer = render(
      <OmiRow
        title="Weekly planning"
        subtitle="Priorities for the release"
        meta="Conversation · 9:00 AM"
        leadingIcon="chat_bubble"
      />,
    );
    expect(texts(renderer)).toEqual([
      'Weekly planning',
      'Priorities for the release',
      'Conversation · 9:00 AM',
    ]);
  });

  test('error state names what failed and offers Try Again', () => {
    const onRetry = jest.fn();
    const renderer = render(
      <OmiPageState
        kind="error"
        title="Couldn't Load Conversations"
        message="Check your connection."
        onRetry={onRetry}
      />,
      'dark',
    );
    expect(texts(renderer)).toEqual([
      "Couldn't Load Conversations",
      'Check your connection.',
      'Try Again',
    ]);
    act(() =>
      renderer.root
        .findByProps({accessibilityLabel: 'Try Again'})
        .props.onPress(),
    );
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  test('empty state has at most one action', () => {
    const renderer = render(
      <OmiPageState
        kind="empty"
        icon="checklist"
        title="No Tasks"
        message="Tasks from your conversations land here."
        action={{label: 'New Task', onPress: () => {}}}
      />,
    );
    expect(
      renderer.root.findAll(
        node =>
          typeof node.type === 'string' &&
          node.props.accessibilityRole === 'button',
      ),
    ).toHaveLength(1);
  });
});

test('small mobile controls keep a 44-pt touch target', () => {
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <OmiThemeProvider scheme="dark" density="mobile">
        <OmiChip label="Installed" selected={false} onPress={() => {}} />
      </OmiThemeProvider>,
    );
  });
  const chip = renderer.root.findByProps({accessibilityRole: 'button'});
  const theme = omiTheme('dark', 'mobile');
  expect(theme.size.controlCompact + chip.props.hitSlop.top * 2).toBe(
    theme.size.hitTarget,
  );
});
