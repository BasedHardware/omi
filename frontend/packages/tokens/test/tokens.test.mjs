import test from "node:test";
import assert from "node:assert/strict";
import { DATE_PRESENTATION_POLICY, getTheme, SEMANTIC_TOKENS, themeNameFor, TYPOGRAPHY_CONTENT_POLICY, typographyFamilyStack } from "../dist/index.js";

test("exposes platform geometry in explicit light and dark modes", () => {
  assert.deepEqual(Object.keys(SEMANTIC_TOKENS), ["mobileDark", "mobileLight", "desktopLightGlass", "desktopDarkGlass"]);
  assert.equal(getTheme("mobileDark").colors.surface.raised, "#1F1F25");
  assert.equal(getTheme("mobileLight").interaction.minTapTarget, 44);
  assert.equal(getTheme("desktopLightGlass").glass.material, "hudWindow");
  assert.equal(getTheme("desktopDarkGlass").glass.material, "hudWindow");
  assert.equal(themeNameFor("mobile", "dark"), "mobileDark");
  assert.equal(themeNameFor("mobile", "light"), "mobileLight");
  assert.equal(themeNameFor("desktop", "dark"), "desktopDarkGlass");
  assert.equal(themeNameFor("desktop", "light"), "desktopLightGlass");
});

test("does not promote the unresolved purple screenshot accent", () => {
  const serialized = JSON.stringify(SEMANTIC_TOKENS).toLowerCase();
  assert.equal(serialized.includes("purple"), false);
  assert.equal(serialized.includes("#7b5cff"), false);
  assert.equal(serialized.includes("#613cb1"), false);
});

test("keeps platform interaction targets in logical points", () => {
  // red-proof: dropping the 44-point ratchet must fail this assertion.
  for (const theme of Object.values(SEMANTIC_TOKENS)) {
    assert.ok(theme.interaction.minTapTarget >= 44);
    assert.ok(theme.interaction.focusRingWidth > 0);
    assert.ok(theme.interaction.selectedBorderWidth >= theme.interaction.focusRingWidth);
    assert.ok(theme.interaction.disabledOpacity > 0 && theme.interaction.disabledOpacity < 1);
  }
});

test("ships a complete visual-state token contract without an unbundled font", () => {
  // red-proof: reintroducing the unshipped Open Runde family, omitting the code
  // role, or collapsing the state timing ladder must fail here.
  const serialized = JSON.stringify(SEMANTIC_TOKENS).toLowerCase();
  assert.equal(serialized.includes("open runde"), false);
  assert.equal(serialized.includes("openrunde"), false);
  for (const theme of Object.values(SEMANTIC_TOKENS)) {
    assert.deepEqual(Object.keys(theme.motion.duration), ["instant", "fast", "standard", "deliberate"]);
    assert.equal(theme.motion.duration.instant, 0);
    assert.ok(theme.motion.duration.fast > 0);
    assert.ok(theme.motion.duration.standard > theme.motion.duration.fast);
    assert.ok(theme.motion.duration.deliberate > theme.motion.duration.standard);
    assert.equal(theme.typography.code.family, "mono");
    assert.equal(theme.typography.meta.family, "system");
    assert.ok(theme.layout.contentWidth.compact < theme.layout.contentWidth.regular);
    assert.ok(theme.layout.contentWidth.regular < theme.layout.contentWidth.wide);
    assert.ok(theme.layout.readableMeasure <= theme.layout.contentWidth.regular);
    assert.ok(theme.layout.rowMinHeight >= 44);
    assert.deepEqual(Object.keys(theme.shadows), ["card", "floating", "overlay"]);
  }
  assert.match(typographyFamilyStack("system"), /-apple-system/);
  assert.match(typographyFamilyStack("rounded"), /ui-rounded/);
  assert.match(typographyFamilyStack("mono"), /ui-monospace/);
});

test("defines one executable content role, measure, truncation, and date-granularity matrix", () => {
  assert.deepEqual(Object.keys(TYPOGRAPHY_CONTENT_POLICY), ["display", "title", "heading", "body", "row", "label", "meta", "button", "code"]);
  assert.deepEqual(TYPOGRAPHY_CONTENT_POLICY.body, { measureCh: 68, overflow: "wrap", maxLines: null });
  assert.deepEqual(TYPOGRAPHY_CONTENT_POLICY.meta, { measureCh: 44, overflow: "single-line-ellipsis", maxLines: 1 });
  assert.deepEqual(TYPOGRAPHY_CONTENT_POLICY.code, { measureCh: 96, overflow: "scroll", maxLines: null });
  assert.deepEqual(DATE_PRESENTATION_POLICY, {
    primary: "localized-medium-date",
    secondary: "localized-medium-date-short-time",
    exactTimePlacement: "secondary-detail",
  });
  for (const theme of Object.values(SEMANTIC_TOKENS)) {
    assert.deepEqual(Object.keys(theme.typography), Object.keys(TYPOGRAPHY_CONTENT_POLICY));
  }
});

function parseColor(value) {
  if (value.startsWith("#")) {
    return [1, 3, 5].map((start) => Number.parseInt(value.slice(start, start + 2), 16) / 255).concat(1);
  }
  const match = value.match(/^rgba?\(([^)]+)\)$/);
  assert.ok(match, `unsupported test color ${value}`);
  const channels = match[1].split(",").map((part) => Number(part.trim()));
  return channels.slice(0, 3).map((channel) => channel / 255).concat(channels[3] ?? 1);
}

function composite(foreground, background) {
  return foreground.slice(0, 3).map((channel, index) => channel * foreground[3] + background[index] * (1 - foreground[3]));
}

function luminance(color) {
  return color.slice(0, 3)
    .map((channel) => channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4)
    .reduce((sum, channel, index) => sum + channel * [0.2126, 0.7152, 0.0722][index], 0);
}

function contrastRatio(foreground, background) {
  const lighter = Math.max(luminance(foreground), luminance(background));
  const darker = Math.min(luminance(foreground), luminance(background));
  return (lighter + 0.05) / (darker + 0.05);
}

test("semantic text and control colors carry a machine-measured WCAG AA receipt", () => {
  for (const [name, theme] of Object.entries(SEMANTIC_TOKENS)) {
    const canvas = parseColor(theme.colors.surface.canvas);
    for (const surfaceName of ["canvas", "raised", "elevated"]) {
      const rawSurface = parseColor(theme.colors.surface[surfaceName]);
      const surface = surfaceName === "canvas" ? rawSurface.slice(0, 3) : composite(rawSurface, canvas);
      for (const contentName of ["primary", "secondary", "tertiary"]) {
        const content = composite(parseColor(theme.colors.content[contentName]), surface.concat(1));
        assert.ok(contrastRatio(content, surface) >= 4.5, `${name}.${contentName} meets AA on ${surfaceName}`);
      }
      for (const semanticName of ["accent", "danger", "success", "warning"]) {
        const semantic = composite(parseColor(theme.colors[semanticName]), surface.concat(1));
        assert.ok(contrastRatio(semantic, surface) >= 4.5, `${name}.${semanticName} meets AA when used as text on ${surfaceName}`);
      }
      const focus = composite(parseColor(theme.colors.focus), surface.concat(1));
      assert.ok(contrastRatio(focus, surface) >= 3, `${name}.focus remains a visible non-text boundary on ${surfaceName}`);
    }
  }
});
