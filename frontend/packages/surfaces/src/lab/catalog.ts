import { FIXTURE_STATES as MEMORY_STATES } from "../production/memory-fixtures.js";
import { CONVERSATION_FIXTURE_STATES } from "../production/conversation-fixtures.js";
import { FIXTURE_STATES as TASK_STATES } from "../production/task-fixtures.js";
import { PROPOSITION_FIXTURE_STATES } from "../production/proposition-fixtures.js";
import { CHAT_FIXTURE_STATES } from "../production/chat-fixtures.js";
import { SETTINGS_FIXTURE_STATES } from "../production/settings-fixtures.js";
import { POLISH_EVIDENCE_STATES } from "../production/polish-evidence-fixtures.js";

export type SurfaceId =
  | "memories"
  | "memories-platform"
  | "conversations"
  | "conversation-detail"
  | "folders"
  | "tasks"
  | "chat"
  | "listen"
  | "settings";

export type LabPlatform = "mobile" | "desktop";
export type LabCatalogName = "lab" | "matrix";

export type SurfaceDefinition = {
  id: SurfaceId;
  label: string;
  description: string;
  states: readonly string[];
  polishDomain?: keyof typeof POLISH_EVIDENCE_STATES;
};

export const LAB_PLATFORMS: readonly LabPlatform[] = ["mobile", "desktop"];
export const LAB_LOCALES: readonly string[] = ["en-US"];

export const LAB_VIEWPORTS: Readonly<Record<LabPlatform, { width: number; height: number }>> = {
  mobile: { width: 390, height: 844 },
  desktop: { width: 1280, height: 800 },
};

export const LAB_ORIGIN = "http://127.0.0.1:4650";

export const SURFACES: readonly SurfaceDefinition[] = [
  { id: "memories", label: "Memories", description: "Saved context, editing, provenance, and sync recovery", states: MEMORY_STATES },
  { id: "conversations", label: "Conversations", description: "Library rows, filters, locks, and discarded records", states: CONVERSATION_FIXTURE_STATES },
  { id: "conversation-detail", label: "Conversation detail", description: "Selected-row summary, organization, and visibility", states: CONVERSATION_FIXTURE_STATES },
  { id: "tasks", label: "Tasks", description: "Today, Tomorrow, Later, keyboard flow, and queue recovery", states: TASK_STATES },
  { id: "memories-platform", label: "Memories (platform)", description: "Synthesized propositions, lineage, and honest recall completeness", states: PROPOSITION_FIXTURE_STATES },
  { id: "chat", label: "Chat", description: "Server-authoritative mirror, streaming, echo reconcile, and attachment cap", states: CHAT_FIXTURE_STATES },
  { id: "settings", label: "Settings", description: "Identity, appearance, and the entitlement upsell", states: SETTINGS_FIXTURE_STATES },
  { id: "folders", label: "Folders", description: "Read-only organization and filtered conversation entry", states: POLISH_EVIDENCE_STATES.folders, polishDomain: "folders" },
  { id: "listen", label: "Listen", description: "Capture preflight, backlog, transcript, and recovery truth", states: POLISH_EVIDENCE_STATES.listen, polishDomain: "listen" },
];

export const MATRIX_SURFACES: readonly SurfaceDefinition[] = [
  { id: "memories-platform", label: "Memories", description: "Canonical polish lifecycle evidence", states: POLISH_EVIDENCE_STATES.memories, polishDomain: "memories" },
  { id: "tasks", label: "Tasks", description: "Canonical polish lifecycle evidence", states: POLISH_EVIDENCE_STATES.tasks, polishDomain: "tasks" },
  { id: "conversations", label: "Conversations", description: "Canonical polish lifecycle evidence", states: POLISH_EVIDENCE_STATES.conversations, polishDomain: "conversations" },
  { id: "folders", label: "Folders", description: "Canonical polish lifecycle evidence", states: POLISH_EVIDENCE_STATES.folders, polishDomain: "folders" },
  { id: "chat", label: "Chat", description: "Canonical polish lifecycle evidence", states: POLISH_EVIDENCE_STATES.chat, polishDomain: "chat" },
  { id: "listen", label: "Listen", description: "Canonical polish lifecycle evidence", states: POLISH_EVIDENCE_STATES.listen, polishDomain: "listen" },
  { id: "settings", label: "Settings", description: "Canonical polish lifecycle evidence", states: POLISH_EVIDENCE_STATES.settings, polishDomain: "settings" },
];

export type LabStateEntry = {
  id: string;
  url: string;
  path: string;
  surface: SurfaceId;
  state: string;
  platform: LabPlatform;
  locale: string;
  polish: boolean;
  catalogs: readonly LabCatalogName[];
  viewport: { width: number; height: number };
  shell: { reachable: boolean; reason: string | null };
};

export function fixtureHref(surface: SurfaceDefinition, state: string, platform: LabPlatform, locale: string): string {
  const polish = surface.polishDomain !== undefined;
  const params = new URLSearchParams({ qa: surface.id, state, platform, locale, ...(polish ? { polish: "1" } : {}) });
  return `?${params.toString()}`;
}

function stateId(surface: SurfaceId, state: string, platform: LabPlatform, locale: string, polish: boolean): string {
  return `${surface}.${state}.${platform}.${locale}.${polish ? "polish" : "raw"}`;
}

function shellReachability(platform: LabPlatform): LabStateEntry["shell"] {
  if (platform === "mobile") {
    return {
      reachable: false,
      reason: "macOS fixture windows cannot be 390×844; GlassHost minimum width is 760px, so true mobile chrome is browser-only.",
    };
  }
  return { reachable: true, reason: null };
}

export function enumerateLabStates(origin = LAB_ORIGIN): LabStateEntry[] {
  const byKey = new Map<string, LabStateEntry>();
  const catalogs: ReadonlyArray<readonly [LabCatalogName, readonly SurfaceDefinition[]]> = [
    ["lab", SURFACES],
    ["matrix", MATRIX_SURFACES],
  ];
  for (const [catalog, surfaces] of catalogs) {
    for (const surface of surfaces) {
      const polish = surface.polishDomain !== undefined;
      for (const state of surface.states) {
        for (const platform of LAB_PLATFORMS) {
          for (const locale of LAB_LOCALES) {
            const path = fixtureHref(surface, state, platform, locale);
            const key = path.slice(1);
            const existing = byKey.get(key);
            if (existing) {
              if (!existing.catalogs.includes(catalog)) {
                byKey.set(key, { ...existing, catalogs: [...existing.catalogs, catalog] });
              }
              continue;
            }
            const id = stateId(surface.id, state, platform, locale, polish);
            byKey.set(key, {
              id,
              url: `${origin}/${path}`,
              path,
              surface: surface.id,
              state,
              platform,
              locale,
              polish,
              catalogs: [catalog],
              viewport: LAB_VIEWPORTS[platform],
              shell: shellReachability(platform),
            });
          }
        }
      }
    }
  }
  return [...byKey.values()].sort((left, right) => left.id.localeCompare(right.id));
}

export function labManifest(origin = LAB_ORIGIN): {
  schema: "omi.ui-harness.manifest/v1";
  origin: string;
  platforms: readonly LabPlatform[];
  locales: readonly string[];
  viewports: typeof LAB_VIEWPORTS;
  count: number;
  states: LabStateEntry[];
} {
  const states = enumerateLabStates(origin);
  return {
    schema: "omi.ui-harness.manifest/v1",
    origin,
    platforms: LAB_PLATFORMS,
    locales: LAB_LOCALES,
    viewports: LAB_VIEWPORTS,
    count: states.length,
    states,
  };
}
