import {desktopSystemFontFamily} from './desktopChrome';

export const desktopTokens = {
  color: {
    ink: '#242622',
    inkMuted: '#666a62',
    inkFaint: '#777b72',
    glass: 'transparent',
    glassStrong: 'rgba(255, 255, 255, 0.36)',
    glassQuiet: 'rgba(30, 40, 50, 0.035)',
    glassSelected: 'rgba(30, 40, 50, 0.09)',
    line: 'rgba(30, 40, 50, 0.10)',
    lineStrong: 'rgba(0, 0, 0, 0.22)',
    dark: '#242622',
    white: '#ffffff',
    blue: '#007aff',
    red: '#ff3b30',
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
