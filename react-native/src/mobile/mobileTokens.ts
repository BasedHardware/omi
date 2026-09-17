export const mobileColor = {
  background: '#0f0f0f',
  surface: '#1a1a1a',
  surfaceRaised: '#252622',
  surfaceQuiet: '#151613',
  border: '#343630',
  text: '#ffffff',
  textMuted: '#b5b8af',
  textSubtle: '#92968b',
  accent: '#ffffff',
  recording: '#ff5a62',
  connected: '#10b981',
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
  sm: 12,
  md: 16,
  lg: 22,
  chip: 16,
  round: 18,
} as const;

export const mobileType = {
  caption: {fontSize: 13, lineHeight: 18, fontWeight: '500' as const},
  body: {fontSize: 17, lineHeight: 24, fontWeight: '400' as const},
  title: {fontSize: 22, lineHeight: 28, fontWeight: '600' as const},
} as const;
