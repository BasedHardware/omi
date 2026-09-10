import {
  TASKS_READ_CONTRACT_VERSION,
  type TaskRead,
} from "@omi-core/ratified-contracts/projections/tasks";

const TASKS_FRONTIER = "frontier-v1:tasks-declared";

type StoredTask = {
  id: string;
  description: string;
  completed: number;
  completedAt: number | null;
  dueAt: number | null;
  owner: string | null;
  source: string;
  provenance: string;
  sortOrder: number;
  indentLevel: number;
  createdAt: number;
  updatedAt: number;
  revision: string | null;
};

export function parseTaskLimit(
  value: string | null | undefined
): number | null {
  // Match production parsePageQuery: 1-3 digit strings then range 1-100.
  if (value === null || value === undefined) return 25;
  if (!/^[0-9]{1,3}$/.test(value)) return null;
  const limit = Number(value);
  if (!Number.isSafeInteger(limit) || limit < 1 || limit > 100) return null;
  return limit;
}
export async function readTasks(
  db: D1Database,
  accountId: string,
  limit: number,
  cursor: string | undefined
): Promise<TaskRead.Page | "unprojectable" | "invalid_cursor"> {
  if (cursor !== undefined) {
    if (cursor.length < 1 || cursor.length > 1024) return "invalid_cursor";
    const found = await db
      .prepare("SELECT 1 FROM tasks WHERE account_id = ? AND id = ?")
      .bind(accountId, cursor)
      .first();
    if (found === null) return "invalid_cursor";
  }
  const statement = db.prepare(
    "SELECT id, description, completed, completed_at AS completedAt, due_at AS dueAt, owner, source, provenance, sort_order AS sortOrder, indent_level AS indentLevel, created_at AS createdAt, updated_at AS updatedAt, revision FROM tasks WHERE account_id = ? AND (? IS NULL OR id > ?) ORDER BY id LIMIT ?"
  );
  const bound = statement.bind(
    accountId,
    cursor ?? null,
    cursor ?? null,
    limit + 1
  );
  const result = await bound.all<StoredTask>();
  const rows = result.results;
  const hasMore = rows.length > limit;
  const pageRows = rows.slice(0, limit);
  const items: TaskRead.Item[] = [];
  for (const row of pageRows) {
    const item = toTaskItem(row);
    if (item === null) return "unprojectable";
    items.push(item);
  }
  const nextCursor = hasMore ? pageRows[pageRows.length - 1]?.id ?? null : null;

  return {
    contractVersion: TASKS_READ_CONTRACT_VERSION,
    items,
    window: {
      status: hasMore ? "more" : "complete",
      complete: !hasMore,
      hasMore,
      nextCursor,
    },
    completeness: {
      version: "tasks-completeness-v1",
      status: "complete",
      reasons: [],
      frontiers: {
        declaredFrontier:
          TASKS_FRONTIER as TaskRead.Frontiers["declaredFrontier"],
        newestAppliedFrontier:
          TASKS_FRONTIER as TaskRead.Frontiers["newestAppliedFrontier"],
        missingAppliedFrontierReason: null,
      },
    },
    absence:
      items.length === 0 ? ({ kind: "query_gap" } as TaskRead.QueryGap) : null,
  } as TaskRead.Page;
}

function toTaskItem(row: StoredTask): TaskRead.Item | null {
  let provenance: unknown;
  try {
    provenance = JSON.parse(row.provenance);
  } catch {
    return null;
  }
  if (
    !Array.isArray(provenance) ||
    !provenance.every((entry) => typeof entry === "string")
  ) {
    return null;
  }
  const item: Record<string, unknown> = {};
  item["id"] = row.id;
  item["description"] = row.description;
  item["completed"] = Boolean(row.completed);
  item["completedAt"] = row.completedAt ?? null;
  item["dueAt"] = row.dueAt ?? null;
  item["owner"] = row.owner ?? null;
  item["source"] = row.source;
  item["provenance"] = provenance;
  item["sortOrder"] = row.sortOrder;
  item["indentLevel"] = row.indentLevel;
  item["createdAt"] = row.createdAt;
  item["updatedAt"] = row.updatedAt;
  item["revision"] = row.revision ?? null;
  return item as unknown as TaskRead.Item;
}
