import { describe, expect, test } from "bun:test";

import {
  buildProductGroupProjection,
} from "./product-projection";
import {
  buildDerivedGroupRecallCandidates,
  derivedGroupRecallProjectedContentDigest,
  parseDerivedGroupRecallMembers,
} from "./derived-group-recall-source";

const digest = (character: string): string => character.repeat(64);

const group = () => buildProductGroupProjection({
  owner_account_id: "account:alice",
  proposition_ids: ["proposition:one", "proposition:two"],
    input_frontier: digest("a"),
    projection_contract_digest: digest("c"),
    result_digest: digest("d"),
  created_at_event_time: 1,
});

describe("derived group recall source", () => {
  test("builds query candidates from derived groups only", () => {
    const members = parseDerivedGroupRecallMembers([{
      group: group(),
      rendered_text: "Launch week grouped the Atlas facts.",
    }]);
    const candidates = buildDerivedGroupRecallCandidates(members);
    expect(candidates).toHaveLength(1);
    expect(candidates[0]?.contributing_subject_classes).toEqual(["derived_group"]);
    expect(candidates[0]?.trace_ref).toMatch(/^tr1_[a-f0-9]{64}$/);
    expect(derivedGroupRecallProjectedContentDigest(members)).toMatch(/^[a-f0-9]{64}$/);
  });

  test("rejects unconsolidated card bags that are not group projections", () => {
    expect(() => parseDerivedGroupRecallMembers([{
      group: { id: "card:one", text: "a raw card" },
      rendered_text: "a raw card",
    }])).toThrow("invalid_group_projection");
  });
});
