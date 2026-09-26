import {desktopSystemFontFamily} from './desktopChrome';

// Light-on-dark glass palette. The window material is the system HUD glass
// (dark, behind-window vibrancy), so ink stays light for readable contrast
// regardless of what the window floats over.
export const desktopTokens = {
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
} as const;
