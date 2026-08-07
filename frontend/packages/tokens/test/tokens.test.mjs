import test from "node:test";
import assert from "node:assert/strict";
import { getTheme, SEMANTIC_TOKENS } from "../dist/index.js";

test("exposes both ratified production themes", () => {
  assert.deepEqual(Object.keys(SEMANTIC_TOKENS), ["mobileDark", "desktopLightGlass"]);
  assert.equal(getTheme("mobileDark").colors.surface.raised, "#1F1F25");
  assert.equal(getTheme("desktopLightGlass").glass.material, "hudWindow");
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
