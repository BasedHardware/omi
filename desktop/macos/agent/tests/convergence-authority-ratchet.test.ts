import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const MACOS_DIR = fileURLToPath(new URL("../..", import.meta.url));
const SWIFT_SOURCES = join(MACOS_DIR, "Desktop", "Sources");
const AGENT_SOURCES = join(MACOS_DIR, "agent", "src");

interface ForbiddenPattern {
  id: string;
  relativePath: string;
  pattern: RegExp;
}

function declarationBody(source: string, declaration: string): string {
  const declarationIndex = source.indexOf(declaration);
  if (declarationIndex < 0) throw new Error(`Missing declaration: ${declaration}`);
  const open = source.indexOf("{", declarationIndex);
  let depth = 0;
  for (let index = open; index < source.length; index += 1) {
    if (source[index] === "{") depth += 1;
    if (source[index] === "}") depth -= 1;
    if (depth === 0) return source.slice(open + 1, index);
  }
  throw new Error(`Unclosed declaration: ${declaration}`);
}

function sourceFiles(root: string): string[] {
  return readdirSync(root).flatMap((name) => {
    const path = join(root, name);
    return statSync(path).isDirectory()
      ? sourceFiles(path)
      : name.endsWith(".ts") || name.endsWith(".swift") ? [path] : [];
  });
}

const FORBIDDEN: ForbiddenPattern[] = [
  {
    id: "chat-provider-backend-writer",
    relativePath: "Desktop/Sources/Providers/ChatProvider.swift",
    pattern: /\.saveMessage\s*\(/,
  },
  {
    id: "chat-provider-save-poll-authority",
    relativePath: "Desktop/Sources/Providers/ChatProvider.swift",
    pattern: /pendingSurfaceTurns|PendingSaveCounter|pollForNewMessages|textPrefix/,
  },
  {
    id: "task-chat-second-writer",
    relativePath: "Desktop/Sources/Rewind/Core/TaskChatMessageStorage.swift",
    pattern: /func\s+(?:saveMessage|updateMessage|markSynced|deleteMessage)\s*\(/,
  },
  {
    id: "swift-capability-authority",
    relativePath: "Desktop/Sources/Chat/AgentRuntimeProcess.swift",
    pattern: /RunToolCapabilityRegistry|tool_capability_(?:register|revoke)|activeRequests\[[^\]]+\].*onToolCall/s,
  },
  {
    id: "swift-tool-semantic-policy-authority",
    relativePath: "Desktop/Sources/Providers/ChatToolExecutor.swift",
    pattern: /permissionExecutionRoute|LocalToolPolicyDecision|localPolicyDecision/,
  },
  {
    id: "legacy-floating-semantic-router",
    relativePath: "Desktop/Sources/FloatingControlBar/AgentPill.swift",
    pattern: /static\s+func\s+classify\s*\(/,
  },
  {
    id: "swift-coordinator-semantic-router",
    relativePath: "Desktop/Sources/Chat/DesktopCoordinatorService.swift",
    pattern: /shouldCreateDispatch\s*\(|normalized\.contains\(\"build\"\)/,
  },
  {
    id: "legacy-floating-route-heuristic",
    relativePath: "Desktop/Sources/FloatingControlBar/FloatingControlBarWindow.swift",
    pattern: /routerCanSkipToChat|AgentDelegationResolver/,
  },
  {
    id: "legacy-realtime-route-heuristic",
    relativePath: "Desktop/Sources/FloatingControlBar/RealtimeHubController.swift",
    pattern: /routerCanSkipToChat|AgentDelegationResolver/,
  },
  {
    id: "swift-voice-second-state-owner",
    relativePath: "Desktop/Sources/FloatingControlBar/PushToTalkManager.swift",
    pattern: /enum\s+PTTState|private\s+var\s+(?:currentVoiceTurnID|finalizationTurnID|liveFinalizationTimeout)[^{\n]*$/m,
  },
  {
    id: "request-supplied-runtime-authority",
    relativePath: "agent/src/protocol.ts",
    pattern: /interface\s+QueryMessage[^\{]*\{[^}]*\b(?:systemPrompt|adapterId|model|cwd|surfaceContextJson)\??\s*:/,
  },
  {
    id: "swift-warmup-profile-authority",
    relativePath: "Desktop/Sources/Chat/AgentRuntimeProcess.swift",
    pattern: /struct\s+WarmupSessionConfig[\s\S]*?\b(?:model|systemPrompt)\s*:/,
  },
  {
    id: "timestamp-journal-cursor",
    relativePath: "agent/src/runtime/conversation-journal.ts",
    pattern: /(?:cursor|highWater)[A-Za-z_]*\s*(?:=|:)[^\n]*(?:createdAt|created_at|timestamp)/i,
  },
  {
    id: "metadata-json-idempotency",
    relativePath: "agent/src/runtime/conversation-journal.ts",
    pattern: /metadataJson[^\n]*(?:idempoten|dedup)|(?:idempoten|dedup)[^\n]*metadataJson/i,
  },
];

describe("#9515 single-owner authority ratchets", () => {
  it("forbids known dual-authority surfaces", () => {
    const violations: string[] = [];
    for (const forbidden of FORBIDDEN) {
      const path = join(MACOS_DIR, forbidden.relativePath);
      if (!existsSync(path)) continue;
      if (forbidden.pattern.test(readFileSync(path, "utf8"))) {
        violations.push(`${forbidden.id}: ${forbidden.relativePath}`);
      }
    }
    expect(violations, violations.join("\n")).toEqual([]);
  });

  it("deletes the standalone delegation resolver", () => {
    expect(
      existsSync(join(SWIFT_SOURCES, "FloatingControlBar", "AgentDelegationResolver.swift")),
    ).toBe(false);
  });

  it("deletes legacy voice and persistence authority owners", () => {
    for (const relativePath of [
      "Desktop/Sources/FloatingControlBar/PTTVoiceOutputCoordinator.swift",
      "Desktop/Sources/FloatingControlBar/RealtimeVoiceTurnOutbox.swift",
      "Desktop/Sources/PendingSaveCounter.swift",
    ]) {
      expect(existsSync(join(MACOS_DIR, relativePath)), relativePath).toBe(false);
    }
  });

  it("keeps the singleton route owner and deletes Swift journal compatibility writers", () => {
    const routerSource = readFileSync(join(AGENT_SOURCES, "runtime", "desktop-intent-router.ts"), "utf8");
    expect(routerSource).not.toMatch(/export\s+function\s+routeDesktopIntent\s*\(/);
    const violations: string[] = [];
    const legacySwiftWriter = /recordSurfaceTurn|projectCrossSurfaceTurn|pill_completion|\[Background agent id=/;
    for (const path of sourceFiles(SWIFT_SOURCES)) {
      if (legacySwiftWriter.test(readFileSync(path, "utf8"))) {
        violations.push(path);
      }
    }
    expect(violations, violations.join("\n")).toEqual([]);
  });

  it("keeps every chat-turn mutation behind the canonical journal", () => {
    const violations: string[] = [];
    const legacyAuthority = /\b(?:recordSurfaceTurn|projectCrossSurfaceTurn|importConversationTurns(?:Backfill|ForSurface)|listUndeliveredConversationTurns|maxConversationTurnCreatedAtMs|lastDeliveredTurnCreatedAtMs|last_delivered_turn_created_at_ms|get_voice_seed_context|voice_seed_context|get_kernel_turn_tail|kernel_turn_tail|clear_owner_surface_state|merge_floating_chat_into_main_chat)\b/;
    for (const path of sourceFiles(AGENT_SOURCES)) {
      const source = readFileSync(path, "utf8");
      if (legacyAuthority.test(source)) violations.push(`legacy chat authority: ${path}`);
      if (
        /\.insertConversationTurn\s*\(/.test(source)
        && !path.endsWith("/runtime/conversation-journal.ts")
        && !path.endsWith("/runtime/sqlite-store.ts")
      ) {
        violations.push(`direct chat writer: ${path}`);
      }
    }
    expect(violations, violations.join("\n")).toEqual([]);
    expect(existsSync(join(AGENT_SOURCES, "runtime", "turn-context.ts"))).toBe(false);
  });

  it("keeps physical backend chat writes and deletes behind the journal driver", () => {
    const violations: string[] = [];
    const physicalMutation = /APIClient\.shared\.(?:saveMessage|deleteMessages|deleteChatSession)\s*\(/;
    for (const path of sourceFiles(SWIFT_SOURCES)) {
      if (path.endsWith("/Chat/KernelJournalBackendSyncDriver.swift")) continue;
      if (physicalMutation.test(readFileSync(path, "utf8"))) violations.push(path);
    }
    expect(violations, violations.join("\n")).toEqual([]);
  });

  it("keeps raw realtime provider tool calls behind the external run authority", () => {
    const source = readFileSync(
      join(SWIFT_SOURCES, "FloatingControlBar", "RealtimeHubController.swift"),
      "utf8",
    );
    const handler = declarationBody(source, "func hubDidRequestTool(");
    expect(handler).toContain("invokeExternallyAuthorizedTool(");
    expect(handler).not.toMatch(/ChatToolExecutor\.execute|APIClient\.shared|NSWorkspace\.shared/);
    expect(source).not.toContain("voiceResponseWatchdog");
  });

  it("never serializes an invocation bearer into a context snapshot", () => {
    const protocolPath = join(AGENT_SOURCES, "protocol.ts");
    const contextPath = join(AGENT_SOURCES, "runtime", "context-snapshot.ts");
    const forbiddenBearer = /\b(?:capabilityRef|invocationId|daemonBootEpoch)\b/;
    const offenders = [
      forbiddenBearer.test(
        declarationBody(readFileSync(protocolPath, "utf8"), "interface ContextSnapshotProjection"),
      ) ? protocolPath : null,
      forbiddenBearer.test(readFileSync(contextPath, "utf8")) ? contextPath : null,
    ].filter((path): path is string => path !== null);
    expect(offenders, offenders.join("\n")).toEqual([]);
  });

  it("requires explicit owners and removal contracts on convergence compatibility readers", () => {
    const contracts = [
      readFileSync(join(SWIFT_SOURCES, "Providers", "ChatProvider.swift"), "utf8"),
      readFileSync(join(SWIFT_SOURCES, "Rewind", "Core", "TaskChatMessageStorage.swift"), "utf8"),
      readFileSync(join(SWIFT_SOURCES, "FloatingControlBar", "LegacyVoiceJournalImporter.swift"), "utf8"),
      readFileSync(join(SWIFT_SOURCES, "Chat", "AgentBridge.swift"), "utf8"),
      readFileSync(join(AGENT_SOURCES, "runtime", "surface-session.ts"), "utf8"),
    ];
    for (const contract of contracts) {
      expect(contract).toMatch(/\bowner\b/);
      expect(contract).toMatch(/removalCondition/);
      expect(contract).toMatch(/removeBy/);
    }
    const surfaceCompatibility = readFileSync(
      join(AGENT_SOURCES, "runtime", "surface-session.ts"),
      "utf8",
    );
    const legacyHandler = readFileSync(join(AGENT_SOURCES, "index.ts"), "utf8");
    expect(surfaceCompatibility).toMatch(/LEGACY_MAIN_CHAT_SESSION_COMPATIBILITY[\s\S]*?owner[\s\S]*?removalCondition[\s\S]*?removeBy/);
    expect(legacyHandler).toContain("LEGACY_MAIN_CHAT_SESSION_COMPATIBILITY");

    for (const path of [
      join(AGENT_SOURCES, "runtime", "sqlite-store.ts"),
      join(AGENT_SOURCES, "runtime", "session-execution-profile.ts"),
    ]) {
      const source = readFileSync(path, "utf8");
      const declarations = [...source.matchAll(/legacyProjection\s*[:',]\s*(?:json_object\()?\s*\{?[\s\S]{0,500}?(?=\n\s*\}?\)?[,;])/g)]
        .map((match) => match[0]);
      expect(declarations.length, path).toBeGreaterThan(0);
      for (const declaration of declarations) {
        expect(declaration, path).toMatch(/owner/);
        expect(declaration, path).toMatch(/removalCondition/);
        expect(declaration, path).toMatch(/removeBy/);
      }
    }
  });

  it("keeps deleted request-derived owner and boolean spawn authority seams absent", () => {
    const control = readFileSync(join(AGENT_SOURCES, "runtime", "control-tools.ts"), "utf8");
    expect(control).not.toMatch(/ActiveControlToolOwnerInput|activeControlToolOwnerId/);
    expect(control).not.toMatch(/ownerIdForRequest|fallbackOwnerId|allowFallbackOwner/);
    expect(control).not.toMatch(/canSpawnAgents/);
  });
});
