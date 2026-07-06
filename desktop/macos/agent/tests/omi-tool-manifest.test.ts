import { describe, expect, it } from "vitest";
import {
  buildToolAvailabilitySnapshot,
  mcpToolDefinitionsForAdapter,
  normalizeOmiToolName,
  omiToolManifest,
  toolNamesForAdapter,
  toolsForAdapter,
} from "../src/runtime/omi-tool-manifest.js";

describe("omi tool manifest", () => {
  it("has unique canonical names", () => {
    const names = omiToolManifest.map((tool) => tool.name);
    expect(new Set(names).size).toBe(names.length);
  });

  it("projects the pi-mono task-agent surface", () => {
    expect(toolNamesForAdapter("pi-mono")).toEqual([
      "execute_sql",
      "semantic_search",
      "get_daily_recap",
      "get_task_agent_status",
      "list_agent_sessions",
      "get_agent_run",
      "cancel_agent_run",
      "inspect_agent_artifacts",
      "update_agent_artifact_lifecycle",
      "send_agent_message",
      "delegate_agent",
      "fill_cloud_connector_form",
      "spawn_agent",
      "manage_agent_pills",
      "search_tasks",
      "complete_task",
      "delete_task",
      "load_skill",
      "save_knowledge_graph",
      "get_conversations",
      "search_conversations",
      "get_memories",
      "search_memories",
      "get_action_items",
      "create_action_item",
      "update_action_item",
      "capture_screen",
    ]);
  });

  it("keeps directed provider routing on the canonical spawn_agent schema", () => {
    const spawnAgent = toolsForAdapter("pi-mono").find((tool) => tool.name === "spawn_agent");

    expect(spawnAgent?.inputSchema.properties.provider).toMatchObject({
      enum: ["openclaw", "hermes", "codex"],
    });
    expect(spawnAgent?.promptGuidelines?.join("\n")).toContain("provider='openclaw'");
    expect(spawnAgent?.promptGuidelines?.join("\n")).toContain("provider='hermes'");
    expect(spawnAgent?.promptGuidelines?.join("\n")).toContain("provider='codex'");
  });

  it("projects stdio onboarding-only tools only in onboarding context", () => {
    const regular = new Set(toolNamesForAdapter("omi-tools-stdio"));
    const onboarding = new Set(toolNamesForAdapter("omi-tools-stdio", { onboarding: true }));

    expect(regular.has("request_permission")).toBe(false);
    expect(regular.has("get_email_insights")).toBe(false);
    expect(regular.has("capture_screen")).toBe(false);
    expect(regular.has("get_work_context")).toBe(false);
    expect(onboarding.has("request_permission")).toBe(true);
    expect(onboarding.has("get_email_insights")).toBe(true);
    expect(onboarding.has("capture_screen")).toBe(false);
  });

  it("emits MCP tool definitions from the same projection", () => {
    expect(mcpToolDefinitionsForAdapter("omi-tools-stdio").map((tool) => tool.name)).toEqual(
      toolNamesForAdapter("omi-tools-stdio"),
    );
  });

  it("keeps schemas expressive enough for nested onboarding tools", () => {
    const saveKnowledgeGraph = toolsForAdapter("omi-tools-stdio", { onboarding: true }).find(
      (tool) => tool.name === "save_knowledge_graph",
    );
    const askFollowup = toolsForAdapter("omi-tools-stdio", { onboarding: true }).find(
      (tool) => tool.name === "ask_followup",
    );
    const requestPermission = toolsForAdapter("omi-tools-stdio", { onboarding: true }).find(
      (tool) => tool.name === "request_permission",
    );

    expect(saveKnowledgeGraph?.inputSchema.properties.nodes).toMatchObject({ type: "array" });
    expect(saveKnowledgeGraph?.inputSchema.properties.edges).toMatchObject({ type: "array" });
    expect(askFollowup?.inputSchema.properties.options).toMatchObject({ type: "array" });
    expect(askFollowup?.inputSchema.required).toEqual(["question", "options"]);
    expect(requestPermission?.inputSchema.properties.type).toMatchObject({
      enum: ["screen_recording", "microphone", "accessibility", "automation", "full_disk_access"],
    });
  });

  it("strips top-level schema combinators the Anthropic API rejects from MCP projections", () => {
    // The Claude Code SDK forwards these schemas verbatim to the Anthropic
    // API, which 400s on top-level oneOf/allOf/anyOf (observed live:
    // "input_schema does not support oneOf, allOf, or anyOf at the top
    // level"). The preconditions stay in prompt guidelines and are enforced
    // by the executor at call time.
    for (const tool of mcpToolDefinitionsForAdapter("omi-tools-stdio")) {
      expect(tool.inputSchema.anyOf, `${tool.name} anyOf`).toBeUndefined();
      expect(tool.inputSchema.allOf, `${tool.name} allOf`).toBeUndefined();
      expect(tool.inputSchema.oneOf, `${tool.name} oneOf`).toBeUndefined();
      expect(tool.inputSchema.if, `${tool.name} if`).toBeUndefined();
      expect(tool.inputSchema.then, `${tool.name} then`).toBeUndefined();
    }
  });

  it("keeps MCP-only schema options from overriding base tool schema fields", () => {
    for (const tool of toolsForAdapter("omi-tools-stdio")) {
      const mcpTool = mcpToolDefinitionsForAdapter("omi-tools-stdio").find((candidate) => candidate.name === tool.name);
      expect(mcpTool?.inputSchema.type).toBe(tool.inputSchema.type);
      expect(mcpTool?.inputSchema.properties).toEqual(tool.inputSchema.properties);
      expect(mcpTool?.inputSchema.required).toEqual(tool.inputSchema.required);
      expect(mcpTool?.inputSchema.additionalProperties).toEqual(tool.inputSchema.additionalProperties);
    }
  });

  it("normalizes MCP-prefixed and explicit aliases", () => {
    expect(normalizeOmiToolName("omi-tools-stdio", "mcp__omi-tools__execute_sql")).toEqual({
      canonicalName: "execute_sql",
      wasAlias: true,
    });
    expect(normalizeOmiToolName("omi-tools-stdio", "omi-tools.semantic_search")).toEqual({
      canonicalName: "semantic_search",
      wasAlias: true,
    });
    expect(normalizeOmiToolName("local-agent-api", "search_screen_history")).toEqual({
      canonicalName: "semantic_search",
      wasAlias: true,
    });
  });

  it("builds a debuggable availability snapshot", () => {
    const snapshot = buildToolAvailabilitySnapshot("pi-mono");

    expect(snapshot.adapterId).toBe("pi-mono");
    expect(snapshot.advertisedToolCount).toBe(toolNamesForAdapter("pi-mono").length);
    expect(snapshot.advertisedToolNames).toEqual(toolNamesForAdapter("pi-mono"));
    expect(snapshot.aliases["mcp__omi-tools__execute_sql"]).toBe("execute_sql");
    expect(snapshot.disabled.some((tool) => tool.name === "request_permission")).toBe(true);
  });
});
