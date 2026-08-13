/**
 * The shared semantic token contract.
 *
 * Values are intentionally platform-neutral strings/numbers. A host maps these
 * roles to CSS variables, SwiftUI colours, or Flutter colours; surfaces should
 * not import a platform theme directly. Four host/appearance combinations are
 * ratified: mobile and desktop, each in light and dark mode.
 */

export type ThemeName = "mobileDark" | "mobileLight" | "desktopLightGlass" | "desktopDarkGlass";
export type ColorMode = "light" | "dark";

export type ColorTokens = {
  surface: {
    canvas: string;
    raised: string;
    elevated: string;
    scrim: string;
  };
  content: {
    primary: string;
    secondary: string;
    tertiary: string;
    inverse: string;
  };
  accent: string;
  focus: string;
  border: string;
  danger: string;
  success: string;
  warning: string;
};

export type SpacingTokens = {
  none: number;
  xs: number;
  sm: number;
  md: number;
  lg: number;
  xl: number;
  xxl: number;
  xxxl: number;
  xxxxl: number;
};

export type RadiusTokens = {
  element: number;
  smallControl: number;
  control: number;
  section: number;
  card: number;
  window: number;
  circular: number;
};

export type TypographyRole = {
  /** Deliberate system fallbacks; no unshipped font name may enter a token. */
  family: "system" | "rounded" | "mono";
  size: number;
  weight: 400 | 500 | 600;
  lineHeight: number;
  tracking: number;
};

export function typographyFamilyStack(family: TypographyRole["family"]): string {
  switch (family) {
    case "rounded":
      return "ui-rounded, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
    case "mono":
      return "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace";
    case "system":
      return "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
  }
}

export type TypographyTokens = {
  display: TypographyRole;
  title: TypographyRole;
  heading: TypographyRole;
  body: TypographyRole;
  row: TypographyRole;
  label: TypographyRole;
  meta: TypographyRole;
  button: TypographyRole;
  code: TypographyRole;
};

export type TypographyContentPolicy = {
  readonly measureCh: number;
  readonly overflow: "wrap" | "single-line-ellipsis" | "scroll";
  readonly maxLines: number | null;
};

/**
 * Content behavior belongs to semantic type roles, not individual routes.
 * `measureCh` is a readable upper bound rather than a forced width. Labels and
 * metadata stay one line only in compact rows; body/title content wraps; code
 * remains horizontally inspectable instead of being silently truncated.
 */
export const TYPOGRAPHY_CONTENT_POLICY = Object.freeze({
  display: { measureCh: 32, overflow: "wrap", maxLines: 2 },
  title: { measureCh: 40, overflow: "wrap", maxLines: 2 },
  heading: { measureCh: 48, overflow: "wrap", maxLines: 3 },
  body: { measureCh: 68, overflow: "wrap", maxLines: null },
  row: { measureCh: 56, overflow: "single-line-ellipsis", maxLines: 1 },
  label: { measureCh: 32, overflow: "single-line-ellipsis", maxLines: 1 },
  meta: { measureCh: 44, overflow: "single-line-ellipsis", maxLines: 1 },
  button: { measureCh: 28, overflow: "wrap", maxLines: 2 },
  code: { measureCh: 96, overflow: "scroll", maxLines: null },
} satisfies Readonly<Record<keyof TypographyTokens, TypographyContentPolicy>>);

/** Locale-aware dates are human-readable first; exact time is secondary detail. */
export const DATE_PRESENTATION_POLICY = Object.freeze({
  primary: "localized-medium-date",
  secondary: "localized-medium-date-short-time",
  exactTimePlacement: "secondary-detail",
} as const);

export type MotionTokens = {
  duration: {
    instant: number;
    fast: number;
    standard: number;
    deliberate: number;
  };
  easing: {
    standard: string;
    emphasized: string;
  };
};

export type LayoutTokens = {
  contentWidth: {
    compact: number;
    regular: number;
    wide: number;
  };
  readableMeasure: number;
  rowMinHeight: number;
};

export type ShadowTokens = {
  card: string;
  floating: string;
  overlay: string;
};

export type GlassTokens = {
  material: "hudWindow" | "none";
  opacity: number;
  tintOpacity: number;
  scrimOpacity: number;
  edgeOpacity: number;
  reduceTransparencyMaterial: "solid" | "none";
};

/** Interaction dimensions are logical points; hosts map them to platform pixels. */
export type InteractionTokens = {
  minTapTarget: number;
  focusRingWidth: number;
  selectedBorderWidth: number;
  pressedOffset: number;
  disabledOpacity: number;
};

export type SemanticTheme = {
  name: ThemeName;
  colors: ColorTokens;
  spacing: SpacingTokens;
  radii: RadiusTokens;
  typography: TypographyTokens;
  motion: MotionTokens;
  layout: LayoutTokens;
  shadows: ShadowTokens;
  glass: GlassTokens;
  interaction: InteractionTokens;
};

const sharedMotion: MotionTokens = {
  duration: {
    instant: 0,
    fast: 120,
    standard: 180,
    deliberate: 260,
  },
  easing: {
    standard: "cubic-bezier(0.2, 0, 0, 1)",
    emphasized: "cubic-bezier(0.2, 0.8, 0.2, 1)",
  },
};

const sharedInteraction: InteractionTokens = {
  minTapTarget: 44,
  focusRingWidth: 2,
  selectedBorderWidth: 2,
  pressedOffset: 1,
  disabledOpacity: 0.46,
};

const mobileDark: SemanticTheme = {
  name: "mobileDark",
  colors: {
    // Grounded in app/lib/utils/ui_guidelines.dart: black, #1F1F25, #35343B.
    surface: {
      canvas: "#000000",
      raised: "#1F1F25",
      elevated: "#35343B",
      scrim: "rgba(0, 0, 0, 0.40)",
    },
    content: {
      primary: "#FFFFFF",
      secondary: "rgba(255, 255, 255, 0.80)",
      tertiary: "rgba(255, 255, 255, 0.60)",
      inverse: "#000000",
    },
    // The legacy guideline uses the platform blue accent; purple screenshot
    // pixels are intentionally not promoted to a token without a ratification.
    accent: "#66B2FF",
    focus: "#66B2FF",
    border: "rgba(255, 255, 255, 0.12)",
    danger: "#FF746C",
    success: "#5FD278",
    warning: "#F59E0B",
  },
  spacing: {
    none: 0,
    xs: 4,
    sm: 8,
    md: 12,
    lg: 16,
    xl: 24,
    xxl: 32,
    xxxl: 40,
    xxxxl: 48,
  },
  radii: {
    element: 6,
    smallControl: 8,
    control: 12,
    section: 16,
    card: 24,
    window: 24,
    circular: 999,
  },
  typography: {
    display: { family: "system", size: 34, weight: 600, lineHeight: 1.1, tracking: -1.19 },
    title: { family: "system", size: 28, weight: 600, lineHeight: 1.18, tracking: -0.84 },
    heading: { family: "system", size: 18, weight: 600, lineHeight: 1.25, tracking: 0 },
    body: { family: "system", size: 15, weight: 400, lineHeight: 1.4, tracking: 0 },
    row: { family: "system", size: 15, weight: 500, lineHeight: 1.4, tracking: 0 },
    label: { family: "system", size: 12, weight: 500, lineHeight: 1.2, tracking: 0 },
    meta: { family: "system", size: 12, weight: 400, lineHeight: 1.35, tracking: 0 },
    button: { family: "system", size: 15, weight: 600, lineHeight: 1.2, tracking: 0 },
    code: { family: "mono", size: 13, weight: 500, lineHeight: 1.4, tracking: 0 },
  },
  motion: sharedMotion,
  layout: {
    contentWidth: { compact: 320, regular: 680, wide: 920 },
    readableMeasure: 640,
    rowMinHeight: 52,
  },
  shadows: {
    card: "none",
    floating: "0 10px 30px rgba(0, 0, 0, 0.28)",
    overlay: "0 24px 64px rgba(0, 0, 0, 0.40)",
  },
  glass: {
    material: "none",
    opacity: 1,
    tintOpacity: 0,
    scrimOpacity: 0,
    edgeOpacity: 0,
    reduceTransparencyMaterial: "solid",
  },
  interaction: sharedInteraction,
};

/** Mobile keeps its established geometry in light mode; only semantic colour roles change. */
const mobileLight: SemanticTheme = {
  ...mobileDark,
  name: "mobileLight",
  colors: {
    surface: {
      canvas: "#F7F7F8",
      raised: "#FFFFFF",
      elevated: "#ECECF0",
      scrim: "rgba(0, 0, 0, 0.16)",
    },
    content: {
      primary: "#111216",
      secondary: "rgba(17, 18, 22, 0.74)",
      tertiary: "rgba(17, 18, 22, 0.60)",
      inverse: "#FFFFFF",
    },
    accent: "#005FCC",
    focus: "#005FCC",
    border: "rgba(17, 18, 22, 0.12)",
    danger: "#B42318",
    success: "#166A2F",
    warning: "#8A4300",
  },
  shadows: {
    card: "0 1px 2px rgba(17, 18, 22, 0.06)",
    floating: "0 12px 32px rgba(17, 18, 22, 0.16)",
    overlay: "0 24px 64px rgba(17, 18, 22, 0.22)",
  },
};

const desktopLightGlass: SemanticTheme = {
  name: "desktopLightGlass",
  colors: {
    // InkGlass is an aqua-pinned HUD material. These are semantic fallbacks for
    // web hosts; native hosts should map surface.raised to their HUD material.
    surface: {
      canvas: "#EAF3FB",
      raised: "rgba(255, 255, 255, 0.76)",
      elevated: "rgba(255, 255, 255, 0.88)",
      scrim: "rgba(0, 0, 0, 0.46)",
    },
    content: {
      primary: "#1B1F23",
      secondary: "rgba(27, 31, 35, 0.80)",
      tertiary: "rgba(27, 31, 35, 0.68)",
      inverse: "#FFFFFF",
    },
    accent: "#005FCC",
    focus: "#005FCC",
    border: "rgba(27, 31, 35, 0.06)",
    danger: "#B42318",
    success: "#166A2F",
    warning: "#8A4300",
  },
  spacing: {
    none: 0,
    xs: 2,
    sm: 6,
    md: 10,
    lg: 14,
    xl: 18,
    xxl: 24,
    xxxl: 32,
    xxxxl: 40,
  },
  radii: {
    element: 8,
    smallControl: 12,
    control: 16,
    section: 20,
    card: 24,
    window: 22,
    circular: 999,
  },
  typography: {
    display: { family: "rounded", size: 34, weight: 600, lineHeight: 1.1, tracking: -1.19 },
    title: { family: "rounded", size: 27, weight: 600, lineHeight: 1.18, tracking: -0.81 },
    heading: { family: "system", size: 20, weight: 600, lineHeight: 1.25, tracking: 0 },
    body: { family: "system", size: 17, weight: 400, lineHeight: 1.55, tracking: -0.17 },
    row: { family: "system", size: 15, weight: 500, lineHeight: 1.4, tracking: -0.15 },
    label: { family: "system", size: 12, weight: 500, lineHeight: 1.2, tracking: 0 },
    meta: { family: "system", size: 12, weight: 400, lineHeight: 1.35, tracking: 0 },
    button: { family: "system", size: 15, weight: 600, lineHeight: 1.2, tracking: 0 },
    code: { family: "mono", size: 13, weight: 500, lineHeight: 1.4, tracking: 0 },
  },
  motion: sharedMotion,
  layout: {
    contentWidth: { compact: 640, regular: 960, wide: 1180 },
    readableMeasure: 720,
    rowMinHeight: 48,
  },
  shadows: {
    card: "0 1px 2px rgba(27, 31, 35, 0.08)",
    floating: "0 14px 36px rgba(27, 31, 35, 0.16)",
    overlay: "0 28px 72px rgba(27, 31, 35, 0.22)",
  },
  glass: {
    material: "hudWindow",
    opacity: 0.588,
    tintOpacity: 0.909,
    scrimOpacity: 0.46,
    edgeOpacity: 0.06,
    reduceTransparencyMaterial: "solid",
  },
  interaction: sharedInteraction,
};

/** Desktop dark mode retains the glass geometry and interaction model of the Aqua default. */
const desktopDarkGlass: SemanticTheme = {
  ...desktopLightGlass,
  name: "desktopDarkGlass",
  colors: {
    surface: {
      canvas: "#0C1015",
      raised: "rgba(31, 35, 42, 0.82)",
      elevated: "rgba(48, 53, 62, 0.88)",
      scrim: "rgba(0, 0, 0, 0.52)",
    },
    content: {
      primary: "#F7F8FA",
      secondary: "rgba(247, 248, 250, 0.78)",
      tertiary: "rgba(247, 248, 250, 0.58)",
      inverse: "#111318",
    },
    accent: "#66B2FF",
    focus: "#66B2FF",
    border: "rgba(255, 255, 255, 0.11)",
    danger: "#FF746C",
    success: "#5FD278",
    warning: "#FF9F0A",
  },
  shadows: {
    card: "0 1px 2px rgba(0, 0, 0, 0.22)",
    floating: "0 14px 38px rgba(0, 0, 0, 0.34)",
    overlay: "0 30px 76px rgba(0, 0, 0, 0.48)",
  },
};

export const SEMANTIC_TOKENS = {
  mobileDark,
  mobileLight,
  desktopLightGlass,
  desktopDarkGlass,
} as const satisfies Record<ThemeName, SemanticTheme>;

export function themeNameFor(platform: "mobile" | "desktop", mode: ColorMode): ThemeName {
  if (platform === "mobile") return mode === "dark" ? "mobileDark" : "mobileLight";
  return mode === "dark" ? "desktopDarkGlass" : "desktopLightGlass";
}

export function getTheme(name: ThemeName): SemanticTheme {
  return SEMANTIC_TOKENS[name];
}
