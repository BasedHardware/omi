// LIFECYCLE: permanent
//
// The task bag used by the dev/L3 write journey while the registered write
// door still stores opaque bags without applying the signed defaults itself.
//
// R26's thirteen-field vocabulary has two store-owned fields (`id`,
// `revision`) and eleven projection fields. The current read composition reads
// those eleven from the bag, including the two timestamps that R26 A2 assigns
// to the future enforcing door. Until that enforcement lands, omitting any one
// of them lets an accepted dev write make GET /v1/tasks unservable. Keeping the
// transitional full bag in one helper prevents the direct journey and its
// outbox seed from drifting into two vocabularies.

export const JOURNEY_TASK_TIMESTAMP = 1_786_248_000;

export function createReadableTaskBag({
  description,
  completed,
  timestamp = JOURNEY_TASK_TIMESTAMP,
  source = "user",
} = {}) {
  if (typeof description !== "string") {
    throw new TypeError("journey task description must be a string");
  }
  if (typeof completed !== "boolean") {
    throw new TypeError("journey task completed must be a boolean");
  }
  if (!Number.isSafeInteger(timestamp)) {
    throw new TypeError("journey task timestamp must be a safe integer");
  }
  if (typeof source !== "string") {
    throw new TypeError("journey task source must be a string");
  }

  return {
    description,
    completed,
    completedAt: null,
    dueAt: null,
    owner: null,
    source,
    provenance: [],
    sortOrder: 0,
    indentLevel: 0,
    createdAt: timestamp,
    updatedAt: timestamp,
  };
}
