/**
 * Adversarial RUNTIME boundary tests for the ratified write-ops envelope.
 *
 * The wire is already shipped (`@omi-core/ratified-contracts/write/ops`). This
 * file does not move it — it constructs hostile request bytes a confused client
 * or hostile router might send, and asserts the existing validators reject (or,
 * for a handful of controls, accept) them. Sister of
 * `write-ops-conformance.test.ts`, which consumes the corpus of record; this
 * file invents attacks the corpus does not need to enumerate.
 */

import assert from "node:assert/strict";
import test from "node:test";

import {
  WRITE_OPS_PATH_PATTERN,
  WRITABLE_DOMAINS,
  isTrustedWriteOpEnvelope,
  isWritableDomain,
  parseWriteOpEnvelopeJson,
  writeOpsPath,
} from "@omi-core/ratified-contracts/write/ops";

/** Fixed 64-hex write_id from the write-ops conformance corpus — valid grammar, no entropy needed. */
const WRITE_ID = "e11889ad5e74748964b84c271bd3b7bc6170d4a5816eb7e33f701a2cabe77a4c";
const BASE_REVISION = "219a4807d8970548f0af5a687bb16d444d7090c74e203b37e072baae95a5f022";

/** A minimal accepted tasks/patch envelope. Mutate copies; never send this helper itself as the attack. */
function validPatchEnvelope(): Record<string, unknown> {
  return {
    write_id: WRITE_ID,
    account_epoch: 7,
    domain: "tasks",
    op: {
      op: "patch",
      record_id: "task-9f21",
      patch: { done: true },
    },
  };
}

function asCanonicalJson(value: unknown): string {
  return JSON.stringify(value);
}

function assertRejectedRaw(raw: string, label: string): void {
  assert.equal(parseWriteOpEnvelopeJson(raw), null, `${label}: parseWriteOpEnvelopeJson must reject`);
}

function assertRejectedObject(value: unknown, label: string): void {
  assert.equal(isTrustedWriteOpEnvelope(value), false, `${label}: isTrustedWriteOpEnvelope must reject`);
  assertRejectedRaw(asCanonicalJson(value), label);
}

// ── control: clearly-valid envelopes must still pass ─────────────────────────

test("control: a well-formed tasks patch envelope is accepted", () => {
  // Models the happy path a real outbox drain sends — without this, every
  // rejection below could be a parser that rejects everything.
  const envelope = validPatchEnvelope();
  const raw = asCanonicalJson(envelope);
  assert.equal(isTrustedWriteOpEnvelope(envelope), true);
  assert.deepEqual(parseWriteOpEnvelopeJson(raw), envelope);
});

test("control: a well-formed tasks create (no base_revision) is accepted", () => {
  // Create is a legitimate verb; the attack below is create+base_revision, not create itself.
  const envelope = {
    write_id: WRITE_ID,
    account_epoch: 7,
    domain: "tasks",
    op: {
      op: "create",
      record_id: "task-0001",
      content: { title: "x" },
    },
  };
  assert.equal(isTrustedWriteOpEnvelope(envelope), true);
  assert.deepEqual(parseWriteOpEnvelopeJson(asCanonicalJson(envelope)), envelope);
});

// ── 1. domain field attacks (B6 allowlist + string identity) ─────────────────

test("domain: wrong case 'Tasks' is refused", () => {
  // Case-folding a path segment is a classic router footgun; the allowlist is
  // exact string identity, not a case-insensitive match.
  const envelope = validPatchEnvelope();
  envelope["domain"] = "Tasks";
  assert.equal(isWritableDomain("Tasks"), false);
  assertRejectedObject(envelope, "domain=Tasks");
});

test("domain: trailing space 'tasks ' is refused", () => {
  // A trim-happy client, or a log-rehydrated value with whitespace, must not
  // slip past the allowlist.
  const envelope = validPatchEnvelope();
  envelope["domain"] = "tasks ";
  assert.equal(isWritableDomain("tasks "), false);
  assertRejectedObject(envelope, "domain=tasks[space]");
});

test("domain: memories is refused (B6 — read-only by ratified design)", () => {
  // B6: Memories is deliberately absent from WRITABLE_DOMAINS. Naming it must
  // fail validation here, not reach an apply path that "might" refuse later.
  const envelope = validPatchEnvelope();
  envelope["domain"] = "memories";
  envelope["op"] = { op: "patch", record_id: "mem-01", patch: { text: "x" } };
  assert.equal(isWritableDomain("memories"), false);
  assert.ok(!WRITABLE_DOMAINS.includes("memories" as (typeof WRITABLE_DOMAINS)[number]));
  assertRejectedObject(envelope, "domain=memories");
});

test("domain: near-miss singular 'task' is refused", () => {
  // Typo / singularisation must not invent a writable domain.
  const envelope = validPatchEnvelope();
  envelope["domain"] = "task";
  assert.equal(isWritableDomain("task"), false);
  assertRejectedObject(envelope, "domain=task");
});

test("domain: empty string is refused", () => {
  // Empty path segment after a confused URL join.
  const envelope = validPatchEnvelope();
  envelope["domain"] = "";
  assert.equal(isWritableDomain(""), false);
  assertRejectedObject(envelope, "domain=\"\"");
});

test("domain: path-traversal-looking '../tasks' is refused", () => {
  // A client that concatenated a relative segment into the domain field.
  const envelope = validPatchEnvelope();
  envelope["domain"] = "../tasks";
  assert.equal(isWritableDomain("../tasks"), false);
  assertRejectedObject(envelope, "domain=../tasks");
});

test("domain: number or array instead of string is refused", () => {
  // JSON type confusion: a numeric or array domain is not an allowlist hit.
  const asNumber = validPatchEnvelope();
  asNumber["domain"] = 0;
  assert.equal(isWritableDomain(0), false);
  assertRejectedObject(asNumber, "domain=0");

  const asArray = validPatchEnvelope();
  asArray["domain"] = ["tasks"];
  assert.equal(isWritableDomain(["tasks"]), false);
  assertRejectedObject(asArray, "domain=[tasks]");
});

test("domain: string '__proto__' is refused", () => {
  // Prototype-pollution vocabulary as a domain name — must not be writable and
  // must not be treated as a special key by the allowlist Set.
  const envelope = validPatchEnvelope();
  envelope["domain"] = "__proto__";
  assert.equal(isWritableDomain("__proto__"), false);
  assertRejectedObject(envelope, "domain=__proto__");
});

// ── 2. op.op field attacks ───────────────────────────────────────────────────

test("op.op: unknown verbs 'upsert' and 'replace' are refused", () => {
  // REST habits (upsert/replace) must not invent verbs on this one-envelope wire.
  for (const verb of ["upsert", "replace"] as const) {
    const envelope = validPatchEnvelope();
    envelope["op"] = {
      op: verb,
      record_id: "task-9f21",
      patch: { done: true },
    };
    assertRejectedObject(envelope, `op.op=${verb}`);
  }
});

test("op.op: missing op verb is refused", () => {
  // A partial object that still looks like a patch payload without naming a verb.
  const envelope = validPatchEnvelope();
  envelope["op"] = {
    record_id: "task-9f21",
    patch: { done: true },
  };
  assertRejectedObject(envelope, "op.op missing");
});

test("op.op: object instead of string is refused", () => {
  // Type confusion: nest another envelope-shaped object where the verb belongs.
  const envelope = validPatchEnvelope();
  envelope["op"] = {
    op: { op: "patch" },
    record_id: "task-9f21",
    patch: { done: true },
  };
  assertRejectedObject(envelope, "op.op=object");
});

// ── 3. envelope shape attacks ("tolerate whats received, refuse what you send") ─

test("envelope: unknown top-level field is refused", () => {
  // Deliberate: the envelope is a REQUEST shape. Silently ignoring a field the
  // client thought it sent is how a precondition goes missing (corpus note on
  // the unknown-field row; B4).
  const envelope = validPatchEnvelope();
  envelope["op_id"] = "edit-task-9f21";
  assertRejectedObject(envelope, "extra top-level op_id");

  const raw =
    `{"write_id":"${WRITE_ID}","account_epoch":7,"domain":"tasks",` +
    `"op":{"op":"patch","record_id":"task-9f21","patch":{"done":true}},"client_meta":1}`;
  assertRejectedRaw(raw, "extra top-level client_meta");
});

test("envelope: missing any of the four required keys is refused", () => {
  // A truncated client serializer that drops a stamp must not partially apply.
  for (const key of ["write_id", "account_epoch", "domain", "op"] as const) {
    const envelope = validPatchEnvelope();
    delete envelope[key];
    assertRejectedObject(envelope, `missing ${key}`);
  }
});

test("envelope: op is null is refused", () => {
  // JSON null where an op object is required — not an empty delete.
  const envelope = validPatchEnvelope();
  envelope["op"] = null;
  assertRejectedObject(envelope, "op=null");
});

test("envelope: create carrying base_revision is refused", () => {
  // Module rule: a create carries no precondition — there is nothing to be a
  // revision OF. Accepting it would let a client believe it had a fence it does not.
  const envelope = {
    write_id: WRITE_ID,
    account_epoch: 7,
    domain: "tasks",
    op: {
      op: "create",
      record_id: "task-0001",
      content: { title: "x" },
      base_revision: BASE_REVISION,
    },
  };
  assertRejectedObject(envelope, "create+base_revision");
});

// ── 4. writeOpsPath / WRITE_OPS_PATH_PATTERN attacks ─────────────────────────

test("writeOpsPath only emits paths for WRITABLE_DOMAINS, and the pattern matches them", () => {
  // B4/B6: the route is built from the allowlist, never hand-spelled. Runtime
  // check: every writable domain compiles a pattern-matching path, and the
  // allowlist is exactly the shipped set (tasks only).
  assert.deepEqual([...WRITABLE_DOMAINS], ["tasks"]);
  for (const domain of WRITABLE_DOMAINS) {
    assert.equal(isWritableDomain(domain), true);
    const path = writeOpsPath(domain);
    assert.equal(path, `/v1/${domain}/ops`);
    assert.equal(WRITE_OPS_PATH_PATTERN.test(path), true, path);
  }
});

test("WRITE_OPS_PATH_PATTERN rejects hostile router strings", () => {
  // Probes a confused reverse-proxy or hand-rolled matcher might see. The
  // pattern is the server-side assertion companion to writeOpsPath.
  const rejected = [
    "/v1/tasks/ops/", // trailing slash
    "/v1/tasks/../memories/ops", // traversal across domains
    "/v1//ops", // empty domain segment
    "/v1/TASKS/ops", // wrong case
    "/v1/tasks/ops?x=1", // query string glued on
    "//v1/tasks/ops", // scheme-relative / double-slash
    "/v1/tasks\u0000/ops", // null byte in the domain segment
    "/v1/%2e%2e/ops", // percent-encoded .. as the domain
    "/v1/memories/ops", // read-only domain — pattern is shape-only, but still a string a router sees; memories matches the *shape* grammar
  ];

  assert.equal(WRITE_OPS_PATH_PATTERN.test("/v1/tasks/ops"), true, "control path must match");

  for (const path of rejected) {
    if (path === "/v1/memories/ops") {
      // The path *pattern* is domain-generic (B6); writability is a separate
      // allowlist. Confirm the split: shape may match, domain must not be writable.
      assert.equal(WRITE_OPS_PATH_PATTERN.test(path), true, `${path}: shape matches`);
      assert.equal(isWritableDomain("memories"), false);
      continue;
    }
    assert.equal(WRITE_OPS_PATH_PATTERN.test(path), false, `pattern must reject ${JSON.stringify(path)}`);
  }
});

// ── 5. __proto__ / prototype-pollution style attacks ─────────────────────────

test("envelope JSON with top-level '__proto__' or 'constructor' key is refused", () => {
  // Pollution vocabulary as an extra REQUEST field — refused by exact-key check
  // ("refuse what you send"), and must not leave Object.prototype tainted.
  const withProto =
    `{"write_id":"${WRITE_ID}","account_epoch":7,"domain":"tasks",` +
    `"op":{"op":"patch","record_id":"task-9f21","patch":{"done":true}},` +
    `"__proto__":{"polluted":true}}`;
  const withCtor =
    `{"write_id":"${WRITE_ID}","account_epoch":7,"domain":"tasks",` +
    `"op":{"op":"patch","record_id":"task-9f21","patch":{"done":true}},` +
    `"constructor":{"prototype":{"polluted":true}}}`;

  assertRejectedRaw(withProto, "top-level __proto__");
  assertRejectedRaw(withCtor, "top-level constructor");
  assert.equal(({} as { polluted?: unknown }).polluted, undefined);
});

test("op payload keys '__proto__' / 'constructor' do not pollute Object.prototype", () => {
  // Even if a patch field map carries pollution vocabulary as ordinary data
  // keys, parsing must not define inherited properties on Object.prototype.
  // Acceptance-or-rejection is secondary; non-pollution is the invariant.
  const rawProto =
    `{"write_id":"${WRITE_ID}","account_epoch":7,"domain":"tasks",` +
    `"op":{"op":"patch","record_id":"task-9f21","patch":{"__proto__":{"polluted":true},"done":true}}}`;
  const rawCtor =
    `{"write_id":"${WRITE_ID}","account_epoch":7,"domain":"tasks",` +
    `"op":{"op":"patch","record_id":"task-9f21","patch":{"constructor":{"polluted":true},"done":true}}}`;

  // Exercise the real untrusted-bytes entrypoint either way.
  parseWriteOpEnvelopeJson(rawProto);
  parseWriteOpEnvelopeJson(rawCtor);

  assert.equal(({} as { polluted?: unknown }).polluted, undefined);
  assert.equal(Object.prototype.hasOwnProperty("polluted"), false);

  // And a trusted-predicate pass over JSON.parse output must likewise leave the
  // prototype chain clean (isTrustedWriteOpEnvelope is not the hostile boundary,
  // but must not be a pollution gadget if a caller feeds it parsed JSON).
  isTrustedWriteOpEnvelope(JSON.parse(rawProto));
  isTrustedWriteOpEnvelope(JSON.parse(rawCtor));
  assert.equal(({} as { polluted?: unknown }).polluted, undefined);
});
