import {tokens} from './tokens';
import {desktopTokens} from '../desktop/tokens';
import {mobileColor} from '../mobile/mobileTokens';
import {applyHanaTokens, hanaTokenOverrides} from './hanaTokens';

type Color = Record<string, string>;

function channels(value: string): [number, number, number, number] {
  const match = value.match(
    /^rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)(?:[,\s]+([\d.]+))?\s*\)$/,
  );
  if (match === null) {
    const hex = value.replace('#', '');
    return [
      parseInt(hex.slice(0, 2), 16),
      parseInt(hex.slice(2, 4), 16),
      parseInt(hex.slice(4, 6), 16),
      1,
    ];
  }
  return [
    Number(match[1]),
    Number(match[2]),
    Number(match[3]),
    match[4] === undefined ? 1 : Number(match[4]),
  ];
}

function luminance([r, g, b]: [number, number, number]): number {
  const linear = (channel: number) => {
    const c = channel / 255;
    return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b);
}

function compositeOver(
  value: string,
  background: [number, number, number],
): [number, number, number] {
  const [r, g, b, alpha] = channels(value);
  return [
    alpha * r + (1 - alpha) * background[0],
    alpha * g + (1 - alpha) * background[1],
    alpha * b + (1 - alpha) * background[2],
  ];
}

function contrast(a: string, background: [number, number, number]): number {
  const fg = luminance(compositeOver(a, background));
  const bg = luminance(background);
  const [lighter, darker] = fg > bg ? [fg, bg] : [bg, fg];
  return (lighter + 0.05) / (darker + 0.05);
}

// Representative surfaces each tier composites onto in practice.
const DESKTOP_BACKGROUNDS: Array<[number, number, number]> = [
  [233, 236, 232], // approximated glass over wallpaper
  [240, 242, 238], // card surface
];
const MOBILE_BACKGROUNDS: Array<[number, number, number]> = [
  [15, 15, 15], // canvas
  [26, 26, 26], // card surface
];
const APP_BACKGROUNDS: Array<[number, number, number]> = [
  [20, 20, 20], // canvas
];

// The Hana reference sample colors its hero with Color.purple; V5 must never
// drift into the violet band (INV-UI-1 spirit). Guard the experiment data.
function hueDegrees([r, g, b]: [number, number, number]): number {
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  if (max === min) {
    return 0;
  }
  const span = max - min;
  if (max === r) {
    return (60 * ((g - b) / span) + 360) % 360;
  }
  if (max === g) {
    return 60 * ((b - r) / span) + 120;
  }
  return 60 * ((r - g) / span) + 240;
}

describe('hanaTokenOverrides', () => {
  it('never introduces purple or violet hues', () => {
    for (const scheme of Object.values(hanaTokenOverrides)) {
      for (const value of Object.values(scheme)) {
        const [r, g, b] = channels(value);
        const saturation = Math.max(r, g, b) - Math.min(r, g, b);
        const hue = hueDegrees([r, g, b]);
        if (saturation > 24) {
          expect(hue).toBeLessThan(250);
        }
      }
    }
  });

  it('keeps the label hierarchy ordered (secondary > tertiary)', () => {
    expect(channels(hanaTokenOverrides.app.textMuted)[3]).toBeGreaterThan(
      channels(hanaTokenOverrides.app.textSubtle)[3],
    );
    expect(channels(hanaTokenOverrides.desktop.inkMuted)[3]).toBeGreaterThan(
      channels(hanaTokenOverrides.desktop.inkFaint)[3],
    );
    expect(channels(hanaTokenOverrides.mobile.textMuted)[3]).toBeGreaterThan(
      channels(hanaTokenOverrides.mobile.textSubtle)[3],
    );
  });

  it('meets WCAG AA (4.5:1) composited for functional small text tiers', () => {
    for (const background of DESKTOP_BACKGROUNDS) {
      expect(
        contrast(hanaTokenOverrides.desktop.inkMuted, background),
      ).toBeGreaterThanOrEqual(4.5);
      expect(
        contrast(hanaTokenOverrides.desktop.inkFaint, background),
      ).toBeGreaterThanOrEqual(4.5);
    }
    for (const background of MOBILE_BACKGROUNDS) {
      expect(
        contrast(hanaTokenOverrides.mobile.textMuted, background),
      ).toBeGreaterThanOrEqual(4.5);
      expect(
        contrast(hanaTokenOverrides.mobile.textSubtle, background),
      ).toBeGreaterThanOrEqual(4.5);
    }
    for (const background of APP_BACKGROUNDS) {
      expect(
        contrast(hanaTokenOverrides.app.textMuted, background),
      ).toBeGreaterThanOrEqual(4.5);
      expect(
        contrast(hanaTokenOverrides.app.textSubtle, background),
      ).toBeGreaterThanOrEqual(4.5);
    }
  });

  it('reserves low alpha for decorative separators only', () => {
    for (const value of [
      hanaTokenOverrides.app.line,
      hanaTokenOverrides.desktop.line,
      hanaTokenOverrides.mobile.border,
    ]) {
      expect(channels(value)[3]).toBeLessThanOrEqual(0.2);
    }
  });

  it('only overrides keys that exist on the live token modules', () => {
    for (const [scheme, updates] of Object.entries(hanaTokenOverrides)) {
      const target: Color =
        scheme === 'app'
          ? tokens.color
          : scheme === 'desktop'
          ? desktopTokens.color
          : mobileColor;
      for (const key of Object.keys(updates)) {
        expect(target).toHaveProperty(key);
      }
    }
  });

  it('applies to the live modules and can be restored', () => {
    const original = {
      app: {...tokens.color},
      desktop: {...desktopTokens.color},
      mobile: {...mobileColor},
    };
    applyHanaTokens();
    expect(tokens.color.textMuted).toBe(hanaTokenOverrides.app.textMuted);
    expect(desktopTokens.color.inkMuted).toBe(
      hanaTokenOverrides.desktop.inkMuted,
    );
    expect(mobileColor.textMuted).toBe(hanaTokenOverrides.mobile.textMuted);
    Object.assign(tokens.color, original.app);
    Object.assign(desktopTokens.color, original.desktop);
    Object.assign(mobileColor, original.mobile);
    expect(tokens.color.textMuted).toBe(original.app.textMuted);
  });
});
