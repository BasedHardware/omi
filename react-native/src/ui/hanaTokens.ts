// EXPERIMENT — Hana-inspired token treatment. Do not wire into production.
//
// Applies the alpha-based label/separator structure observed in the Hana
// Interface design tokens (https://hana-interface.vercel.app, reviewed in
// thread T-01a0aadf) to V5's existing token modules, without changing layout,
// materials, interaction defaults, or any component file.
//
// @hana-ui/react itself is NOT published on npm (registry E404, verified
// 2026-09-19); the `hana-ui` package is an unrelated anime-style UIKit. This
// file is therefore an original treatment of V5's own tokens: the structure
// (label alpha hierarchy + separator alphas) is Hana-inspired, while every hue
// is derived from V5's existing green-neutral bases — no purple anywhere.
//
// Activation is preview-only: pwa/src/hanaPreviewTokens.ts applies these
// overrides before component styles resolve when the design preview is opened
// with ?tokens=hana. Without that parameter nothing changes.
import {tokens} from './tokens';
import {desktopTokens} from '../desktop/tokens';
import {mobileColor} from '../mobile/mobileTokens';

type ColorUpdates = Record<string, string>;

// Functional secondary text uses Hana's stronger contrast companions so it
// stays WCAG AA (>= 4.5:1) over the lightest/warkest surfaces it composites
// onto. Low alpha is reserved for decorative separators and disabled states.
//
// Shared ui chrome (dark), over canvas #141414 —
// muted 60% (~6.4:1), subtle 50% (~4.9:1), separator white 16%, strong 28%.
const app: ColorUpdates = {
  textMuted: 'rgba(242, 244, 241, 0.6)',
  textSubtle: 'rgba(242, 244, 241, 0.5)',
  line: 'rgba(255, 255, 255, 0.16)',
  lineStrong: 'rgba(255, 255, 255, 0.28)',
};

// Desktop light, over glass ~#e9ece8 and cards ~#f0f2ee —
// muted 72% (~5.3:1), faint 66% (~4.9:1), separator 12% (decorative).
const desktop: ColorUpdates = {
  inkMuted: 'rgba(36, 38, 34, 0.72)',
  inkFaint: 'rgba(36, 38, 34, 0.66)',
  line: 'rgba(36, 38, 34, 0.12)',
};

// Mobile dark, over canvas #0f0f0f and cards ~#1a1a1a —
// muted 60% (~7:1), subtle 50% (~5:1), border/separator 16% (decorative).
const mobile: ColorUpdates = {
  textMuted: 'rgba(255, 255, 255, 0.6)',
  textSubtle: 'rgba(255, 255, 255, 0.5)',
  border: 'rgba(255, 255, 255, 0.16)',
};

export const hanaTokenOverrides = {app, desktop, mobile} as const;

export function applyHanaTokens(): void {
  Object.assign(tokens.color, hanaTokenOverrides.app);
  Object.assign(desktopTokens.color, hanaTokenOverrides.desktop);
  Object.assign(mobileColor, hanaTokenOverrides.mobile);
}
