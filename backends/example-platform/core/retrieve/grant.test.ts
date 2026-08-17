import { expect, test } from "bun:test";
import { grantAllows, type RequestContext } from "./grant";

const claim = { owner_account_id: "owner" } as never;
const generic = { subject_class: "generic", sensitivity: "generic", capture_class: "generic" };
const privatePolicy = { subject_class: "owner", sensitivity: "private", capture_class: "voice" };
const narrow: RequestContext = { reader_account_id: "reader", grant: { grant_id: "generic-only", policy_classes: [generic] } };

test("G1 owner identity covers every policy class, including a future unknown label", () => {
  expect(grantAllows({ ...narrow, reader_account_id: "owner" }, claim, { subject_class: "future-subject", sensitivity: "future-sensitivity", capture_class: "future-capture" })).toBe(true);
});
test("G1 synthetic reader grants require all three explicit D23 dimensions", () => {
  expect(grantAllows(narrow, claim, generic)).toBe(true);
  expect(grantAllows(narrow, claim, privatePolicy)).toBe(false);
  expect(grantAllows(narrow, claim, { ...generic, sensitivity: "unclassified-future-value" })).toBe(false);
});
test("G1 adversarial unknown-equals-unknown is denied to a non-owner and remains owner-only", () => {
  const future = { subject_class: "future", sensitivity: "future", capture_class: "future" };
  const forgedExactGrant: RequestContext = { reader_account_id: "reader", grant: { grant_id: "future", policy_classes: [future] } };
  expect(grantAllows(forgedExactGrant, claim, future)).toBe(false);
  expect(grantAllows({ ...forgedExactGrant, reader_account_id: "owner" }, claim, future)).toBe(true);
});
