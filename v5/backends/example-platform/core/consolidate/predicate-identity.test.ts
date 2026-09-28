import { expect, test } from "bun:test";
import { normalizePredicateName, predicateIdForName, predicateRevisionForObservation, predicateRevisionForStoredObservation } from "./predicate-identity";

test("predicate identity is the normalized name and ignores window slot ordinals", () => {
  expect(normalizePredicateName("  Performs-Action ")).toBe("performs_action");
  expect(predicateIdForName("Performs Action")).toBe(predicateIdForName("performs-action"));
  expect(predicateIdForName("performs action")).not.toBe(predicateIdForName("performed action"));
});

test("predicate revisions coexist for optional semantic role sets", () => {
  const predicate_id = predicateIdForName("perform_action");
  const base = predicateRevisionForObservation({ owner_account_id: "owner", predicate_id, display_name: "perform_action", roles: ["agent", "action"] });
  const expanded = predicateRevisionForObservation({ owner_account_id: "owner", predicate_id, display_name: "perform_action", roles: ["target", "agent", "action", "target"] });
  const replay = predicateRevisionForObservation({ owner_account_id: "owner", predicate_id, display_name: "perform_action", roles: ["action", "agent"] });

  expect(base.predicate).toMatchObject({ identity_version: "name-v2", slot_ids: [], observed_roles: ["action", "agent"] });
  expect(expanded.predicate.observed_roles).toEqual(["action", "agent", "target"]);
  expect(expanded.revision_id).not.toBe(base.revision_id);
  expect(replay).toEqual(base);
  expect(expanded.predicate.predicate_id).toBe(base.predicate.predicate_id);
  expect(predicateRevisionForObservation({ ...base.predicate, owner_account_id: "other-owner", roles: ["action", "agent"] }).revision_id)
    .not.toBe(base.revision_id);
});

test("predicate observations reject legacy or mismatched identity coordinates", () => {
  expect(() => predicateRevisionForObservation({ owner_account_id: "owner", predicate_id: "predicate:legacy-slot-key", display_name: "works_on", roles: ["subject"] }))
    .toThrow("predicate observation id does not match normalized name identity");
});

test("stored legacy observations preserve their existing identity without pretending to be v2", () => {
  const legacy = predicateRevisionForStoredObservation({
    owner_account_id: "owner",
    predicate_id: "predicate:legacy-name-plus-slots",
    display_name: "works_on",
    roles: ["subject", "object"],
    legacy_slot_ids: ["window-slot-2", "window-slot-1"],
    lifecycle: "provisional",
  });
  expect(legacy.predicate).toMatchObject({
    predicate_id: "predicate:legacy-name-plus-slots",
    identity_version: "name-slots-v1",
    slot_ids: ["window-slot-1", "window-slot-2"],
    lifecycle: "provisional",
  });
  expect(legacy.predicate).not.toHaveProperty("observed_roles");
});
