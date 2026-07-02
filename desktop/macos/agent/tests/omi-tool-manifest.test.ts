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
      "setup_agent_provider",
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
    expect(spawnAgent?.promptGuidelines?.join("\n")).toContain("'hermes'");
    expect(spawnAgent?.promptGuidelines?.join("\n")).toContain("'codex'");
  });

  it("gates provider install assist on explicit user consent", () => {
    const setupProvider = toolsForAdapter("pi-mono").find((tool) => tool.name === "setup_agent_provider");
    const guidelines = setupProvider?.promptGuidelines?.join("\n") ?? "";

    expect(setupProvider?.inputSchema.properties.provider).toMatchObject({
      enum: ["openclaw", "hermes", "codex"],
    });
    expect(setupProvider?.inputSchema.required).toEqual(["provider"]);
    expect(guidelines).toContain("ONLY after the user explicitly agrees");
    expect(guidelines).toContain("never unprompted");
    expect(guidelines).toContain("after the user confirms in the native dialog");
    expect(guidelines).toContain("interactive login/onboarding steps are left to the user");
    expect(setupProvider?.description).toContain("native confirmation dialog");
  });

  it("never exposes provider installs to external MCP clients", () => {
    // setup_agent_provider triggers software installs on the user's machine.
    // It must stay pi-mono only: the omi-tools-stdio projection is served to
    // EXTERNAL MCP clients, which have no in-conversation consent path.
    expect(toolNamesForAdapter("omi-tools-stdio")).not.toContain("setup_agent_provider");
    expect(toolNamesForAdapter("omi-tools-stdio", { onboarding: true })).not.toContain("setup_agent_provider");
    expect(mcpToolDefinitionsForAdapter("omi-tools-stdio").map((tool) => tool.name)).not.toContain(
      "setup_agent_provider",
    );
    expect(toolNamesForAdapter("pi-mono")).toContain("setup_agent_provider");
  });

  it("guides provider selection by strengths with the default agent as fallback", () => {
    const spawnAgent = toolsForAdapter("pi-mono").find((tool) => tool.name === "spawn_agent");
    const guidelines = spawnAgent?.promptGuidelines?.join("\n") ?? "";

    expect(guidelines).toContain("When the user does not name an agent");
    expect(guidelines).toContain("OpenClaw: messaging/channels (WhatsApp, Telegram, Discord)");
    expect(guidelines).toContain("Hermes: long-running or recurring automations");
    expect(guidelines).toContain("Codex: coding, repositories, and terminal/software-engineering work");
    expect(guidelines).toContain("omit provider to use Omi's default agent");
    expect(guidelines).toContain("When the user names an agent, always use exactly that one");
    expect(guidelines).toContain("offer to install it via setup_agent_provider");
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

  it("preserves control-tool schema preconditions in MCP projections", () => {
    const tools = mcpToolDefinitionsForAdapter("omi-tools-stdio");
    const inspectArtifacts = tools.find((tool) => tool.name === "inspect_agent_artifacts");
    const delegateAgent = tools.find((tool) => tool.name === "delegate_agent");

    expect(inspectArtifacts?.inputSchema.anyOf).toEqual([
      { required: ["artifactId"] },
      { required: ["sessionId"] },
      { required: ["runId"] },
      { required: ["attemptId"] },
    ]);
    expect(delegateAgent?.inputSchema.allOf).toEqual([
      {
        if: { properties: { mode: { const: "continue" } }, required: ["mode"] },
        then: { required: ["childSessionId"] },
      },
    ]);
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
