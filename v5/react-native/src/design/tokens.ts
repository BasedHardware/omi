// Omi design language ("Omi Ink") — the one token source for v5 on every
// surface. Rationale and rules: docs/design-language.md.
//
// Lineage: the shipping Mac app's Ink system (neutral ink on glass, hierarchy
// from ink transparency, colour only for state) and the shipping mobile app's
// OmiTokens (iOS grouped greys, iOS text ramp). Values are inspired by both,
// not copied: v5 is one system with a desktop and a mobile density.

export type OmiScheme = 'light' | 'dark';
export type OmiDensity = 'desktop' | 'mobile';

/** Ink at a fixed transparency. Hierarchy is ink weight, never hue. */
const inkAt = (rgb: string, alpha: number) => `rgba(${rgb}, ${alpha})`;

const LIGHT_INK = '22, 23, 21';
const DARK_INK = '244, 245, 242';

export type OmiPalette = {
  /** Opaque page background when there is no glass (mobile, reduced transparency). */
  canvas: string;
  /** Raised opaque surfaces: cards, sheets, grouped settings. */
  surface: string;
  /** Controls sitting on a surface (fields, segmented tracks). */
  surfaceRaised: string;
  /** Pressed / selected opaque surface. */
  surfacePressed: string;
  /** Primary reading ink. */
  ink: string;
  /** Secondary ink: descriptions, metadata. Safe on glass. */
  inkSecondary: string;
  /** Tertiary ink: timestamps, hints. Opaque surfaces only, never on glass. */
  inkTertiary: string;
  /** Disabled labels. */
  inkDisabled: string;
  /** Text/icon drawn on an ink fill (primary buttons, send). */
  onInk: string;
  /** Rules between blocks. */
  separator: string;
  /** Control outlines (secondary buttons, fields). */
  hairline: string;
  /** Row fill on hover / cards on glass. Rows are clear at rest. */
  fill: string;
  /** Pressed fill. */
  fillPressed: string;
  /** Selected row / active chip. Selection is ink, never accent. */
  fillSelected: string;
  /** The one actionable link on a surface. Never selection. */
  link: string;
  /** Errors and destructive actions: the only place the app raises its voice. */
  danger: string;
  /** Live / recording / connected. */
  live: string;
  /** Needs attention (e.g. waiting for audio, low battery). */
  warning: string;
  /** Status-tinted surfaces (15%) for inline notices. */
  dangerSurface: string;
  liveSurface: string;
  /** Scrim behind modal overlays. */
  scrim: string;
};

const light: OmiPalette = {
  canvas: '#F2F2F4',
  surface: '#FFFFFF',
  surfaceRaised: '#ECECEE',
  surfacePressed: '#DDDDE0',
  ink: inkAt(LIGHT_INK, 1),
  inkSecondary: inkAt(LIGHT_INK, 0.72),
  inkTertiary: inkAt(LIGHT_INK, 0.56),
  inkDisabled: inkAt(LIGHT_INK, 0.32),
  onInk: '#FFFFFF',
  separator: inkAt(LIGHT_INK, 0.1),
  hairline: inkAt(LIGHT_INK, 0.2),
  fill: inkAt(LIGHT_INK, 0.045),
  fillPressed: inkAt(LIGHT_INK, 0.07),
  fillSelected: inkAt(LIGHT_INK, 0.09),
  link: '#0A66D6',
  danger: '#D70015',
  live: '#248A3D',
  warning: '#C35F00',
  dangerSurface: 'rgba(215, 0, 21, 0.10)',
  liveSurface: 'rgba(36, 138, 61, 0.12)',
  scrim: 'rgba(22, 23, 21, 0.28)',
};

const dark: OmiPalette = {
  canvas: '#000000',
  surface: '#1C1C1E',
  surfaceRaised: '#2C2C2E',
  surfacePressed: '#3A3A3C',
  ink: inkAt(DARK_INK, 1),
  inkSecondary: inkAt(DARK_INK, 0.7),
  inkTertiary: inkAt(DARK_INK, 0.52),
  inkDisabled: inkAt(DARK_INK, 0.3),
  onInk: '#111111',
  separator: inkAt(DARK_INK, 0.1),
  hairline: inkAt(DARK_INK, 0.22),
  fill: inkAt(DARK_INK, 0.06),
  fillPressed: inkAt(DARK_INK, 0.1),
  fillSelected: inkAt(DARK_INK, 0.14),
  link: '#4DA3FF',
  danger: '#FF453A',
  live: '#30D158',
  warning: '#FF9F0A',
  dangerSurface: 'rgba(255, 69, 58, 0.15)',
  liveSurface: 'rgba(48, 209, 88, 0.15)',
  scrim: 'rgba(0, 0, 0, 0.5)',
};

export const omiPalettes: Record<OmiScheme, OmiPalette> = {light, dark};

type TextStyleToken = {
  fontSize: number;
  lineHeight: number;
  fontWeight: '400' | '500' | '600' | '700';
  letterSpacing?: number;
};

export type OmiTypeRamp = {
  /** Badges, dense timestamps. */
  caption: TextStyleToken;
  /** Secondary lines, metadata, section labels. */
  footnote: TextStyleToken;
  /** Descriptions, search text. */
  subhead: TextStyleToken;
  /** Row titles and reading text. */
  body: TextStyleToken;
  /** Emphasised row titles, sheet and panel titles. */
  headline: TextStyleToken;
  /** Section headers. */
  title: TextStyleToken;
  /** At most one per screen. */
  display: TextStyleToken;
};

// Desktop is denser than mobile (macOS body is 13, iOS body is 17); the roles
// are the same so a component styles by role, never by number.
const desktopType: OmiTypeRamp = {
  caption: {fontSize: 11, lineHeight: 14, fontWeight: '500'},
  footnote: {fontSize: 12, lineHeight: 16, fontWeight: '400'},
  subhead: {fontSize: 13, lineHeight: 18, fontWeight: '400'},
  body: {fontSize: 14, lineHeight: 20, fontWeight: '400', letterSpacing: -0.1},
  headline: {
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '600',
    letterSpacing: -0.1,
  },
  title: {fontSize: 20, lineHeight: 26, fontWeight: '600', letterSpacing: -0.4},
  display: {
    fontSize: 28,
    lineHeight: 34,
    fontWeight: '600',
    letterSpacing: -0.8,
  },
};

const mobileType: OmiTypeRamp = {
  caption: {fontSize: 12, lineHeight: 16, fontWeight: '500'},
  footnote: {fontSize: 13, lineHeight: 18, fontWeight: '400'},
  subhead: {fontSize: 15, lineHeight: 20, fontWeight: '400'},
  body: {fontSize: 17, lineHeight: 22, fontWeight: '400', letterSpacing: -0.2},
  headline: {
    fontSize: 17,
    lineHeight: 22,
    fontWeight: '600',
    letterSpacing: -0.2,
  },
  title: {fontSize: 22, lineHeight: 28, fontWeight: '600', letterSpacing: -0.4},
  display: {
    fontSize: 30,
    lineHeight: 36,
    fontWeight: '700',
    letterSpacing: -0.8,
  },
};

export const omiType: Record<OmiDensity, OmiTypeRamp> = {
  desktop: desktopType,
  mobile: mobileType,
};

/** 4-pt spacing scale shared by every surface. */
export const omiSpace = {
  xxs: 2,
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 24,
  section: 32,
  page: 40,
} as const;

/**
 * Radii. Glass panels and cards share one radius; controls are capsules.
 * Rows and fields are softer rectangles.
 */
export const omiRadius = {
  badge: 6,
  chip: 11,
  row: 12,
  field: 13,
  sheet: 20,
  card: 22,
  pill: 999,
} as const;

/** Control heights. Every hit target is at least 44 pt on mobile. */
export const omiSize: Record<
  OmiDensity,
  {
    control: number;
    controlCompact: number;
    hitTarget: number;
    icon: number;
    iconSmall: number;
  }
> = {
  desktop: {
    control: 32,
    controlCompact: 26,
    hitTarget: 28,
    icon: 18,
    iconSmall: 15,
  },
  mobile: {
    control: 48,
    controlCompact: 36,
    hitTarget: 44,
    icon: 22,
    iconSmall: 18,
  },
};

/**
 * Motion. Colour-only feedback on press (no scale bounce); movement is for
 * surfaces arriving or leaving. All durations are 0 under Reduce Motion.
 */
export const omiMotion = {
  quick: 120,
  standard: 240,
  emphasized: 350,
  pressedOpacity: 0.82,
} as const;

/** Reading widths so text never runs the full window. */
export const omiLayout = {
  readingColumn: 640,
  listColumn: 720,
  chatColumn: 680,
  pageGutter: {desktop: 24, mobile: 16},
} as const;

export type OmiTheme = {
  scheme: OmiScheme;
  density: OmiDensity;
  color: OmiPalette;
  type: OmiTypeRamp;
  space: typeof omiSpace;
  radius: typeof omiRadius;
  size: (typeof omiSize)[OmiDensity];
  motion: typeof omiMotion;
  layout: typeof omiLayout;
};

export function omiTheme(scheme: OmiScheme, density: OmiDensity): OmiTheme {
  return {
    scheme,
    density,
    color: omiPalettes[scheme],
    type: omiType[density],
    space: omiSpace,
    radius: omiRadius,
    size: omiSize[density],
    motion: omiMotion,
    layout: omiLayout,
  };
}
