import {desktopSystemFontFamily} from './desktopChrome';

export const desktopTokens = {
  color: {
    ink: 'rgba(0, 0, 0, 0.92)',
    onGlass: 'rgba(0, 0, 0, 0.92)',
    inkMuted: 'rgba(0, 0, 0, 0.80)',
    inkFaint: 'rgba(0, 0, 0, 0.55)',
    glass: 'transparent',
    glassStrong: 'rgba(255, 255, 255, 0.46)',
    glassQuiet: 'rgba(0, 0, 0, 0.045)',
    glassSelected: 'rgba(0, 0, 0, 0.085)',
    line: 'rgba(0, 0, 0, 0.06)',
    lineStrong: 'rgba(0, 0, 0, 0.22)',
    sheen: 'rgba(255, 255, 255, 0.50)',
    dark: 'rgba(0, 0, 0, 0.88)',
    white: '#ffffff',
    blue: '#007aff',
    red: '#ff3b30',
  },
  radius: {window: 24, panel: 22, control: 18, chip: 14},
  space: {xs: 6, sm: 8, md: 12, lg: 16, xl: 24},
  type: {
    nav: 11,
    search: 17,
    title: 15,
    body: 15,
    meta: 12,
    caption: 11,
    hero: 17,
  },
  font: desktopSystemFontFamily,
} as const;
