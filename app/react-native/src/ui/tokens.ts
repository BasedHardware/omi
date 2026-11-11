/**
 * Omi-aligned UI tokens for the React Native app.
 *
 * Mirrors the semantic palette and scales from Flutter's
 * `app/lib/ui/omi_tokens.dart` (dark baseline), adapted for RN/mobile.
 * New surfaces should prefer these tokens over hardcoded colors.
 */

export const OmiColors = {
  surface0: '#000000',
  surface1: '#1C1C1E',
  surface2: '#2C2C2E',
  surface3: '#3A3A3C',
  chipSurface: '#2C2C2E',
  messageSurface: '#1C1C1E',
  categorySurface: '#35343B',
  conversationCard: '#1F1F25',
  sourceBadgeSurface: '#2A2A31',
  border: '#3C3C43',
  textPrimary: '#FFFFFF',
  textSecondary: '#AEAEB2',
  textTertiary: '#8E8E93',
  textDisabled: '#636366',
  accent: '#FFFFFF',
  onAccent: '#000000',
  success: '#30D158',
  successSurface: 'rgba(48,209,88,0.15)',
  warning: '#FF9F0A',
  danger: '#FF453A',
  dangerSurface: 'rgba(255,69,58,0.15)',
} as const;

export const OmiType = {
  caption: { fontSize: 11, lineHeight: 14, fontWeight: '400' as const },
  footnote: { fontSize: 13, lineHeight: 18, fontWeight: '400' as const },
  subhead: { fontSize: 15, lineHeight: 20, fontWeight: '400' as const },
  callout: { fontSize: 16, lineHeight: 21, fontWeight: '400' as const },
  body: { fontSize: 17, lineHeight: 22, fontWeight: '400' as const },
  headline: { fontSize: 17, lineHeight: 22, fontWeight: '600' as const },
  title3: { fontSize: 20, lineHeight: 25, fontWeight: '600' as const },
  title2: { fontSize: 24, lineHeight: 30, fontWeight: '600' as const },
  title1: { fontSize: 28, lineHeight: 34, fontWeight: '700' as const },
  largeTitle: { fontSize: 34, lineHeight: 41, fontWeight: '700' as const },
} as const;

export const OmiRadius = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  pill: 999,
} as const;

export const OmiSpacing = {
  xxs: 4,
  xs: 8,
  sm: 12,
  md: 16,
  lg: 20,
  xl: 24,
  xxl: 32,
} as const;

export const OmiShadow = {
  card: {
    shadowColor: '#000',
    shadowOpacity: 0.25,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 6 },
    elevation: 4,
  },
} as const;
