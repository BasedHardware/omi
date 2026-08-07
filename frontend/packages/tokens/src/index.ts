/**
 * The shared semantic token contract.
 *
 * Values are intentionally platform-neutral strings/numbers. A host maps these
 * roles to CSS variables, SwiftUI colours, or Flutter colours; surfaces should
 * not import a platform theme directly. The two themes are the only ratified
 * production modes in Wave 0.
 */

export type ThemeName = "mobileDark" | "desktopLightGlass";

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
  family: "system" | "openRunde";
  size: number;
  weight: 400 | 500 | 600;
  lineHeight: number;
  tracking: number;
};

export type TypographyTokens = {
  display: TypographyRole;
  title: TypographyRole;
  heading: TypographyRole;
  body: TypographyRole;
  row: TypographyRole;
  label: TypographyRole;
  button: TypographyRole;
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
};

export type SemanticTheme = {
  name: ThemeName;
  colors: ColorTokens;
  spacing: SpacingTokens;
  radii: RadiusTokens;
  typography: TypographyTokens;
  glass: GlassTokens;
  interaction: InteractionTokens;
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
    accent: "#007AFF",
    focus: "#007AFF",
    border: "rgba(255, 255, 255, 0.12)",
    danger: "#B71C1C",
    success: "#2E7D32",
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
    button: { family: "system", size: 15, weight: 600, lineHeight: 1.2, tracking: 0 },
  },
  glass: {
    material: "none",
    opacity: 1,
    tintOpacity: 0,
    scrimOpacity: 0,
    edgeOpacity: 0,
    reduceTransparencyMaterial: "solid",
  },
  interaction: {
    minTapTarget: 44,
    focusRingWidth: 2,
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
    accent: "#007AFF",
    focus: "#007AFF",
    border: "rgba(27, 31, 35, 0.06)",
    danger: "#FF3B30",
    success: "#34C759",
    warning: "#FF9500",
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
    display: { family: "openRunde", size: 34, weight: 600, lineHeight: 1.1, tracking: -1.19 },
    title: { family: "openRunde", size: 27, weight: 600, lineHeight: 1.18, tracking: -0.81 },
    heading: { family: "system", size: 20, weight: 600, lineHeight: 1.25, tracking: 0 },
    body: { family: "system", size: 17, weight: 400, lineHeight: 1.55, tracking: -0.17 },
    row: { family: "system", size: 15, weight: 500, lineHeight: 1.4, tracking: -0.15 },
    label: { family: "system", size: 12, weight: 500, lineHeight: 1.2, tracking: 0 },
    button: { family: "system", size: 15, weight: 600, lineHeight: 1.2, tracking: 0 },
  },
  glass: {
    material: "hudWindow",
    opacity: 0.588,
    tintOpacity: 0.909,
    scrimOpacity: 0.46,
    edgeOpacity: 0.06,
    reduceTransparencyMaterial: "solid",
  },
  interaction: {
    minTapTarget: 44,
    focusRingWidth: 2,
  },
};

export const SEMANTIC_TOKENS = {
  mobileDark,
  desktopLightGlass,
} as const satisfies Record<ThemeName, SemanticTheme>;

export function getTheme(name: ThemeName): SemanticTheme {
  return SEMANTIC_TOKENS[name];
}
