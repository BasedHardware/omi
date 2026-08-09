import { Database } from "bun:sqlite";

import type { ConversationRecord } from "../../../apps/service/stores/conversations-store";
import { SqliteConversationsStore } from "./conversations-store";

const ACCOUNT = "acct-conversation-restart";
const RECORD_ID = "conversation-persistent";
const TITLE = "Persistent conversation";
const UPDATED_TITLE = "Persistent after mutation";

const record: ConversationRecord = {
  id: RECORD_ID,
  structured: { title: TITLE, overview: "Separate-process persistence proof." },
  created_at: "2026-08-03T12:00:00.000Z",
  updated_at: "2026-08-03T12:00:00.000Z",
  started_at: "2026-08-03T12:00:00.000Z",
  finished_at: "2026-08-03T12:05:00.000Z",
  source: "omi",
  status: "completed",
  discarded: false,
  starred: false,
  visibility: "private",
  is_locked: false,
  folder_id: null,
};

const phase = process.argv[2];
const databasePath = process.argv[3];
if ((phase !== "write" && phase !== "read") || databasePath === undefined) {
  throw new TypeError("usage: conversations-restart-proof-child.ts <write|read> <database-path>");
}

const db = new Database(databasePath, databasePath === ":memory:" ? undefined : { create: true });
try {
  const store = new SqliteConversationsStore(db);
  if (phase === "write") {
    const saved = store.upsert(ACCOUNT, record);
    if (!saved.stored) throw new Error("conversation write refused");
    const patched = store.updateTitle(
      ACCOUNT,
      RECORD_ID,
      UPDATED_TITLE,
      "2026-08-07T12:00:00.000Z",
    );
    if (!patched.updated) throw new Error("conversation mutation refused");
    process.stdout.write(JSON.stringify({ title: patched.record.structured.title }));
  } else {
    const found = store.readRecord(ACCOUNT, RECORD_ID);
    process.stdout.write(JSON.stringify({
      found: found !== null,
      title: found?.structured.title ?? null,
      revision: store.readStateRevision(ACCOUNT),
    }));
  }
} finally {
  db.close();
}
