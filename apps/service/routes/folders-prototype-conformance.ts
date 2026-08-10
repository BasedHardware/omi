import { pathToFileURL } from "node:url";
import { Database } from "bun:sqlite";

import { createLocalService } from "../app-facing";
import type { ConversationRecord } from "../stores/conversations-store";
import type { FolderRecord } from "../stores/folders-store";

const prototypePath = process.argv[2];
if (prototypePath === undefined) {
  process.stderr.write("usage: folders-prototype-conformance.ts <qa-api-server/server.mjs>\n");
  process.exit(2);
}

interface PrototypeApi {
  readonly state: {
    folders: FolderRecord[];
    conversations: ConversationRecord[];
  };
  start(): Promise<{ readonly host: string; readonly port: number }>;
  close(): Promise<void>;
}

interface PrototypeModule {
  readonly QA_BEARER_TOKEN: string;
  createQaApiServer(options: { readonly port: number }): PrototypeApi;
}

interface Result {
  readonly status: number;
  readonly body: unknown;
}

interface Step {
  readonly label: string;
  readonly path: string;
  readonly init?: RequestInit;
  readonly authenticated?: boolean;
}

interface Scenario {
  readonly label: string;
  readonly setup?: (prototype: PrototypeApi, service: ReturnType<typeof createLocalService>) => void;
  readonly steps: readonly Step[];
}

const CREATED = "2026-08-03T12:00:00.000Z";
const MUTATED = "2026-08-07T12:00:00.000Z";
const OWNER = "folder-conformance-owner";
const json = (method: string, value: unknown): RequestInit => ({
  method,
  headers: { "content-type": "application/json" },
  body: JSON.stringify(value),
});

const folder = (id: string, overrides: Partial<FolderRecord> = {}): FolderRecord => ({
  id,
  name: id,
  description: null,
  color: "#6B7280",
  icon: "folder",
  created_at: CREATED,
  updated_at: MUTATED,
  order: 0,
  is_default: false,
  is_system: false,
  ...overrides,
});

const conversation = (folderId: string): ConversationRecord => ({
  id: "quiet-chat-qa",
  structured: {
    title: "QA bridge check",
    overview: "A deterministic conversation for shell acceptance.",
  },
  created_at: CREATED,
  updated_at: MUTATED,
  started_at: "2026-08-07T11:50:00.000Z",
  finished_at: MUTATED,
  source: "omi",
  status: "completed",
  discarded: false,
  starred: false,
  visibility: "private",
  is_locked: false,
  folder_id: folderId,
});

const parse = async (response: Response): Promise<Result> => {
  const text = await response.text();
  return { status: response.status, body: text.length === 0 ? null : JSON.parse(text) as unknown };
};

const same = (left: unknown, right: unknown): boolean =>
  JSON.stringify(left) === JSON.stringify(right);

const prototypeModule = await import(pathToFileURL(prototypePath).href) as PrototypeModule;
const prototype = prototypeModule.createQaApiServer({ port: 0 });
const address = await prototype.start();
const prototypeBase = `http://${address.host}:${address.port}`;
const db = new Database(":memory:");
const service = createLocalService({
  db,
  ownerAccountId: OWNER,
  memoryCount: 1,
  accountTimezone: "UTC",
  devSecretLabel: "folder-prototype-conformance",
});

const prototypeRequest = (step: Step): Promise<Response> => fetch(`${prototypeBase}${step.path}`, {
  ...step.init,
  headers: {
    ...(step.authenticated === false
      ? {}
      : { authorization: `Bearer ${prototypeModule.QA_BEARER_TOKEN}` }),
    ...(step.init?.headers ?? {}),
  },
});

const serviceRequest = async (step: Step): Promise<Response> => service.app.request(step.path, {
  ...step.init,
  headers: {
    ...(step.authenticated === false ? {} : { authorization: `Bearer ${service.devToken}` }),
    ...(step.init?.headers ?? {}),
  },
});

const scenarios: readonly Scenario[] = [
  { label: "GET bare array ignores pagination", steps: [{ label: "GET", path: "/v1/folders?limit=1&offset=1" }] },
  { label: "GET unauthorized", steps: [{ label: "GET", path: "/v1/folders", authenticated: false }] },
  { label: "POST invalid JSON", steps: [{ label: "POST", path: "/v1/folders", init: { method: "POST", body: "{" } }] },
  { label: "POST null body", steps: [{ label: "POST", path: "/v1/folders", init: json("POST", null) }] },
  { label: "POST missing name", steps: [{ label: "POST", path: "/v1/folders", init: json("POST", {}) }] },
  { label: "POST whitespace name", steps: [{ label: "POST", path: "/v1/folders", init: json("POST", { name: "   " }) }] },
  {
    label: "POST defaults and id-only response",
    steps: [
      { label: "POST", path: "/v1/folders", init: json("POST", { name: "  Preserved  ", description: 7, color: null, icon: false }) },
      { label: "GET-after-POST", path: "/v1/folders" },
    ],
  },
  {
    label: "POST deterministic ids and order",
    steps: [
      { label: "POST-1", path: "/v1/folders", init: json("POST", { name: "First" }) },
      { label: "POST-2", path: "/v1/folders", init: json("POST", { name: "Second" }) },
      { label: "GET-after-two", path: "/v1/folders" },
    ],
  },
  { label: "PATCH missing before JSON parse", steps: [{ label: "PATCH", path: "/v1/folders/missing", init: { method: "PATCH", body: "{" } }] },
  { label: "PATCH invalid JSON", steps: [{ label: "PATCH", path: "/v1/folders/work-folder-qa", init: { method: "PATCH", body: "{" } }] },
  { label: "PATCH null body", steps: [{ label: "PATCH", path: "/v1/folders/work-folder-qa", init: json("PATCH", null) }] },
  {
    label: "PATCH five-key untyped merge",
    steps: [{
      label: "PATCH",
      path: "/v1/folders/work-folder-qa",
      init: json("PATCH", {
        name: null,
        description: { nested: true },
        color: false,
        icon: ["array"],
        order: "last",
        is_system: true,
        updated_at: "hostile",
        extra: "ignored",
      }),
    }],
  },
  { label: "PATCH empty object", steps: [{ label: "PATCH", path: "/v1/folders/work-folder-qa", init: json("PATCH", {}) }] },
  { label: "PATCH nested path", steps: [{ label: "PATCH", path: "/v1/folders/work-folder-qa/nested", init: json("PATCH", {}) }] },
  { label: "DELETE missing", steps: [{ label: "DELETE", path: "/v1/folders/missing", init: { method: "DELETE" } }] },
  { label: "DELETE system before self", steps: [{ label: "DELETE", path: "/v1/folders/default-folder-qa?move_to_folder_id=default-folder-qa", init: { method: "DELETE" } }] },
  { label: "DELETE self move", steps: [{ label: "DELETE", path: "/v1/folders/work-folder-qa?move_to_folder_id=work-folder-qa", init: { method: "DELETE" } }] },
  { label: "DELETE empty explicit target", steps: [{ label: "DELETE", path: "/v1/folders/work-folder-qa?move_to_folder_id=", init: { method: "DELETE" } }] },
  { label: "DELETE unknown target", steps: [{ label: "DELETE", path: "/v1/folders/work-folder-qa?move_to_folder_id=missing", init: { method: "DELETE" } }] },
  {
    label: "DELETE explicit target reassigns conversation",
    steps: [
      { label: "DELETE", path: "/v1/folders/work-folder-qa?move_to_folder_id=default-folder-qa", init: { method: "DELETE" } },
      { label: "GET-conversations", path: "/v1/conversations" },
    ],
  },
  {
    label: "DELETE falls back to default",
    steps: [
      { label: "DELETE", path: "/v1/folders/work-folder-qa", init: { method: "DELETE" } },
      { label: "GET-conversations", path: "/v1/conversations" },
    ],
  },
  {
    label: "DELETE with no default leaves dangling reference",
    setup(api, local) {
      api.state.folders = [folder("source")];
      api.state.conversations = [conversation("source")];
      local.writePath.folders.reset();
      local.writePath.conversations.reset();
      local.writePath.folders.upsert(OWNER, folder("source"));
      local.writePath.conversations.upsert(OWNER, conversation("source"));
    },
    steps: [
      { label: "DELETE", path: "/v1/folders/source", init: { method: "DELETE" } },
      { label: "GET-folders", path: "/v1/folders" },
      { label: "GET-conversations", path: "/v1/conversations" },
    ],
  },
  {
    label: "DELETE decodes one id segment",
    setup(api, local) {
      api.state.folders.push(folder("space folder", { order: 2 }));
      local.writePath.folders.upsert(OWNER, folder("space folder", { order: 2 }));
    },
    steps: [{ label: "DELETE", path: "/v1/folders/space%20folder", init: { method: "DELETE" } }],
  },
  { label: "DELETE nested path", steps: [{ label: "DELETE", path: "/v1/folders/a/b", init: { method: "DELETE" } }] },
];

let comparisons = 0;
try {
  for (const scenario of scenarios) {
    const reset = await fetch(`${prototypeBase}/__qa/reset`, {
      method: "POST",
      headers: { authorization: `Bearer ${prototypeModule.QA_BEARER_TOKEN}` },
    });
    if (reset.status !== 200) throw new Error(`prototype reset failed: ${reset.status}`);
    service.reseed();
    scenario.setup?.(prototype, service);
    for (const step of scenario.steps) {
      const [expected, actual] = await Promise.all([
        prototypeRequest(step).then(parse),
        serviceRequest(step).then(parse),
      ]);
      comparisons += 1;
      if (actual.status !== expected.status || !same(actual.body, expected.body)) {
        process.stderr.write(`folder route prototype conformance failed: ${scenario.label} / ${step.label}\n`);
        process.stderr.write(`${JSON.stringify({ expected, actual }, null, 2)}\n`);
        process.exitCode = 1;
        break;
      }
      process.stdout.write(`${scenario.label} / ${step.label}: status=${actual.status} body=match\n`);
    }
    if (process.exitCode === 1) break;
  }
  if (process.exitCode !== 1) {
    process.stdout.write(`folder route prototype conformance: PASS (${comparisons} status/body comparisons)\n`);
  }
} finally {
  db.close();
  await prototype.close();
}
