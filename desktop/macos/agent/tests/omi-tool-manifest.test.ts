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
  it("projects agent-management tools out of leaf worker contexts", () => {
    for (const adapterId of ["pi-mono", "omi-tools-stdio"] as const) {
      const names = toolNamesForAdapter(adapterId, { executionRole: "leaf", screenContext: true });
      expect(names).not.toContain("spawn_agent");
      expect(names).not.toContain("spawn_background_agent");
      expect(names).not.toContain("run_agent_and_wait");
      expect(names).not.toContain("send_agent_message");
    }
  });

  it("has unique canonical names", () => {
    const names = omiToolManifest.map((tool) => tool.name);
    expect(new Set(names).size).toBe(names.length);
  });

  it("projects the pi-mono task-agent surface", () => {
    expect(toolNamesForAdapter("pi-mono")).toEqual([
      "execute_sql",
      "semantic_search",
      "get_daily_recap",
      "fill_cloud_connector_form",
      "list_agent_sessions",
      "get_agent_run",
      "build_desktop_awareness_snapshot",
      "list_desktop_action_queue",
      "get_desktop_open_loops",
      "build_desktop_context_packet",
      "route_desktop_intent",
      "evaluate_desktop_tool_policy",
      "create_desktop_dispatch",
      "cancel_agent_run",
      "inspect_agent_artifacts",
      "read_tool_output",
      "search_tool_output",
      "update_agent_artifact_lifecycle",
      "send_agent_message",
      "spawn_agent",
      "run_agent_and_wait",
      "set_desktop_attention_override",
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
      "check_permission_status",
      "request_permission",
      "screenshot",
      "get_work_context",
    ]);
    expect(toolNamesForAdapter("pi-mono")).not.toContain("resolve_desktop_dispatch");
  });

  it("keeps the realtime screenshot executor capability-registered", () => {
    const screenshot = toolsForAdapter("pi-mono").find((tool) => tool.name === "screenshot");

    expect(screenshot?.surfaces).toEqual(["realtime_voice"]);
    expect(screenshot?.executor).toEqual({ kind: "swiftTool", executorName: "realtimeHub" });
  });

  it("routes current-screen questions to work context before raw screenshots", () => {
    const workContext = toolsForAdapter("pi-mono").find((tool) => tool.name === "get_work_context");
    const captureScreen = toolsForAdapter("pi-mono").find((tool) => tool.name === "capture_screen");
    const requestPermission = toolsForAdapter("pi-mono").find((tool) => tool.name === "request_permission");

    expect(workContext?.promptGuidelines?.join("\n")).toContain("Call get_work_context first");
    expect(captureScreen?.promptGuidelines?.join("\n")).toContain("Call get_work_context first");
    expect(captureScreen?.promptGuidelines?.join("\n")).toContain("requires explicit approval");
    expect(requestPermission?.promptGuidelines?.join("\n")).toContain("current user message explicitly requests one named permission");
  });

  it("keeps spawn_background_agent internal to coordinator RPC only", () => {
    expect(toolNamesForAdapter("pi-mono")).not.toContain("spawn_background_agent");
    expect(toolsForAdapter("pi-mono").find((tool) => tool.name === "spawn_agent")).toBeDefined();
  });

  it("keeps directed provider routing on the canonical spawn_agent schema", () => {
    const spawnAgent = toolsForAdapter("pi-mono").find((tool) => tool.name === "spawn_agent");

    expect(spawnAgent?.inputSchema.required).toEqual(["objective"]);
    expect(spawnAgent?.inputSchema.properties).not.toHaveProperty("originSurfaceKind");
    expect(spawnAgent?.inputSchema.properties.provider).toMatchObject({
      enum: ["openclaw", "hermes", "codex"],
    });
    expect(spawnAgent?.promptGuidelines?.join("\n")).toContain("provider='openclaw'");
    expect(spawnAgent?.promptGuidelines?.join("\n")).toContain("provider='hermes'");
    expect(spawnAgent?.promptGuidelines?.join("\n")).toContain("provider='codex'");
  });

  it("guides realtime child-result retrieval without exposing internal ids", () => {
    const list = omiToolManifest.find((tool) => tool.name === "list_agent_sessions");
    const run = omiToolManifest.find((tool) => tool.name === "get_agent_run");

    expect(list?.promptGuidelines?.join("\n")).toContain("do not infer run completion from session status");
    expect(list?.voice?.realtimeDescription).toContain("restrict discovery to status='open'");
    expect(run?.promptGuidelines?.join("\n")).toContain("run.finalText");
    expect(run?.voice?.realtimeDescription).toContain("run.finalText");
    expect(run?.voice?.realtimeDescription).toContain("do not expose the internal id");
  });

  it("keeps permission tools available to main stdio while onboarding-only tools remain scoped", () => {
    const regular = new Set(toolNamesForAdapter("omi-tools-stdio"));
    const onboarding = new Set(toolNamesForAdapter("omi-tools-stdio", { onboarding: true }));
    const screenContext = new Set(toolNamesForAdapter("omi-tools-stdio", { screenContext: true }));

    expect(regular.has("request_permission")).toBe(true);
    expect(regular.has("check_permission_status")).toBe(true);
    expect(regular.has("get_email_insights")).toBe(false);
    expect(regular.has("capture_screen")).toBe(false);
    expect(regular.has("get_work_context")).toBe(false);
    expect(onboarding.has("request_permission")).toBe(true);
    expect(onboarding.has("check_permission_status")).toBe(true);
    expect(onboarding.has("get_email_insights")).toBe(true);
    expect(onboarding.has("capture_screen")).toBe(false);
    expect(screenContext.has("request_permission")).toBe(true);
    expect(screenContext.has("check_permission_status")).toBe(true);
    expect(screenContext.has("get_work_context")).toBe(true);
    expect(screenContext.has("capture_screen")).toBe(true);
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
      enum: ["screen_recording", "microphone", "notifications", "accessibility", "automation", "full_disk_access"],
    });
  });

  it("keeps control-tool cross-field preconditions in runtime validation instead of MCP schemas", () => {
    const tools = mcpToolDefinitionsForAdapter("omi-tools-stdio");
    const inspectArtifacts = tools.find((tool) => tool.name === "inspect_agent_artifacts");

    expect(inspectArtifacts?.inputSchema).toMatchObject({
      type: "object",
      required: [],
    });
    expect(inspectArtifacts?.inputSchema).not.toHaveProperty("anyOf");
    expect(inspectArtifacts?.inputSchema).not.toHaveProperty("oneOf");
    expect(inspectArtifacts?.inputSchema).not.toHaveProperty("allOf");
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
    expect(snapshot.disabled.some((tool) => tool.name === "get_email_insights")).toBe(true);
  });

  it("requires surfaces and capabilityDoc on every manifest entry", () => {
    // spawn_background_agent is the coordinator-RPC-only entrypoint and is
    // deliberately advertised on no agent-facing surface (see sibling test).
    const internalOnlyTools = new Set(["spawn_background_agent"]);
    for (const tool of omiToolManifest) {
      if (!internalOnlyTools.has(tool.name)) {
        expect(tool.surfaces.length, `${tool.name} surfaces`).toBeGreaterThan(0);
      }
      expect(tool.capabilityDoc.title, `${tool.name} capabilityDoc.title`).toBeTruthy();
      expect(tool.capabilityDoc.summary, `${tool.name} capabilityDoc.summary`).toBeTruthy();
      expect(tool.capabilityDoc.bullets.length, `${tool.name} capabilityDoc.bullets`).toBeGreaterThan(0);
    }
  });
});
