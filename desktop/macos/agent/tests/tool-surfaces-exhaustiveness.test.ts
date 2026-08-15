import { describe, expect, it } from "vitest";
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, statSync } from "node:fs";
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
const generatedOutputPaths = [
  join(__dirname, "../../Desktop/Sources/Generated/GeneratedToolCapabilities.swift"),
  realtimeToolsPath,
  join(__dirname, "../../Desktop/Sources/Generated/GeneratedToolExecutors.swift"),
  join(__dirname, "../../Desktop/Sources/Generated/OmiToolManifest.generated.swift"),
  fixturePath,
];
const providerTopLevelCompositeSchemaKeys = ["anyOf", "oneOf", "allOf"];

function stripTypesNode(): string {
  const candidates = [
    process.env.OMI_TOOL_SURFACE_NODE,
    "/opt/homebrew/opt/node@22/bin/node",
    "/usr/local/opt/node@22/bin/node",
    process.execPath,
  ].filter((candidate): candidate is string => Boolean(candidate));

  for (const candidate of candidates) {
    if (!existsSync(candidate)) continue;
    try {
      execFileSync(candidate, ["--experimental-strip-types", "-e", ""], { stdio: "pipe" });
      return candidate;
    } catch {
      // This Vitest process may run under a package-manager Node older than 22.
    }
  }
  throw new Error("Node.js 22.6+ with --experimental-strip-types is required for tool surface generation");
}

function runToolSurfaceGenerator(args = "") {
  execFileSync(stripTypesNode(), ["--experimental-strip-types", "scripts/generate-tool-surfaces.mjs", ...args.trim().split(/\s+/).filter(Boolean)], {
    cwd: join(__dirname, ".."),
    stdio: "pipe",
  });
}

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

function hasRealtimeSurface(tool: (typeof omiToolManifest)[number]): boolean {
  if (tool.surfaces.includes("realtime_voice")) return true;
  return Object.values(tool.aliasCapabilityDocs ?? {}).some((doc) =>
    (doc.surfaces ?? tool.surfaces).includes("realtime_voice"),
  );
}

describe("tool surface exhaustiveness", () => {
  it("declares and generates both permission tools across pi-mono and realtime", () => {
    const permissionTools = ["check_permission_status", "request_permission"];
    const piMonoNames = new Set(toolsForAdapter("pi-mono").map((tool) => tool.name));
    const realtimeNames = new Set(generatedRealtimeToolDefinitions().map((tool) => tool.name));

    for (const name of permissionTools) {
      expect(piMonoNames, `pi-mono missing ${name}`).toContain(name);
      expect(realtimeNames, `generated realtime tools missing ${name}`).toContain(name);
    }
  });

  it("matches the checked-in manifest fixture", () => {
    const fixture = JSON.parse(readFileSync(fixturePath, "utf8"));
    expect(fixture).toEqual(JSON.parse(JSON.stringify(omiToolManifest)));
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
    expect(() => runToolSurfaceGenerator(" --check")).not.toThrow();
  });

  it("does not rewrite unchanged generated outputs", () => {
    runToolSurfaceGenerator();
    const firstRunMtimes = new Map(
      generatedOutputPaths.map((path) => [path, statSync(path, { bigint: true }).mtimeNs]),
    );

    runToolSurfaceGenerator();

    for (const path of generatedOutputPaths) {
      expect(statSync(path, { bigint: true }).mtimeNs, path).toBe(firstRunMtimes.get(path));
    }
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
      ...mcpToolDefinitionsForAdapter("omi-tools-stdio", { screenContext: true }).map((tool) => ({
        surface: "mcp:screenContext",
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

  it("only generates realtime tools that declare a realtime surface", () => {
    const generated = generatedRealtimeToolDefinitions().map((tool) => tool.name);
    expect(generated).not.toContain("run_agent_and_wait");

    for (const name of generated) {
      const tool = omiToolManifest.find((candidate) => {
        if (candidate.name === name) return true;
        return Object.keys(candidate.aliasCapabilityDocs ?? {}).includes(name);
      });
      expect(tool, `missing manifest entry for realtime tool ${name}`).toBeTruthy();
      expect(hasRealtimeSurface(tool!), `${name} must declare realtime_voice`).toBe(true);
    }
  });

  it("exposes runtime dispatch scoping fields in provider schemas", () => {
    const dispatch = omiToolManifest.find((tool) => tool.name === "create_desktop_dispatch");
    expect(dispatch).toBeTruthy();
    const properties = dispatch!.inputSchema.properties;
    for (const field of [
      "recommendedDefault",
      "sourceSessionId",
      "sourceRunId",
      "sourceAttemptId",
      "sourceArtifactId",
      "capability",
      "operation",
      "resourceRef",
      "expiresAtMs",
    ]) {
      expect(properties, `create_desktop_dispatch missing ${field}`).toHaveProperty(field);
    }
  });
});
