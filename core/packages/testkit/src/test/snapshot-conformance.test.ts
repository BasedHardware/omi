/** One suite, every domain: the rule-12 laws executed against all fetchers. */

import assert from "node:assert/strict";
import { test } from "node:test";
import {
  fetchConversationIdSnapshot,
  fetchFolderIdSnapshot,
  fetchIdSnapshot,
  fetchMemoryIdSnapshot,
} from "@omi-core/adapters-legacy";
import { checkSnapshotConformance, type SnapshotDescriptor } from "../snapshot-conformance.js";

const DESCRIPTORS: SnapshotDescriptor[] = [
  {
    domain: "tasks",
    kind: "unpaginated",
    fetch: (http) => fetchIdSnapshot(http),
    okBody: (ids) => ({ ids }),
  },
  {
    domain: "memories",
    kind: "paged",
    fetch: (http) => fetchMemoryIdSnapshot(http, 100),
    okBody: (ids) => ids.map((id) => ({ id })),
    pageSize: 100,
  },
  {
    domain: "conversations",
    kind: "paged-filtered",
    fetch: (http) => fetchConversationIdSnapshot(http, 100),
    okBody: (ids) => ids.map((id) => ({ id })),
    pageSize: 100,
  },
  {
    domain: "folders",
    kind: "unpaginated",
    fetch: (http) => fetchFolderIdSnapshot(http),
    okBody: (ids) => ids.map((id) => ({ id })),
  },
];

test("every domain's id-snapshot fetcher obeys the rule-12 honesty laws", async () => {
  const failures = await checkSnapshotConformance(DESCRIPTORS);
  assert.deepEqual(failures, [], failures.map((f) => `${f.domain}: ${f.law} (got ${f.got})`).join("\n"));
});
