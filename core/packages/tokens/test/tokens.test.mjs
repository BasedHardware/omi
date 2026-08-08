import test from "node:test";
import assert from "node:assert/strict";
import { getTheme, SEMANTIC_TOKENS, themeNameFor } from "../dist/index.js";

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
  }
});
