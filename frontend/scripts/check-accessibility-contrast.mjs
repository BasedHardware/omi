#!/usr/bin/env node
/**
 * Production contrast fence for *token pairs* — WCAG 2.2 AA numbers, not a
 * palette redesign. Text roles must keep 4.5:1 against canvas/raised/elevated
 * (translucent surfaces composited over canvas). Focus, as a non-text UI
 * boundary, must keep 3:1.
 *
 * Border, glass-over-wallpaper, and any pair that would need a new colour
 * value are out of scope: those need a ruling, not a gate.
 *
 * `src/dev/**` and `src/lab/**` are not production surfaces and are exempt.
 */
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = fileURLToPath(new URL("..", import.meta.url));
const TOKENS_DIST = join(ROOT, "packages/tokens/dist/index.js");
const TEXT_MIN = 4.5;
const NONTEXT_MIN = 3;

export function parseColor(value) {
  if (value.startsWith("#")) {
    const hex = value.length === 4
      ? `#${[...value.slice(1)].map((channel) => channel + channel).join("")}`
      : value;
    return [1, 3, 5].map((start) => Number.parseInt(hex.slice(start, start + 2), 16) / 255).concat(1);
  }
  const match = String(value).match(/^rgba?\(([^)]+)\)$/);
  if (!match) throw new Error(`unsupported color ${value}`);
  const channels = match[1].split(",").map((part) => Number(part.trim()));
  return channels.slice(0, 3).map((channel) => channel / 255).concat(channels[3] ?? 1);
}

export function composite(foreground, background) {
  const fg = foreground.length === 3 ? foreground.concat(1) : foreground;
  const bg = background.length === 3 ? background.concat(1) : background;
  return fg.slice(0, 3).map((channel, index) => channel * fg[3] + bg[index] * (1 - fg[3])).concat(1);
}

export function luminance(color) {
  return color.slice(0, 3)
    .map((channel) => (channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4))
    .reduce((sum, channel, index) => sum + channel * [0.2126, 0.7152, 0.0722][index], 0);
}

export function contrastRatio(foreground, background) {
  const lighter = Math.max(luminance(foreground), luminance(background));
  const darker = Math.min(luminance(foreground), luminance(background));
  return (lighter + 0.05) / (darker + 0.05);
}

function surfaceColor(theme, surfaceName) {
  const canvas = parseColor(theme.colors.surface.canvas);
  const raw = parseColor(theme.colors.surface[surfaceName]);
  return surfaceName === "canvas" ? raw : composite(raw, canvas);
}

export function measureTokenContrast(themes) {
  const measurements = [];
  for (const [themeName, theme] of Object.entries(themes)) {
    for (const surfaceName of ["canvas", "raised", "elevated"]) {
      const surface = surfaceColor(theme, surfaceName);
      for (const contentName of ["primary", "secondary", "tertiary"]) {
        const foreground = composite(parseColor(theme.colors.content[contentName]), surface);
        measurements.push({
          theme: themeName,
          pair: `content.${contentName}`,
          surface: surfaceName,
          ratio: contrastRatio(foreground, surface),
          min: TEXT_MIN,
          role: "text",
        });
      }
      for (const semanticName of ["accent", "danger", "success", "warning"]) {
        const foreground = composite(parseColor(theme.colors[semanticName]), surface);
        measurements.push({
          theme: themeName,
          pair: semanticName,
          surface: surfaceName,
          ratio: contrastRatio(foreground, surface),
          min: TEXT_MIN,
          role: "text",
        });
      }
      const focus = composite(parseColor(theme.colors.focus), surface);
      measurements.push({
        theme: themeName,
        pair: "focus",
        surface: surfaceName,
        ratio: contrastRatio(focus, surface),
        min: NONTEXT_MIN,
        role: "nontext",
      });
    }
  }
  return measurements;
}

export function findContrastFailures(themes) {
  return measureTokenContrast(themes).filter((row) => row.ratio < row.min);
}

const SELF_TESTS = [
  {
    name: "white text on white canvas fails AA",
    themes: {
      fixture: {
        colors: {
          surface: { canvas: "#FFFFFF", raised: "#FFFFFF", elevated: "#FFFFFF" },
          content: { primary: "#FFFFFF", secondary: "#FFFFFF", tertiary: "#FFFFFF" },
          accent: "#FFFFFF",
          danger: "#FFFFFF",
          success: "#FFFFFF",
          warning: "#FFFFFF",
          focus: "#FFFFFF",
        },
      },
    },
    mustFail: true,
  },
  {
    name: "black text and a 3:1 focus ring on white pass AA",
    themes: {
      fixture: {
        colors: {
          surface: { canvas: "#FFFFFF", raised: "#FFFFFF", elevated: "#FFFFFF" },
          content: { primary: "#000000", secondary: "#000000", tertiary: "#000000" },
          accent: "#000000",
          danger: "#000000",
          success: "#000000",
          warning: "#000000",
          focus: "#005FCC",
        },
      },
    },
    mustFail: false,
  },
  {
    name: "a 3.9:1 body pair fails the 4.5:1 text floor",
    themes: {
      fixture: {
        colors: {
          // #767676 on #FFFFFF is ~4.54; #888888 on #FFFFFF is ~3.54.
          surface: { canvas: "#FFFFFF", raised: "#FFFFFF", elevated: "#FFFFFF" },
          content: { primary: "#888888", secondary: "#888888", tertiary: "#888888" },
          accent: "#888888",
          danger: "#888888",
          success: "#888888",
          warning: "#888888",
          focus: "#005FCC",
        },
      },
    },
    mustFail: true,
  },
];

function runSelfTests() {
  const failures = [];
  const scratch = mkdtempSync(join(tmpdir(), "omi-a11y-contrast-"));
  try {
    writeFileSync(join(scratch, "receipt"), "self-test");
    for (const fixture of SELF_TESTS) {
      const failed = findContrastFailures(fixture.themes).length > 0;
      if (failed !== fixture.mustFail) {
        failures.push(
          `self-test "${fixture.name}": expected ${fixture.mustFail ? "FAIL" : "PASS"}, `
            + `it ${failed ? "failed" : "passed"}`,
        );
      }
    }
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
  return failures;
}

const isMain = import.meta.url === pathToFileURL(resolve(process.argv[1] ?? "")).href;
if (isMain) {
  const selfTestFailures = runSelfTests();
  if (selfTestFailures.length) {
    console.error(`accessibility contrast fence IS ITSELF BROKEN (${selfTestFailures.length}):`);
    for (const failure of selfTestFailures) console.error(`  ${failure}`);
    process.exit(1);
  }

  let tokens;
  try {
    tokens = await import(pathToFileURL(TOKENS_DIST).href);
  } catch (error) {
    console.error(`accessibility contrast fence FAILED: build @omi-core/tokens first (${error.message})`);
    process.exit(1);
  }

  const productionFailures = findContrastFailures(tokens.SEMANTIC_TOKENS);
  if (productionFailures.length) {
    console.error(`accessibility contrast fence FAILED (${productionFailures.length}):`);
    for (const row of productionFailures) {
      console.error(
        `  ${row.theme} ${row.pair} on ${row.surface}: ${row.ratio.toFixed(2)}:1 < ${row.min}:1 (${row.role})`,
      );
    }
    process.exit(1);
  }

  const measured = measureTokenContrast(tokens.SEMANTIC_TOKENS).length;
  console.log(
    "accessibility contrast fence passed "
      + `(WCAG 2.2 AA token pairs; ${Object.keys(tokens.SEMANTIC_TOKENS).length} themes; `
      + `${measured} measurements; ${SELF_TESTS.length} self-test fixtures green).`,
  );
}
