#!/usr/bin/env node
/**
 * Generate Swift tool surfaces and test fixtures from omi-tool-manifest.ts.
 * Run: node --experimental-strip-types scripts/generate-tool-surfaces.mjs [--check]
 */
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { omiToolManifest } from "../dist/runtime/omi-tool-manifest.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const AGENT_DIR = join(__dirname, "..");
const MACOS_DIR = join(AGENT_DIR, "..");
const GENERATED_DIR = join(MACOS_DIR, "Desktop", "Sources", "Generated");
const FIXTURE_PATH = join(AGENT_DIR, "tests", "fixtures", "tool-manifest.json");

const VALID_SURFACES = new Set(["desktop_chat", "realtime_voice", "onboarding", "task_chat"]);
const PROVIDER_TOP_LEVEL_COMPOSITE_SCHEMA_KEYS = ["anyOf", "oneOf", "allOf"];
const CHECK_MODE = process.argv.includes("--check");

const OUTPUTS = [
  join(GENERATED_DIR, "GeneratedToolCapabilities.swift"),
  join(GENERATED_DIR, "GeneratedRealtimeTools.swift"),
  join(GENERATED_DIR, "GeneratedToolExecutors.swift"),
  join(GENERATED_DIR, "OmiToolManifest.generated.swift"),
  FIXTURE_PATH,
];

function swiftEscape(value) {
  return value
    .replace(/\\/g, "\\\\")
    .replace(/"/g, '\\"')
    .replace(/\r/g, "")
    .replace(/\n/g, "\\n");
}

function swiftStringArray(values) {
  if (values.length === 0) return "[]";
  return `[\n${values.map((v) => `      ${JSON.stringify(v)}`).join(",\n")}\n    ]`;
}

function latencyEnum(latency) {
  switch (latency) {
    case "fast local":
      return ".fastLocal";
    case "fast network":
      return ".fastNetwork";
    case "async background":
      return ".asyncBackground";
    default:
      throw new Error(`Unknown latency: ${latency}`);
  }
}

function surfaceEnum(surface) {
  switch (surface) {
    case "desktop_chat":
      return ".desktopChat";
    case "realtime_voice":
      return ".realtimeHub";
    case "onboarding":
      return ".onboarding";
    case "task_chat":
      return ".taskChat";
    default:
      throw new Error(`Unknown surface: ${surface}`);
  }
}

function surfaceSet(surfaces) {
  const unique = [...new Set(surfaces)];
  return `Set([${unique.map(surfaceEnum).join(", ")}])`;
}

function assertFlatProviderInputSchema(schema, label) {
  if (!schema || typeof schema !== "object" || Array.isArray(schema)) {
    throw new Error(`${label} provider input schema must be an object`);
  }
  if (schema.type !== "object") {
    throw new Error(`${label} provider input schema must have top-level type=object`);
  }
  if (!schema.properties || typeof schema.properties !== "object" || Array.isArray(schema.properties)) {
    throw new Error(`${label} provider input schema must have top-level properties`);
  }
  for (const key of PROVIDER_TOP_LEVEL_COMPOSITE_SCHEMA_KEYS) {
    if (Object.prototype.hasOwnProperty.call(schema, key)) {
      throw new Error(`${label} provider input schema must not use top-level ${key}`);
    }
  }
}

function validateManifest() {
  const names = new Set();
  const aliases = new Map();

  for (const tool of omiToolManifest) {
    if (tool.intendedForAgents !== false && !tool.surfaces?.length) {
      throw new Error(`Tool ${tool.name} is missing surfaces`);
    }
    if (!tool.capabilityDoc?.title) {
      throw new Error(`Tool ${tool.name} is missing capabilityDoc`);
    }
    for (const surface of tool.surfaces) {
      if (!VALID_SURFACES.has(surface)) {
        throw new Error(`Tool ${tool.name} references unknown surface ${surface}`);
      }
    }
    if (!tool.executor?.kind) {
      throw new Error(`Tool ${tool.name} is missing executor.kind`);
    }
    assertFlatProviderInputSchema(tool.inputSchema, `${tool.name} manifest`);
    if (tool.mcpInputSchema) {
      assertFlatProviderInputSchema(tool.mcpInputSchema, `${tool.name} MCP`);
    }
    if (tool.executor.kind === "swiftTool" && !tool.executor.executorName) {
      tool.executor.executorName = "chatToolExecutor";
    }
    if (names.has(tool.name)) {
      throw new Error(`Duplicate tool name: ${tool.name}`);
    }
    names.add(tool.name);

    const registerAlias = (alias) => {
      if (aliases.has(alias)) {
        throw new Error(`Duplicate alias ${alias} on ${tool.name} and ${aliases.get(alias)}`);
      }
      aliases.set(alias, tool.name);
    };

    for (const alias of tool.aliases ?? []) {
      registerAlias(alias);
    }
    for (const alias of Object.keys(tool.aliasCapabilityDocs ?? {})) {
      if (!(tool.aliases ?? []).includes(alias)) {
        registerAlias(alias);
      }
    }
  }
}

function collectCapabilities() {
  const capabilities = [];

  const pushCapability = (toolName, tool, doc, surfaces, { mergeGuidelines = false } = {}) => {
    // Canonical entries fold promptGuidelines into the capability bullets so
    // the manifest stays the single declaration site (guidelines are never
    // hand-mirrored into capabilityDoc; ChatDiscoverabilityTests enforces the
    // superset). Aliases keep their own doc verbatim.
    const bullets = [...doc.bullets];
    if (mergeGuidelines) {
      for (const guideline of tool.promptGuidelines ?? []) {
        if (!bullets.includes(guideline)) bullets.push(guideline);
      }
    }
    capabilities.push({
      toolName,
      title: doc.title,
      latency: tool.latency,
      surfaces,
      summary: doc.summary,
      bullets,
    });
  };

  for (const tool of omiToolManifest) {
    pushCapability(tool.name, tool, tool.capabilityDoc, tool.surfaces, { mergeGuidelines: true });
    for (const [alias, doc] of Object.entries(tool.aliasCapabilityDocs ?? {})) {
      const aliasSurfaces = doc.surfaces ?? tool.surfaces;
      pushCapability(alias, tool, doc, aliasSurfaces);
    }
  }

  return capabilities;
}

function realtimeToolName(tool) {
  const aliasDocs = tool.aliasCapabilityDocs ?? {};
  for (const [alias, doc] of Object.entries(aliasDocs)) {
    const aliasSurfaces = doc.surfaces ?? tool.surfaces;
    if (aliasSurfaces.includes("realtime_voice")) {
      return alias;
    }
  }
  return tool.name;
}

function realtimeTools() {
  const REALTIME_CONTROL_TOOLS = new Set([
    "list_agent_sessions",
    "get_agent_run",
    "cancel_agent_run",
    "inspect_agent_artifacts",
    "update_agent_artifact_lifecycle",
    "spawn_agent",
    "set_desktop_attention_override",
  ]);

  const hasRealtimeVoiceSurface = (tool) => {
    if (tool.surfaces.includes("realtime_voice")) return true;
    for (const doc of Object.values(tool.aliasCapabilityDocs ?? {})) {
      const aliasSurfaces = doc.surfaces ?? tool.surfaces;
      if (aliasSurfaces.includes("realtime_voice")) return true;
    }
    return false;
  };

  const shouldExpose = (tool) => {
    if (tool.voice?.realtimeExpose === false) return false;
    if (tool.voice?.realtimeExpose === true) return true;
    if (tool.executor.kind === "runtimeControl") {
      return REALTIME_CONTROL_TOOLS.has(tool.name) && hasRealtimeVoiceSurface(tool);
    }
    return hasRealtimeVoiceSurface(tool);
  };

  const entries = [];
  const seen = new Set();

  const push = (exposedName, tool) => {
    if (seen.has(exposedName)) return;
    seen.add(exposedName);
    entries.push({ exposedName, tool });
  };

  for (const tool of omiToolManifest) {
    if (shouldExpose(tool)) {
      push(realtimeToolName(tool), tool);
    }
    for (const [alias, doc] of Object.entries(tool.aliasCapabilityDocs ?? {})) {
      const aliasSurfaces = doc.surfaces ?? tool.surfaces;
      if (!aliasSurfaces.includes("realtime_voice")) continue;
      if (!shouldExpose(tool)) continue;
      push(alias, tool);
    }
  }
  return entries;
}

function schemaForRealtime(tool) {
  return tool.voice?.schemaOverride ?? tool.inputSchema;
}

function descriptionForRealtime(tool) {
  return tool.voice?.realtimeDescription ?? tool.description;
}

// Gemini Live functionDeclaration.parameters uses OpenAPI 3.0 Schema, not full JSON Schema.
// Strip keys that make setup fail (e.g. additionalProperties) before embedding in realtime tools.
const GEMINI_UNSUPPORTED_REALTIME_SCHEMA_KEYS = new Set([
  "additionalProperties",
  "$schema",
  "default",
  "title",
  "pattern",
  "const",
]);

function sanitizeRealtimeVoiceSchema(schema) {
  if (schema === null || typeof schema !== "object" || Array.isArray(schema)) {
    return schema;
  }

  const out = {};
  for (const [key, value] of Object.entries(schema)) {
    if (GEMINI_UNSUPPORTED_REALTIME_SCHEMA_KEYS.has(key)) continue;
    if (key === "properties" && value && typeof value === "object" && !Array.isArray(value)) {
      const props = {};
      for (const [propKey, propValue] of Object.entries(value)) {
        props[propKey] = sanitizeRealtimeVoiceSchema(propValue);
      }
      out[key] = props;
      continue;
    }
    if (key === "items" && value && typeof value === "object") {
      out[key] = sanitizeRealtimeVoiceSchema(value);
      continue;
    }
    if (Array.isArray(value)) {
      out[key] = value.map((item) =>
        item && typeof item === "object" ? sanitizeRealtimeVoiceSchema(item) : item,
      );
      continue;
    }
    if (value && typeof value === "object") {
      out[key] = sanitizeRealtimeVoiceSchema(value);
      continue;
    }
    out[key] = value;
  }
  return out;
}

function openAIToolDefinition({ exposedName, tool }, { includeSpawnProvider = false, directedProviders = [] } = {}) {
  const schema = schemaForRealtime(tool);
  const description = descriptionForRealtime(tool);

  if (tool.name === "spawn_agent" && includeSpawnProvider) {
    const properties = {
      brief: {
        type: "string",
        description:
          "The user's raw delegation intent or proposed task. Include concrete details you know; Omi's resolver will rewrite it before any child agent sees it.",
      },
      title: {
        type: "string",
        description:
          "A short Title Case label for the task pill (≤ ~5 words, no trailing punctuation), e.g. 'Draft Launch Email'.",
      },
    };
    if (directedProviders.length > 0) {
      properties.provider = {
        type: "string",
        enum: directedProviders,
        description: "Optional available local provider to run this background agent through.",
      };
    }
    return {
      type: "function",
      name: exposedName,
      description,
      parameters: {
        type: "object",
        properties,
        required: ["brief"],
      },
    };
  }

  const parameters = sanitizeRealtimeVoiceSchema({ ...schema });

  return {
    type: "function",
    name: exposedName,
    description,
    parameters,
  };
}

function generateCapabilitiesSwift(capabilities, realtimeExposedNames) {
  const entries = capabilities
    .map((cap) => {
      const bullets = swiftStringArray(cap.bullets);
      return `    Capability(
      toolName: ${JSON.stringify(cap.toolName)},
      title: ${JSON.stringify(cap.title)},
      latency: ${latencyEnum(cap.latency)},
      surfaces: ${surfaceSet(cap.surfaces)},
      summary: ${JSON.stringify(cap.summary)},
      bullets: ${bullets}
    )`;
    })
    .join(",\n");

  return `// Generated by agent/scripts/generate-tool-surfaces.mjs — do not edit.
import Foundation

enum GeneratedToolCapabilities {
  enum Surface: Hashable {
    case desktopChat
    case realtimeHub
    case onboarding
    case taskChat
  }

  enum LatencyClass: String {
    case fastLocal = "fast local"
    case fastNetwork = "fast network"
    case asyncBackground = "async background"
  }

  struct Capability {
    let toolName: String
    let title: String
    let latency: LatencyClass
    let surfaces: Set<Surface>
    let summary: String
    let bullets: [String]

    func supports(_ surface: Surface) -> Bool {
      surfaces.contains(surface)
    }
  }

  static let capabilities: [Capability] = [
${entries}
  ]

  static func capabilities(for surface: Surface) -> [Capability] {
    capabilities.filter { $0.supports(surface) }
  }

  static var desktopToolNames: [String] {
    capabilities(for: .desktopChat).map(\\.toolName)
  }

  static var realtimeToolNames: [String] {
    ${JSON.stringify(realtimeExposedNames)}
  }
}
`;
}

function generateRealtimeToolsSwift(realtimeEntries) {
  const baseTools = realtimeEntries.map((entry) => openAIToolDefinition(entry));
  for (const tool of baseTools) {
    assertFlatProviderInputSchema(tool.parameters, `${tool.name} realtime`);
  }
  // Double backslashes so Swift multiline strings preserve JSON escapes (e.g. \n).
  const json = JSON.stringify(baseTools, null, 2).replace(/\\/g, "\\\\");

  const hubCases = realtimeEntries
    .map(({ exposedName }) => {
      const caseName = exposedName
        .replace(/_([a-z])/g, (_, c) => c.toUpperCase())
        .replace(/_([0-9])/g, (_, d) => d);
      const swiftCase = caseName.charAt(0).toLowerCase() + caseName.slice(1);
      return `  case ${swiftCase} = "${exposedName}"`;
    })
    .join("\n");

  return `// Generated by agent/scripts/generate-tool-surfaces.mjs — do not edit.
import Foundation

enum HubTool: String {
${hubCases}
}

enum GeneratedRealtimeTools {
  private static let baseOpenAIToolsTemplateJSON = """
${json}
"""

  static var baseOpenAIToolsTemplate: [[String: Any]] {
    guard let data = baseOpenAIToolsTemplateJSON.data(using: .utf8),
      let tools = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]]
    else {
      fatalError("Invalid generated realtime tools JSON")
    }
    return tools
  }

  static func baseOpenAITools(providerProperty: [String: Any]?) -> [[String: Any]] {
    var tools = baseOpenAIToolsTemplate
    guard let index = tools.firstIndex(where: { ($0["name"] as? String) == "spawn_agent" }) else {
      return tools
    }
    guard var parameters = tools[index]["parameters"] as? [String: Any],
      var properties = parameters["properties"] as? [String: Any] else {
      return tools
    }
    if let providerProperty {
      properties["provider"] = providerProperty
    } else {
      properties.removeValue(forKey: "provider")
    }
    parameters["properties"] = properties
    tools[index]["parameters"] = parameters
    return tools
  }
}
`;
}

function swiftExecutorEnum(name) {
  switch (name) {
    case "chatToolExecutor":
      return ".chatToolExecutor";
    case "realtimeHub":
      return ".realtimeHub";
    default:
      throw new Error(`Unknown swift executor: ${name}`);
  }
}

function swiftToolCaseName(name) {
  const camel = name.replace(/_([a-z])/g, (_, c) => c.toUpperCase());
  return camel;
}

function generateExecutorsSwift() {
  const swiftTools = omiToolManifest.filter((tool) => tool.executor.kind === "swiftTool");
  const enumCases = swiftTools
    .map((tool) => `  case ${swiftToolCaseName(tool.name)} = "${tool.name}"`)
    .join("\n");

  const aliasMapEntries = [];
  const aliasKeys = new Set();
  for (const tool of swiftTools) {
    for (const alias of [...(tool.aliases ?? []), ...Object.keys(tool.aliasCapabilityDocs ?? {})]) {
      if (aliasKeys.has(alias)) continue;
      aliasKeys.add(alias);
      aliasMapEntries.push(`    "${alias}": .${swiftToolCaseName(tool.name)}`);
    }
  }

  const executorEntries = swiftTools
    .map(
      (tool) =>
        `    .${swiftToolCaseName(tool.name)}: ${swiftExecutorEnum(tool.executor.executorName ?? "chatToolExecutor")}`,
    )
    .join(",\n");

  const chatToolCases = swiftTools
    .filter((tool) => (tool.executor.executorName ?? "chatToolExecutor") === "chatToolExecutor")
    .map((tool) => `    case ${swiftToolCaseName(tool.name)}`)
    .join("\n");

  return `// Generated by agent/scripts/generate-tool-surfaces.mjs — do not edit.
import Foundation

enum GeneratedSwiftTool: String, CaseIterable {
${enumCases}
}

enum GeneratedSwiftToolExecutor: String {
  case chatToolExecutor
  case realtimeHub
}

enum GeneratedToolExecutors {
  static let aliasToCanonical: [String: GeneratedSwiftTool] = [
${aliasMapEntries.join(",\n")}
  ]

  static let executorByTool: [GeneratedSwiftTool: GeneratedSwiftToolExecutor] = [
${executorEntries}
  ]

  static func resolve(_ name: String) -> GeneratedSwiftTool? {
    if let direct = GeneratedSwiftTool(rawValue: name) {
      return direct
    }
    return aliasToCanonical[name]
  }

  static func isChatToolExecutorTool(_ name: String) -> Bool {
    guard let tool = resolve(name) else { return false }
    return executorByTool[tool] == .chatToolExecutor
  }

  static var chatToolExecutorToolNames: Set<String> {
    Set(
      executorByTool.compactMap { tool, executor in
        executor == .chatToolExecutor ? tool.rawValue : nil
      }
      + aliasToCanonical.compactMap { alias, tool in
        executorByTool[tool] == .chatToolExecutor ? alias : nil
      }
    )
  }

  static var realtimeHubToolNames: Set<String> {
    Set(GeneratedToolCapabilities.realtimeToolNames)
  }

  /// Dispatch surface for ChatToolExecutor — chatToolExecutor-bound tools only.
  enum ChatDispatch {
${chatToolCases}
    case unhandled
  }

  static func chatDispatch(for name: String) -> ChatDispatch {
    guard let tool = resolve(name), executorByTool[tool] == .chatToolExecutor else {
      return .unhandled
    }
    switch tool {
${swiftTools
  .filter((tool) => (tool.executor.executorName ?? "chatToolExecutor") === "chatToolExecutor")
  .map((tool) => `    case .${swiftToolCaseName(tool.name)}: return .${swiftToolCaseName(tool.name)}`)
  .join("\n")}
    default: return .unhandled
    }
  }
}
`;
}

function schemaPropertyToSwift(name, schema) {
  const lines = [`"${name}": [`];
  if (schema.type) lines.push(`  "type": "${schema.type}",`);
  if (schema.description) lines.push(`  "description": ${JSON.stringify(schema.description)},`);
  if (schema.enum) lines.push(`  "enum": ${JSON.stringify(schema.enum)},`);
  if (schema.items) {
    lines.push(`  "items": [`);
    if (schema.items.type) lines.push(`    "type": "${schema.items.type}",`);
    if (schema.items.description) lines.push(`    "description": ${JSON.stringify(schema.items.description)},`);
    lines.push(`  ],`);
  }
  lines.push(`]`);
  return lines.join("\n        ");
}

function generateLocalApiSwift() {
  const localTools = omiToolManifest.filter((tool) => tool.adapters["local-agent-api"]?.advertised === true);

  const entries = localTools
    .map((tool) => {
      const properties = Object.entries(tool.inputSchema.properties ?? {});
      const propertiesSwift =
        properties.length === 0
          ? "[:]"
          : `[\n        ${properties.map(([name, schema]) => schemaPropertyToSwift(name, schema)).join(",\n        ")}\n      ]`;
      const required = swiftStringArray(tool.inputSchema.required ?? []);
      const annotations = [
        `"readOnlyHint": ${tool.annotations.readOnlyHint ?? false}`,
        `"destructiveHint": ${tool.annotations.destructiveHint ?? false}`,
        `"openWorldHint": ${tool.annotations.openWorldHint ?? false}`,
      ].join(", ");
      return `    LocalAgentTool(
      name: ${JSON.stringify(tool.name)},
      description: ${JSON.stringify(tool.description)},
      properties: ${propertiesSwift},
      required: ${required},
      annotations: [${annotations}]
    )`;
    })
    .join(",\n");

  return `// Generated by agent/scripts/generate-tool-surfaces.mjs — do not edit.
import Foundation

enum OmiToolManifest {
  static let localAgentAPITools: [LocalAgentTool] = [
${entries}
  ]
}
`;
}

function generateFixture() {
  return `${JSON.stringify(omiToolManifest, null, 2)}\n`;
}

function writeOrCheck(path, content) {
  if (CHECK_MODE) {
    const existing = readFileSync(path, "utf8");
    if (existing !== content) {
      throw new Error(`Generated output drift: ${path}`);
    }
    return;
  }
  writeFileSync(path, content, "utf8");
}

function main() {
  validateManifest();
  const capabilities = collectCapabilities();
  const realtimeEntries = realtimeTools();
  const realtimeExposedNames = realtimeEntries.map((entry) => entry.exposedName).sort();

  mkdirSync(GENERATED_DIR, { recursive: true });
  mkdirSync(dirname(FIXTURE_PATH), { recursive: true });

  const files = {
    [join(GENERATED_DIR, "GeneratedToolCapabilities.swift")]: generateCapabilitiesSwift(capabilities, realtimeExposedNames),
    [join(GENERATED_DIR, "GeneratedRealtimeTools.swift")]: generateRealtimeToolsSwift(realtimeEntries),
    [join(GENERATED_DIR, "GeneratedToolExecutors.swift")]: generateExecutorsSwift(),
    [join(GENERATED_DIR, "OmiToolManifest.generated.swift")]: generateLocalApiSwift(),
    [FIXTURE_PATH]: generateFixture(),
  };

  for (const [path, content] of Object.entries(files)) {
    writeOrCheck(path, content);
  }

  if (CHECK_MODE) {
    console.log("generate-tool-surfaces: all outputs match (--check)");
  } else {
    const hash = createHash("sha256").update(JSON.stringify(omiToolManifest)).digest("hex").slice(0, 12);
    console.log(`generate-tool-surfaces: wrote ${Object.keys(files).length} files (manifest ${hash})`);
  }
}

main();
