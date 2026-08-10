import type { Hono } from "hono";

import type { DevPrincipal } from "../auth/dev-token";
import type { ServedCounter } from "../observability/served-count";
import type {
  FolderDeletionOutcome,
  FolderDeletionUnitOfWork,
} from "../stores/folder-deletion-unit-of-work";
import type { FolderPatch, FoldersStore } from "../stores/folders-store";

const JSON_HEADERS = Object.freeze({
  "cache-control": "no-store",
  "content-type": "application/json; charset=utf-8",
});
const EMPTY_HEADERS = Object.freeze({ "cache-control": "no-store" });
export const FOLDERS_PATH = "/v1/folders";
const FOLDER_PREFIX = `${FOLDERS_PATH}/`;

export interface FolderRouteDependencies {
  readonly resolvePrincipal: (token: string) => DevPrincipal | null;
  readonly store: FoldersStore;
  readonly deletion: FolderDeletionUnitOfWork;
  readonly counter: ServedCounter;
  readonly now: () => string;
  readonly createId: () => string;
}

const jsonResponse = (value: unknown, status = 200): Response =>
  new Response(JSON.stringify(value), { status, headers: JSON_HEADERS });

const errorResponse = (status: number, code: string): Response =>
  jsonResponse({ error: code }, status);

const bearerToken = (header: string | undefined): string | null => {
  if (typeof header !== "string" || !header.startsWith("Bearer ")) return null;
  const token = header.slice("Bearer ".length);
  return token.length > 0 ? token : null;
};

const authenticate = (
  header: string | undefined,
  resolvePrincipal: FolderRouteDependencies["resolvePrincipal"],
): DevPrincipal | null => {
  const token = bearerToken(header);
  return token === null ? null : resolvePrincipal(token);
};

const requestUrl = (raw: Request): URL | null => {
  try {
    return new URL(raw.url);
  } catch {
    return null;
  }
};

const decodeId = (raw: string): string | null => {
  if (!raw || raw.includes("/")) return null;
  try {
    const decoded = decodeURIComponent(raw);
    return decoded && !decoded.includes("/") ? decoded : null;
  } catch {
    return null;
  }
};

const readJsonLikePrototype = async (request: Request): Promise<unknown> => {
  const body = await request.text();
  if (body.length === 0) return {};
  return JSON.parse(body) as unknown;
};

const deleteError = (reason: Exclude<
  FolderDeletionOutcome,
  { readonly deleted: true }
>["reason"]): Response => {
  if (reason === "system_folder" || reason === "self_move") {
    return errorResponse(400, reason);
  }
  return errorResponse(404, reason);
};

export const registerFolderRoutes = (
  app: Hono,
  deps: FolderRouteDependencies,
): void => {
  app.get(FOLDERS_PATH, (context) => {
    const principal = authenticate(context.req.header("authorization"), deps.resolvePrincipal);
    if (principal === null) {
      deps.counter.recordDomainRead("denied");
      return errorResponse(401, "unauthorized");
    }
    // The prototype ignores limit/offset and returns one unpaginated bare array.
    // Preserve that visible wart rather than borrowing conversations pagination.
    const folders = deps.store.listFolders(principal.uid);
    deps.counter.recordDomainRead("served");
    return jsonResponse(folders);
  });

  app.post(FOLDERS_PATH, async (context) => {
    const principal = authenticate(context.req.header("authorization"), deps.resolvePrincipal);
    if (principal === null) return errorResponse(401, "unauthorized");
    try {
      let body: unknown;
      try {
        body = await readJsonLikePrototype(context.req.raw);
      } catch {
        return errorResponse(400, "invalid_json");
      }
      // Accessing `name` on JSON null throws in the prototype and becomes
      // qa_server_error. Preserve that visible wart.
      const input = body as Record<string, unknown>;
      if (typeof input.name !== "string" || input.name.trim() === "") {
        return errorResponse(400, "name_required");
      }
      // The prototype trim-checks a name but stores its original whitespace,
      // and silently replaces non-string optional values with defaults.
      // Preserve both visible warts.
      const created = deps.store.createFolder(principal.uid, {
        id: deps.createId(),
        name: input.name,
        description: typeof input.description === "string" ? input.description : null,
        color: typeof input.color === "string" ? input.color : "#6B7280",
        icon: typeof input.icon === "string" ? input.icon : "folder",
        created_at: deps.now(),
        updated_at: deps.now(),
      });
      if (!created.created) return errorResponse(500, "qa_server_error");
      // The prototype returns only `{ id }`, not the created row. Preserve that
      // visible wart even though PATCH returns a full row.
      return jsonResponse({ id: created.record.id }, 201);
    } catch {
      return errorResponse(500, "qa_server_error");
    }
  });

  app.patch(`${FOLDERS_PATH}/*`, async (context) => {
    const principal = authenticate(context.req.header("authorization"), deps.resolvePrincipal);
    if (principal === null) return errorResponse(401, "unauthorized");
    const url = requestUrl(context.req.raw);
    if (url === null) return errorResponse(400, "invalid_url");
    const id = decodeId(url.pathname.slice(FOLDER_PREFIX.length));
    if (id === null) return errorResponse(404, "not_found");
    if (deps.store.readFolder(principal.uid, id) === null) {
      return errorResponse(404, "not_found");
    }
    try {
      let body: unknown;
      try {
        body = await readJsonLikePrototype(context.req.raw);
      } catch {
        return errorResponse(400, "invalid_json");
      }
      const patch: Record<string, unknown> = {};
      // `Object.hasOwn(null, ...)` throws in the prototype and becomes
      // qa_server_error. Preserve that visible wart.
      for (const key of ["name", "description", "color", "icon", "order"] as const) {
        if (Object.hasOwn(body as object, key)) {
          patch[key] = (body as Record<string, unknown>)[key];
        }
      }
      // The prototype validates no PATCH value types, ignores every other key,
      // and treats an empty object as a successful timestamp mutation. Preserve
      // those visible warts and return the full row.
      const outcome = deps.store.patchFolder(principal.uid, id, patch as FolderPatch, deps.now());
      if (!outcome.updated) return errorResponse(404, "not_found");
      return jsonResponse(outcome.record);
    } catch {
      return errorResponse(500, "qa_server_error");
    }
  });

  app.delete(`${FOLDERS_PATH}/*`, async (context) => {
    const principal = authenticate(context.req.header("authorization"), deps.resolvePrincipal);
    if (principal === null) return errorResponse(401, "unauthorized");
    const url = requestUrl(context.req.raw);
    if (url === null) return errorResponse(400, "invalid_url");
    const id = decodeId(url.pathname.slice(FOLDER_PREFIX.length));
    if (id === null) return errorResponse(404, "not_found");
    try {
      // The semantic unit preserves the prototype's check order: system before
      // self or target validation, and an empty query value is an explicit
      // missing target. It owns reassignment and deletion as one commit.
      const outcome = await deps.deletion.execute({
        accountId: principal.uid,
        folderId: id,
        requestedTarget: url.searchParams.get("move_to_folder_id"),
      });
      if (outcome.deleted === false) return deleteError(outcome.reason);
      // With no explicit target the prototype falls back to the default folder.
      // With no default it deletes anyway and leaves conversation.folder_id
      // dangling. Preserve that visible wart; the store reports a null target.
      return new Response(null, { status: 204, headers: EMPTY_HEADERS });
    } catch {
      return errorResponse(500, "qa_server_error");
    }
  });
};
