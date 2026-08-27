export const color = {
  canvas: '#141414',
  chrome: 'rgba(18, 20, 19, 0.78)',
  chromeText: '#c8cbc6',
  danger: '#d9826f',
  focus: '#78bda5',
  input: 'rgba(255, 255, 255, 0.1)',
  inputPressed: 'rgba(255, 255, 255, 0.14)',
  menu: 'rgba(31, 35, 33, 0.98)',
  menuText: '#d7dad5',
  menuTextStrong: '#dfe2dd',
  line: '#303030',
  lineStrong: '#555555',
  primary: '#ffffff',
  primaryPressed: '#e4eee6',
  surface: '#1a1a1a',
  surfaceRaised: '#202020',
  text: '#f2f4f1',
  textInverse: '#141414',
  textMuted: '#b0b0b0',
  textSubtle: '#888888',
  transparent: 'transparent',
} as const;

export const radius = {
  none: 0,
  sm: 6,
  md: 10,
  lg: 14,
  xl: 26,
  pill: 999,
} as const;

export const space = {
  none: 0,
  xxs: 2,
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
  xxxl: 48,
} as const;

export const type = {
  caption: {fontSize: 12, lineHeight: 16, fontWeight: '500' as const},
  label: {fontSize: 13, lineHeight: 18, fontWeight: '600' as const},
  body: {fontSize: 14, lineHeight: 20, fontWeight: '400' as const},
  title: {fontSize: 18, lineHeight: 24, fontWeight: '700' as const},
  display: {fontSize: 28, lineHeight: 34, fontWeight: '700' as const},
} as const;

export const border = {
  width: 1,
} as const;

export const icon = {
  strokeWidth: 2,
} as const;

export const opacity = {
  disabled: 0.48,
  pressed: 0.78,
} as const;

export const layout = {
  grow: 1,
} as const;

export const size = {
  ask: 38,
  askCompact: 26,
  content: 560,
  controlCompact: 30,
  control: 36,
  controlLarge: 44,
  iconSmall: 14,
  icon: 18,
  iconLarge: 20,
  iconChrome: 17,
  searchDock: 52,
  searchDockCompact: 60,
  searchMax: 680,
  sheet: 224,
  sheetTop: 60,
  toolbar: 38,
} as const;

export const tokens = {
  border,
  color,
  icon,
  layout,
  opacity,
  radius,
  size,
  space,
  type,
} as const;
