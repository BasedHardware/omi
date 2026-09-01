export const mobileColor = {
  background: '#0f0f0f',
  surface: '#1a1a1a',
  surfaceRaised: '#1f1f25',
  surfaceQuiet: '#111114',
  border: '#35343b',
  text: '#ffffff',
  textMuted: '#b0b0b0',
  textSubtle: '#888888',
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
