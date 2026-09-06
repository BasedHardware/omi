import { describe, expect, it } from "vitest";
import {
  buildToolAvailabilitySnapshot,
  chatFirstToolManifest,
  JIT_PROACTIVITY_READ_TOOL_NAMES,
  mcpToolDefinitionsForAdapter,
  normalizeOmiToolName,
  omiToolManifest,
  toolNamesForAdapter,
  toolsForAdapter,
} from "../src/runtime/omi-tool-manifest.js";

describe("omi tool manifest", () => {
  it("registers canonical goal creation for Chat-first main Chat", () => {
    const tool = chatFirstToolManifest.find((entry) => entry.name === "create_canonical_goal");

    expect(tool).toMatchObject({
      executor: { kind: "swiftTool" },
      surfaces: ["desktop_chat"],
      annotations: expect.objectContaining({ readOnlyHint: false }),
    });
    expect(tool?.inputSchema.required).toEqual(["title", "desired_outcome"]);
  });

  it("projects create_memory only to the coordinator's typed chat surfaces", () => {
    const mainChat = toolsForAdapter("omi-tools-stdio", {
      surfaceKind: "main_chat",
      executionRole: "coordinator",
    });
    const tool = mainChat.find((entry) => entry.name === "create_memory");

    expect(tool).toMatchObject({
      surfaces: ["desktop_chat"],
      executor: { kind: "swiftTool", executorName: "chatToolExecutor" },
      annotations: { readOnlyHint: false, idempotentHint: false },
    });
    expect(tool?.inputSchema).toEqual({
      type: "object",
      properties: {
        content: {
          type: "string",
          description:
            "A clean standalone fact to save as a short-term memory. Strip the remember/save command; light rewrite is OK. Do not invent facts.",
        },
      },
      required: ["content"],
      additionalProperties: false,
    });
    expect(tool?.voice).toBeUndefined();
    expect(toolNamesForAdapter("omi-tools-stdio", { surfaceKind: "floating_chat", executionRole: "coordinator" }))
      .toContain("create_memory");
    expect(toolNamesForAdapter("omi-tools-stdio", { surfaceKind: "realtime_voice", executionRole: "coordinator" }))
      .not.toContain("create_memory");
    expect(toolNamesForAdapter("omi-tools-stdio", { surfaceKind: "task_chat", executionRole: "coordinator" }))
      .not.toContain("create_memory");
    expect(toolNamesForAdapter("omi-tools-stdio", { surfaceKind: "main_chat", executionRole: "leaf" }))
      .not.toContain("create_memory");
  });
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
      "get_work_context",
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
      "search_skills",
      "save_knowledge_graph",
      "get_conversations",
      "search_conversations",
      "get_memories",
      "search_memories",
      "get_action_items",
      "create_action_item",
      "create_context_reminder",
      "update_action_item",
      "capture_screen",
      "check_permission_status",
      "request_permission",
      "web_search",
      "screenshot",
    ]);
    expect(toolNamesForAdapter("pi-mono")).not.toContain("resolve_desktop_dispatch");
  });

  it("keeps the realtime screenshot executor capability-registered", () => {
    const screenshot = toolsForAdapter("pi-mono").find((tool) => tool.name === "screenshot");

    expect(screenshot?.surfaces).toEqual(["realtime_voice"]);
    expect(screenshot?.executor).toEqual({ kind: "swiftTool", executorName: "realtimeHub" });
  });

  it("keeps think_deeper on exactly two thinking levels with a normal default", () => {
    const thinkDeeper = omiToolManifest.find((tool) => tool.name === "think_deeper");

    const thinking = thinkDeeper?.inputSchema.properties.thinking as Record<string, unknown>;
    expect(thinking?.type).toBe("string");
    expect(thinking?.enum).toEqual(["normal", "heavy"]);
    expect(thinking?.default).toBe("normal");
    expect(thinkDeeper?.inputSchema.required).toEqual(["query"]);

    const overrideThinking = thinkDeeper?.voice?.schemaOverride?.properties.thinking as Record<
      string,
      unknown
    >;
    expect(overrideThinking?.enum).toEqual(["normal", "heavy"]);
    expect(overrideThinking?.default).toBe("normal");
    expect(String(overrideThinking?.description)).toContain("high reasoning");

    // The realtime card must tell the PTT model when to pick heavy and that
    // viewed screenshots are forwarded automatically.
    const description = String(thinkDeeper?.voice?.realtimeDescription);
    expect(description).toContain("thinking='heavy'");
    expect(description).toContain("forwarded to the thinking agent automatically");
  });

  it("keeps current-screen evidence live and work context historical", () => {
    const workContext = toolsForAdapter("pi-mono").find((tool) => tool.name === "get_work_context");
    const captureScreen = toolsForAdapter("pi-mono").find((tool) => tool.name === "capture_screen");
    const requestPermission = toolsForAdapter("pi-mono").find((tool) => tool.name === "request_permission");

    expect(workContext?.promptGuidelines?.join("\n")).toContain("not for direct current-screen questions");
    expect(workContext?.promptGuidelines?.join("\n")).toContain("historical unless this turn separately attached a live image");
    expect(captureScreen?.promptGuidelines?.join("\n")).toContain("capture a live image");
    expect(captureScreen?.promptGuidelines?.join("\n")).not.toContain("get_work_context first");
    expect(captureScreen?.promptGuidelines?.join("\n")).toContain("requires explicit approval");
    expect(requestPermission?.promptGuidelines?.join("\n")).toContain("current user message explicitly requests one named permission");
  });

  it("gives recent-work retrieval explicit precedence over overlapping screen tools", () => {
    const tools = toolsForAdapter("pi-mono");
    const workContext = tools.find((tool) => tool.name === "get_work_context");
    const executeSql = tools.find((tool) => tool.name === "execute_sql");
    const semanticSearch = tools.find((tool) => tool.name === "semantic_search");

    expect(tools[0]?.name).toBe("get_work_context");
    expect(workContext?.description).toContain("Call get_work_context before semantic_search or execute_sql");
    expect(executeSql?.description).toContain("call get_work_context first");
    expect(executeSql?.description).toContain("context_visits(handlesJson)");
    expect(executeSql?.description).toContain("Raw ocrText columns are refused");
    expect(semanticSearch?.description).toContain("after get_work_context cannot identify");
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
      enum: ["openclaw", "hermes"],
    });
    expect(spawnAgent?.promptGuidelines?.join("\n")).toContain("provider='openclaw'");
    expect(spawnAgent?.promptGuidelines?.join("\n")).toContain("provider='hermes'");
  });

  it("leaves explicit provider delegation to the primary model loop", () => {
    const primarySpawn = toolsForAdapter("pi-mono", { executionRole: "coordinator" })
      .find((tool) => tool.name === "spawn_agent");
    const leafTools = toolNamesForAdapter("pi-mono", { executionRole: "leaf" });

    expect(primarySpawn?.promptGuidelines?.join("\n")).toContain(
      "The primary coordinator decides in its model loop whether to call spawn_agent.",
    );
    expect(primarySpawn?.promptGuidelines?.join("\n")).toContain(
      "do not delegate that instruction to another agent",
    );
    expect(leafTools).not.toContain("spawn_agent");
  });

  it("guides realtime child-result retrieval without exposing internal ids", () => {
    const list = omiToolManifest.find((tool) => tool.name === "list_agent_sessions");
    const run = omiToolManifest.find((tool) => tool.name === "get_agent_run");

    expect(list?.promptGuidelines?.join("\n")).toContain("do not infer run completion from session status");
    expect(list?.voice?.realtimeDescription).toContain("omit status filters");
    expect(list?.voice?.realtimeDescription).toContain("latestRun.finalText");
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

  it("documents exact conversation IDs and share links as search inputs", () => {
    const tool = omiToolManifest.find((entry) => entry.name === "search_conversations");

    expect(tool?.capabilityDoc.summary).toContain("exact canonical ID/share link");
    expect(tool?.capabilityDoc.bullets.join(" ")).toContain("canonical conversation UUID");
    expect(tool?.inputSchema.properties.query.description).toContain("canonical UUID");
  });

  it("advertises optional positional parameters for execute_sql", () => {
    const executeSql = mcpToolDefinitionsForAdapter("omi-tools-stdio").find(
      (tool) => tool.name === "execute_sql",
    );

    expect(executeSql?.inputSchema.properties.parameters).toEqual({
      type: "array",
      items: { type: "string" },
      description: "Optional positional values bound to ? placeholders in query. Use this instead of interpolating values into SQL literals.",
    });
    expect(executeSql?.inputSchema.required).toEqual(["query"]);
  });

  it("keeps the capability-off stdio manifest byte-stable and never leaks the chat-first tool", () => {
    const legacyBytes = JSON.stringify(mcpToolDefinitionsForAdapter("omi-tools-stdio"));
    const capabilityOffBytes = JSON.stringify(mcpToolDefinitionsForAdapter("omi-tools-stdio", {
      surfaceKind: "main_chat", chatFirstUi: false, controlGeneration: 7,
    }));
    const nonMainBytes = JSON.stringify(mcpToolDefinitionsForAdapter("omi-tools-stdio", {
      surfaceKind: "floating_chat", chatFirstUi: true, controlGeneration: 7,
    }));

    expect(capabilityOffBytes).toBe(legacyBytes);
    expect(nonMainBytes).toBe(legacyBytes);
    expect(capabilityOffBytes).not.toContain("render_chat_blocks");
    expect(capabilityOffBytes).not.toContain("get_canonical_goals");
    expect(capabilityOffBytes).not.toContain("search_chat_history");
  });

  it("exposes chat-first tools only to the authorized main-chat stdio projection", () => {
    const enabled = mcpToolDefinitionsForAdapter("omi-tools-stdio", {
      surfaceKind: "main_chat", chatFirstUi: true, controlGeneration: 7,
    });
    const snapshot = buildToolAvailabilitySnapshot("omi-tools-stdio", {
      surfaceKind: "main_chat", chatFirstUi: true, controlGeneration: 7,
    });

    expect(enabled.map((tool) => tool.name)).toContain("render_chat_blocks");
    expect(enabled.map((tool) => tool.name)).toContain("get_canonical_goals");
    expect(enabled.map((tool) => tool.name)).toContain("search_chat_history");
    expect(snapshot.advertisedToolNames).toContain("render_chat_blocks");
    expect(snapshot.advertisedToolNames).toContain("get_canonical_goals");
    expect(snapshot.advertisedToolNames).toContain("search_chat_history");
    expect(snapshot.advertisedToolNames).toContain("show_rewind_evidence");
    expect(snapshot.manifestDigest).not.toBe(buildToolAvailabilitySnapshot("omi-tools-stdio").manifestDigest);
    expect(toolNamesForAdapter("pi-mono", {
      surfaceKind: "main_chat", chatFirstUi: true, controlGeneration: 7,
    })).toEqual(expect.arrayContaining(["get_canonical_goals", "render_chat_blocks", "search_chat_history", "show_rewind_evidence"]));
    // The tool is for entities the user asked for or acted on, not for every
    // entity a turn happened to read. The old "render whenever you retrieve"
    // wording stacked three conversation cards above a summary that had merely
    // cited those conversations.
    const renderDescription = enabled.find((tool) => tool.name === "render_chat_blocks")?.description ?? "";
    expect(renderDescription).toContain("when the entity IS the answer");
    expect(renderDescription).toContain("sources belong in citations");
    expect(renderDescription).toContain("Render at most three");
    expect(renderDescription).not.toContain("whenever you retrieve");
    expect(enabled.find((tool) => tool.name === "render_chat_blocks")?.description).toContain(
      "never use a local SQLite/execute_sql numeric row ID",
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
    expect(normalizeOmiToolName("local-agent-api", "look_at_frame")).toEqual({
      canonicalName: "get_screenshot",
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

  describe("JIT knowledge-ledger tools", () => {
    const READ_TOOLS = ["search_knowledge", "read_playbook", "search_historical_facts", "get_entity_timeline_tool"];
    const WRITE_TOOLS = ["save_playbook", "create_standing_trigger", "close_fact"];
    const ALL_LEDGER_TOOLS = [...READ_TOOLS, ...WRITE_TOOLS];

    it("are hidden from every adapter by default (fail closed)", () => {
      for (const adapterId of ["pi-mono", "omi-tools-stdio"] as const) {
        const names = toolNamesForAdapter(adapterId);
        for (const toolName of ALL_LEDGER_TOOLS) {
          expect(names, `${adapterId} should not advertise ${toolName} by default`).not.toContain(toolName);
        }
      }
      // Explicitly false, and every other context flag on, is still hidden.
      const names = toolNamesForAdapter("pi-mono", {
        jitKnowledgeToolsEnabled: false,
        onboarding: true,
        screenContext: true,
      });
      for (const toolName of ALL_LEDGER_TOOLS) {
        expect(names).not.toContain(toolName);
      }
    });

    it("are advertised to pi-mono and omi-tools-stdio once the JIT rollout gate is on", () => {
      for (const adapterId of ["pi-mono", "omi-tools-stdio"] as const) {
        const names = toolNamesForAdapter(adapterId, { jitKnowledgeToolsEnabled: true });
        for (const toolName of ALL_LEDGER_TOOLS) {
          expect(names, `${adapterId} should advertise ${toolName} when gated on`).toContain(toolName);
        }
      }
    });

    it("projects only read-only ledger retrieval for a bounded proactive turn", () => {
      const tools = mcpToolDefinitionsForAdapter("omi-tools-stdio", {
        surfaceKind: "service",
        executionRole: "coordinator",
        jitKnowledgeToolsEnabled: true,
        jitProactivity: true,
      });

      expect(tools.map((tool) => tool.name)).toEqual([...JIT_PROACTIVITY_READ_TOOL_NAMES]);
      expect(JSON.stringify(tools)).not.toContain("create_standing_trigger");
      expect(JSON.stringify(tools)).not.toContain("create_memory");
      expect(tools.every((tool) => READ_TOOLS.includes(tool.name))).toBe(true);
    });

    it("declares a swiftTool/chatToolExecutor dispatch for every ledger tool", () => {
      for (const toolName of ALL_LEDGER_TOOLS) {
        const tool = omiToolManifest.find((entry) => entry.name === toolName);
        expect(tool, `${toolName} manifest entry`).toBeTruthy();
        expect(tool?.executor).toEqual({ kind: "swiftTool", executorName: "chatToolExecutor" });
        expect(tool?.surfaces).toEqual(["desktop_chat"]);
        expect(tool?.latency).toBe("fast network");
        expect(tool?.intendedForAgents).toBe(true);
      }
    });

    it("marks the four read tools read-only and the three write verbs as writes", () => {
      for (const toolName of READ_TOOLS) {
        const tool = omiToolManifest.find((entry) => entry.name === toolName);
        expect(tool?.annotations.readOnlyHint, `${toolName} readOnlyHint`).toBe(true);
      }
      for (const toolName of WRITE_TOOLS) {
        const tool = omiToolManifest.find((entry) => entry.name === toolName);
        expect(tool?.annotations.readOnlyHint, `${toolName} readOnlyHint`).toBe(false);
      }
    });

    it("keeps faithful, minimal input schemas matching the backend tool contracts", () => {
      const enabled = toolsForAdapter("pi-mono", { jitKnowledgeToolsEnabled: true });
      const byName = Object.fromEntries(enabled.map((tool) => [tool.name, tool]));

      expect(byName.search_knowledge.inputSchema.required).toEqual(["query"]);
      expect(byName.search_knowledge.inputSchema.properties).toHaveProperty("kinds");
      expect(byName.search_knowledge.inputSchema.properties).toHaveProperty("limit");

      expect(byName.read_playbook.inputSchema.required).toEqual(["memory_id"]);

      expect(byName.search_historical_facts.inputSchema.required).toEqual(["query"]);
      expect(byName.search_historical_facts.inputSchema.properties).toHaveProperty("include_rejected");

      expect(byName.get_entity_timeline_tool.inputSchema.required).toEqual(["entity"]);
      expect(byName.get_entity_timeline_tool.inputSchema.properties).toHaveProperty("sources");

      expect(byName.save_playbook.inputSchema.required).toEqual(["description", "body"]);
      expect(byName.create_standing_trigger.inputSchema.required).toEqual(["description", "condition"]);
      expect(byName.close_fact.inputSchema.required).toEqual(["memory_id", "reason"]);
    });

    it("describes the typed backend standing-trigger condition contract", () => {
      const tool = toolsForAdapter("pi-mono", { jitKnowledgeToolsEnabled: true }).find(
        (entry) => entry.name === "create_standing_trigger",
      );
      const condition = tool?.inputSchema.properties.condition as Record<string, any>;
      const properties = condition.properties as Record<string, any>;

      expect(condition.additionalProperties).toBe(false);
      expect(condition.anyOf).toEqual([
        { required: ["entity_aliases"] },
        { required: ["keywords"] },
        { required: ["regex"] },
        { required: ["apps"] },
        { required: ["windows"] },
        { required: ["time"] },
        { required: ["calendar"] },
      ]);
      expect(properties.match_mode.enum).toEqual(["all", "any"]);
      expect(properties.entity_aliases.additionalProperties.items.type).toBe("string");
      expect(properties.keywords.items.type).toBe("string");
      expect(properties.keywords.minItems).toBe(1);
      expect(properties.regex.items.type).toBe("string");
      expect(properties.regex.minItems).toBe(1);
      expect(properties.apps.minItems).toBe(1);
      expect(properties.windows.minItems).toBe(1);
      expect(properties.time.required).toEqual(["start", "end"]);
      expect(properties.calendar.anyOf).toEqual([
        { required: ["event_keywords"] },
        { required: ["event_types"] },
      ]);
      expect(properties.calendar.properties.event_keywords.minItems).toBe(1);
      expect(properties.calendar.properties.event_types.minItems).toBe(1);
      expect(condition.examples).toEqual([
        { keywords: ["incident"] },
        { apps: ["Slack"], keywords: ["budget"] },
        { time: { start: "09:00", end: "17:00", timezone: "UTC" } },
      ]);
    });

    it("steers durable facts, playbooks, standing intent, and closures away from generic tools", () => {
      const createMemory = omiToolManifest.find((entry) => entry.name === "create_memory");
      const searchKnowledge = omiToolManifest.find((entry) => entry.name === "search_knowledge");
      const savePlaybook = omiToolManifest.find((entry) => entry.name === "save_playbook");
      const createStandingTrigger = omiToolManifest.find((entry) => entry.name === "create_standing_trigger");
      const closeFact = omiToolManifest.find((entry) => entry.name === "close_fact");

      expect(createMemory?.promptGuidelines?.join("\n")).toContain("knowledge-ledger tools");
      expect(searchKnowledge?.promptGuidelines?.join("\n")).toContain("rather than create_memory or a filesystem document");
      expect(savePlaybook?.promptGuidelines?.join("\n")).toContain("not a filesystem document and not create_memory");
      expect(createStandingTrigger?.promptGuidelines?.join("\n")).toContain("explicit standing-intent request");
      expect(closeFact?.promptGuidelines?.join("\n")).toContain("nothing should replace the closed fact");
    });
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

describe("native component guidance", () => {
  const byName = (name: string) =>
    [...omiToolManifest, ...chatFirstToolManifest].find((tool) => tool.name === name);

  it("teaches conversation and memory retrieval to render the component when the entity is the answer", () => {
    expect(byName("get_conversations")?.promptGuidelines?.join("\n")).toContain("captureLink");
    expect(byName("get_conversations")?.promptGuidelines?.join("\n")).toContain("'pick one'");
    expect(byName("search_conversations")?.promptGuidelines?.join("\n")).toContain("captureLink");
    expect(byName("get_memories")?.promptGuidelines?.join("\n")).toContain("memoryLink");
    expect(byName("search_memories")?.promptGuidelines?.join("\n")).toContain("memoryLink");
    expect(byName("get_action_items")?.promptGuidelines?.join("\n")).toContain("a count, never their names");
  });

  it("makes the component the default for anything Omi draws natively, with prose reserved for reading", () => {
    const lead = byName("render_chat_blocks")?.promptGuidelines?.[0] ?? "";
    expect(lead).toContain("Default to a component");
    expect(lead).toContain("a summary, a recap, an analysis, a comparison, a count");
    expect(lead).toContain("a bold title with a citation number is not a substitute");
  });
});
