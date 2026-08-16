/**
 * INV-CHAT-1 — One shared transcript across surfaces.
 *
 * Behavioral + source ratchet. Surfaces (main_chat, floating_chat / notch) are
 * I/O devices against kernel-owned conversation turns in omi-agentd.sqlite3.
 * Do not introduce a second authoritative chat/history store.
 */
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { SqliteAgentStore } from "../src/runtime/sqlite-store.js";
import { resolveSurfaceSession } from "../src/runtime/surface-session.js";

const RUNTIME_DIR = fileURLToPath(new URL("../src/runtime", import.meta.url));

/** Patterns that would re-introduce a second authoritative transcript store. */
const FORBIDDEN_SOURCE_PATTERNS: { id: string; re: RegExp }[] = [
  {
    id: "second-sqlite-chat-db",
    re: /new\s+Database\s*\(\s*['"`][^'"`]*chat[^'"`]*['"`]/i,
  },
  {
    id: "per-surface-continuity-ring",
    re: /continuityRing|perSurfaceHistory|surfaceOnlyTranscript/i,
  },
  {
    id: "userdefaults-chat-history-authority",
    re: /UserDefaults.*chatHistory|chatHistory.*UserDefaults/i,
  },
];

function walkTsFiles(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    const st = statSync(full);
    if (st.isDirectory()) {
      out.push(...walkTsFiles(full));
    } else if (name.endsWith(".ts") && !name.endsWith(".d.ts")) {
      out.push(full);
    }
  }
  return out;
}

describe("INV-CHAT-1 chat continuity", () => {
  let store: SqliteAgentStore;
  let stateDir: string;

  beforeEach(() => {
    stateDir = mkdtempSync(join(tmpdir(), "omi-chat-continuity-"));
    store = new SqliteAgentStore({ stateDir, reconcileOnOpen: false });
  });

  afterEach(() => {
    store.close();
    rmSync(stateDir, { recursive: true, force: true });
  });

  it("reuses one agent session for repeated main_chat resolves (no second store)", () => {
    const first = resolveSurfaceSession(
      store,
      {
        ownerId: "owner-a",
        surfaceRef: {
          surfaceKind: "main_chat",
          externalRefKind: "chat",
          externalRefId: "default",
        },
      },
      () => 1,
    );
    const second = resolveSurfaceSession(
      store,
      {
        ownerId: "owner-a",
        surfaceRef: {
          surfaceKind: "main_chat",
          externalRefKind: "chat",
          externalRefId: "default",
        },
      },
      () => 2,
    );
    expect(second.agentSessionId).toBe(first.agentSessionId);
    expect(second.conversationId).toBe(first.conversationId);
    expect(store.allRows("SELECT * FROM surface_conversations")).toHaveLength(1);
    expect(store.allRows("SELECT * FROM sessions")).toHaveLength(1);
  });

  it("source ratchet: runtime must not introduce a second chat-history authority", () => {
    const files = walkTsFiles(RUNTIME_DIR);
    expect(files.length).toBeGreaterThan(0);
    const offenders: string[] = [];
    for (const file of files) {
      const text = readFileSync(file, "utf8");
      for (const { id, re } of FORBIDDEN_SOURCE_PATTERNS) {
        if (re.test(text)) {
          offenders.push(`${id}: ${file}`);
        }
      }
    }
    expect(offenders, `INV-CHAT-1 forbidden patterns:\n${offenders.join("\n")}`).toEqual([]);
  });
});
