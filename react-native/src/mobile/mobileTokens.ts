export const mobileColor = {
  background: '#000000',
  surface: '#1d1d23',
  surfaceRaised: '#25252d',
  surfaceQuiet: '#111114',
  border: '#34343d',
  text: '#f7f7f8',
  textMuted: '#aaaab2',
  textSubtle: '#74747d',
  accent: '#ffffff',
  recording: '#ff5a62',
  connected: '#00ed35',
  warning: '#f0b56d',
} as const;

export const mobileSpace = {
  xs: 6,
  sm: 10,
  md: 16,
  lg: 20,
  xl: 28,
  xxl: 36,
} as const;

export const mobileRadius = {
  sm: 14,
  md: 22,
  lg: 30,
  round: 999,
} as const;

export const mobileType = {
  caption: {fontSize: 13, lineHeight: 18, fontWeight: '500' as const},
  body: {fontSize: 17, lineHeight: 24, fontWeight: '400' as const},
  title: {fontSize: 22, lineHeight: 28, fontWeight: '600' as const},
} as const;
