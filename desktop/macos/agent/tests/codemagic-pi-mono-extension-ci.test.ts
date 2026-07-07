import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("macOS release CI", () => {
  it("runs the shared desktop tool-surface guardrail before packaging", () => {
    const codemagic = readFileSync(new URL("../../../../codemagic.yaml", import.meta.url), "utf8");
    const stepStart = codemagic.indexOf("name: Test desktop tool surfaces");
    expect(stepStart).toBeGreaterThanOrEqual(0);

    const step = codemagic.slice(stepStart, codemagic.indexOf("- name:", stepStart + 1));
    expect(step).toContain("scripts/test-tool-surfaces.sh");
    expect(stepStart).toBeLessThan(codemagic.indexOf("name: Prepare universal ffmpeg"));
  });

  it("bundles pi-mono-extension dependencies into release and local app resources", () => {
    const codemagic = readFileSync(new URL("../../../../codemagic.yaml", import.meta.url), "utf8");
    const runScript = readFileSync(new URL("../../run.sh", import.meta.url), "utf8");

    for (const manifestFile of [
      "control-tool-manifest.ts",
      "node-tools.ts",
      "omi-tool-manifest.ts",
    ]) {
      expect(codemagic).toContain(
        `cp -f agent/src/runtime/${manifestFile} "$APP_BUNDLE/Contents/Resources/agent/src/runtime/"`
      );
      expect(runScript).toContain(
        `cp -f "$AGENT_DIR/src/runtime/${manifestFile}" "$APP_BUNDLE/Contents/Resources/agent/src/runtime/"`
      );
    }
    expect(codemagic).toContain(
      'cp -Rf .harness/agent-runtime/agent-node_modules "$APP_BUNDLE/Contents/Resources/agent/node_modules"'
    );
    expect(codemagic).toContain(
      'cp -Rf .harness/agent-runtime/pi-mono-extension-node_modules "$APP_BUNDLE/Contents/Resources/pi-mono-extension/node_modules"'
    );
    expect(runScript).toContain('(cd "$PI_MONO_EXT_DIR" && npm ci --no-fund --no-audit)');
    expect(runScript).toContain(
      'macos_copy_tree "$AGENT_PACKAGED_NODE_MODULES" "$APP_BUNDLE/Contents/Resources/agent/node_modules"'
    );
    expect(runScript).toContain(
      'macos_copy_tree "$PI_MONO_PACKAGED_NODE_MODULES" "$APP_BUNDLE/Contents/Resources/pi-mono-extension/node_modules"'
    );
  });

  it("prepares production-only Node dependencies for app packaging", () => {
    const prepareRuntimeScript = readFileSync(
      new URL("../../scripts/prepare-agent-runtime.sh", import.meta.url),
      "utf8"
    );

    expect(prepareRuntimeScript).toContain("npm run build --silent");
    expect(prepareRuntimeScript).toContain('stage_production_node_modules "$AGENT_DIR" "$AGENT_PACKAGED_NODE_MODULES"');
    expect(prepareRuntimeScript).toContain(
      'stage_production_node_modules "$PI_MONO_DIR" "$PI_MONO_PACKAGED_NODE_MODULES"'
    );
    expect(prepareRuntimeScript).toContain("dedupe_pi_mono_packaged_node_modules");
    expect(prepareRuntimeScript).toContain("prune_packaged_node_modules");
    expect(prepareRuntimeScript).toContain('["darwin_arm64", "darwin_x64"]');
    expect(prepareRuntimeScript).toContain('["arm64-darwin", "x64-darwin"]');
    expect(prepareRuntimeScript).toContain('return `../../agent/node_modules/${packageName}`');
    expect(prepareRuntimeScript).toContain('return `../../../agent/node_modules/${packageName}`');
    expect(prepareRuntimeScript).toContain("npm ci --omit=dev --no-fund --no-audit");
    expect(prepareRuntimeScript).toContain('prune_non_macos_node_packages "$temp_dir"');
  });

  it("signs bundled pi-mono-extension native dependencies before app signing", () => {
    const codemagic = readFileSync(new URL("../../../../codemagic.yaml", import.meta.url), "utf8");

    const bundleStart = codemagic.indexOf(
      'PI_MONO_EXTENSION_BUNDLE="$APP_BUNDLE/Contents/Resources/pi-mono-extension"'
    );
    const appSignStart = codemagic.indexOf("# Sign the main app bundle with release entitlements");

    expect(bundleStart).toBeGreaterThanOrEqual(0);
    expect(appSignStart).toBeGreaterThan(bundleStart);
    expect(codemagic.slice(bundleStart, appSignStart)).toContain(
      'find "$PI_MONO_EXTENSION_BUNDLE/node_modules" -type f'
    );
    expect(codemagic.slice(bundleStart, appSignStart)).toContain('grep -q "Mach-O"');
    expect(codemagic.slice(bundleStart, appSignStart)).toContain(
      "codesign --force --options runtime --timestamp"
    );
  });
});
