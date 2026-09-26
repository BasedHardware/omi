import {desktopSystemFontFamily} from './desktopChrome';

export type DesktopThemeName = 'dark' | 'light';

// The dark palette keeps the original light-on-dark HUD glass look: the
// window material is dark behind-window vibrancy, so ink stays light for
// readable contrast regardless of what the window floats over.
const dark = {
  color: {
    ink: '#F2F4EF',
    inkMuted: 'rgba(242, 244, 239, 0.62)',
    inkFaint: 'rgba(242, 244, 239, 0.45)',
    glass: 'transparent',
    glassStrong: 'rgba(255, 255, 255, 0.14)',
    glassQuiet: 'rgba(255, 255, 255, 0.05)',
    glassSelected: 'rgba(255, 255, 255, 0.16)',
    line: 'rgba(255, 255, 255, 0.10)',
    lineStrong: 'rgba(255, 255, 255, 0.24)',
    dark: '#242622',
    white: '#ffffff',
    blue: '#0a84ff',
    red: '#ff453a',
  },
  radius: {window: 24, panel: 22, control: 18, chip: 14},
  space: {xs: 6, sm: 8, md: 12, lg: 16, xl: 24},
  type: {
    nav: 13,
    search: 15,
    title: 16,
    body: 14,
    meta: 12,
    caption: 12,
    hero: 17,
  },
  font: desktopSystemFontFamily,
};

// The light palette flips to dark ink over the light glass material applied
// natively by OmiGlassPanelView when the appearance preference is 'light'.
const light = {
  color: {
    ink: '#1D1F1B',
    inkMuted: 'rgba(29, 31, 27, 0.62)',
    inkFaint: 'rgba(29, 31, 27, 0.45)',
    glass: 'transparent',
    glassStrong: 'rgba(29, 31, 27, 0.08)',
    glassQuiet: 'rgba(29, 31, 27, 0.04)',
    glassSelected: 'rgba(29, 31, 27, 0.10)',
    line: 'rgba(29, 31, 27, 0.12)',
    lineStrong: 'rgba(29, 31, 27, 0.26)',
    // Kept under the historical name so surface styles need no branching.
    dark: '#F4F5F1',
    white: '#ffffff',
    blue: '#0066d6',
    red: '#d70015',
  },
  radius: dark.radius,
  space: dark.space,
  type: dark.type,
  font: dark.font,
};

export type DesktopTokens = {
  color: {
    ink: string;
    inkMuted: string;
    inkFaint: string;
    glass: string;
    glassStrong: string;
    glassQuiet: string;
    glassSelected: string;
    line: string;
    lineStrong: string;
    dark: string;
    white: string;
    blue: string;
    red: string;
  };
  radius: {window: number; panel: number; control: number; chip: number};
  space: {xs: number; sm: number; md: number; lg: number; xl: number};
  type: {
    nav: number;
    search: number;
    title: number;
    body: number;
    meta: number;
    caption: number;
    hero: number;
  };
  font: string;
};

export const darkDesktopTokens: DesktopTokens = dark;
export const lightDesktopTokens: DesktopTokens = light;

export const desktopThemeTokens: Record<DesktopThemeName, DesktopTokens> = {
  dark: dark,
  light: light,
};

// Default export shape kept for every existing import: the dark palette.
export const desktopTokens = darkDesktopTokens;
