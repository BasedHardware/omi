import {desktopSystemFontFamily} from './desktopChrome';

export const desktopTokens = {
  color: {
    ink: 'rgba(0, 0, 0, 0.92)',
    inkMuted: 'rgba(0, 0, 0, 0.64)',
    inkFaint: 'rgba(0, 0, 0, 0.45)',
    glass: 'transparent',
    glassStrong: 'rgba(255, 255, 255, 0.46)',
    glassQuiet: 'rgba(0, 0, 0, 0.045)',
    glassSelected: 'rgba(0, 0, 0, 0.085)',
    line: 'rgba(0, 0, 0, 0.06)',
    lineStrong: 'rgba(0, 0, 0, 0.22)',
    dark: 'rgba(0, 0, 0, 0.88)',
    white: '#ffffff',
    blue: '#007aff',
    red: '#ff3b30',
  },
  radius: {window: 24, panel: 22, control: 18, chip: 14},
  space: {xs: 6, sm: 8, md: 12, lg: 16, xl: 24},
  type: {
    nav: 12,
    search: 15,
    title: 14,
    body: 14,
    meta: 12,
    caption: 12,
    hero: 17,
  },
  font: desktopSystemFontFamily,
} as const;
