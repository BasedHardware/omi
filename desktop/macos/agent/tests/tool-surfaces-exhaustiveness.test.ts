import { describe, expect, it } from "vitest";
import { execSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { agentControlCapabilityManifest } from "../src/runtime/control-tool-manifest.js";
import {
  mcpToolDefinitionsForAdapter,
  omiToolManifest,
  toolsForAdapter,
} from "../src/runtime/omi-tool-manifest.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const fixturePath = join(__dirname, "fixtures", "tool-manifest.json");
const realtimeToolsPath = join(__dirname, "../../Desktop/Sources/Generated/GeneratedRealtimeTools.swift");
const providerTopLevelCompositeSchemaKeys = ["anyOf", "oneOf", "allOf"];

function assertFlatProviderInputSchema(surface: string, toolName: string, schema: Record<string, unknown>) {
  expect(schema, `${surface}:${toolName} schema`).toMatchObject({
    type: "object",
  });
  expect(schema.properties, `${surface}:${toolName} properties`).toBeTruthy();
  for (const key of providerTopLevelCompositeSchemaKeys) {
    expect(schema, `${surface}:${toolName} top-level ${key}`).not.toHaveProperty(key);
  }
}

function generatedRealtimeToolDefinitions(): Array<{ name: string; parameters: Record<string, unknown> }> {
  const source = readFileSync(realtimeToolsPath, "utf8");
  const match = /baseOpenAIToolsTemplateJSON = """\n([\s\S]*?)\n"""/.exec(source);
  if (!match) {
    throw new Error("GeneratedRealtimeTools.swift is missing baseOpenAIToolsTemplateJSON");
  }
  return JSON.parse(match[1]) as Array<{ name: string; parameters: Record<string, unknown> }>;
}

describe("tool surface exhaustiveness", () => {
  it("matches the checked-in manifest fixture", () => {
    const fixture = JSON.parse(readFileSync(fixturePath, "utf8"));
    expect(fixture).toEqual(omiToolManifest);
  });

  it("binds every swiftTool to a swift executor", () => {
    for (const tool of omiToolManifest) {
      if (tool.executor.kind !== "swiftTool") continue;
      expect(tool.executor.executorName, `${tool.name} missing swift executor`).toBeTruthy();
      expect(["chatToolExecutor", "realtimeHub"]).toContain(tool.executor.executorName);
    }
  });

  it("registers every runtimeControl tool in control-tools dispatch", () => {
    const controlSource = readFileSync(join(__dirname, "../src/runtime/control-tools.ts"), "utf8");
    for (const tool of omiToolManifest) {
      if (tool.executor.kind !== "runtimeControl") continue;
      expect(controlSource).toContain(`case "${tool.name}":`);
    }
    expect(agentControlCapabilityManifest.map((tool) => tool.name).sort()).toEqual(
      omiToolManifest
        .filter((tool) => tool.executor.kind === "runtimeControl")
        .map((tool) => tool.name)
        .sort(),
    );
  });

  it("registers every nodeTool in the node-tools runtime", () => {
    const nodeSource = readFileSync(join(__dirname, "../src/omi-tools-stdio.ts"), "utf8");
    for (const tool of omiToolManifest) {
      if (tool.executor.kind !== "nodeTool") continue;
      expect(nodeSource.includes(`"${tool.name}"`)).toBe(true);
    }
  });

  it("generator check passes on the checked-in manifest snapshot", () => {
    expect(() =>
      execSync("node --experimental-strip-types scripts/generate-tool-surfaces.mjs --check", {
        cwd: join(__dirname, ".."),
        stdio: "pipe",
      }),
    ).not.toThrow();
  });

  it("keeps every provider-facing tool schema as a flat object schema", () => {
    const providerSchemas: Array<{ surface: string; name: string; schema: Record<string, unknown> }> = [
      ...toolsForAdapter("pi-mono").map((tool) => ({
        surface: "pi-mono",
        name: tool.adapters["pi-mono"]?.adapterName ?? tool.name,
        schema: tool.inputSchema,
      })),
      ...mcpToolDefinitionsForAdapter("omi-tools-stdio").map((tool) => ({
        surface: "mcp",
        name: tool.name,
        schema: tool.inputSchema,
      })),
      ...mcpToolDefinitionsForAdapter("omi-tools-stdio", { onboarding: true }).map((tool) => ({
        surface: "mcp:onboarding",
        name: tool.name,
        schema: tool.inputSchema,
      })),
      ...generatedRealtimeToolDefinitions().map((tool) => ({
        surface: "realtime",
        name: tool.name,
        schema: tool.parameters,
      })),
    ];

    expect(providerSchemas.length).toBeGreaterThan(0);
    for (const { surface, name, schema } of providerSchemas) {
      assertFlatProviderInputSchema(surface, name, schema);
    }
  });
});
