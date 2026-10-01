import { expect, test } from "bun:test";
import { gradeResolution } from "./resolution-grade";

test("T8 grading counts correct merge, same-name false merge, abstention, and owner", () => {
  const mentions = [
    { mention_id: "a1", name: "Alice", type: "person" as const, session_id: "s1", examples: [] },
    { mention_id: "a2", name: "Alice", type: "person" as const, session_id: "s2", examples: [] },
    { mention_id: "j1", name: "Jordan Lee", type: "person" as const, session_id: "s1", examples: [] },
    { mention_id: "j2", name: "Jordan Lee", type: "person" as const, session_id: "s2", examples: [] },
    { mention_id: "u1", name: "they", type: "person" as const, session_id: "s1", examples: [] },
    { mention_id: "o1", name: "David", type: "person" as const, session_id: "s1", examples: [] },
  ];
  const gold = { assignments: { a1: "gold-alice", a2: "gold-alice", j1: "gold-jordan-1", j2: "gold-jordan-2", u1: "gold-unresolved-candidate", o1: "OWNER" }, clusters: {} };
  const predicted = { assignments: { a1: "pred-a", a2: "pred-a", j1: "pred-j", j2: "pred-j", u1: "UNRESOLVED", o1: "OWNER" }, clusters: {} };
  const grade = gradeResolution(predicted, gold, mentions);
  expect(grade.outcome_counts).toEqual({ correct: 3, "wrong-entity": 2, "wrong-bucket": 0, abstained: 1, "over-placed": 0 });
  expect(grade.pairwise).toMatchObject({ true_positive: 1, false_positive: 1, false_negative: 0, precision: 0.5, recall: 1, f1: 2 / 3 });
  expect(grade.false_merges).toEqual({ count: 1, offending_name_pairs: [{ mention_ids: ["j1", "j2"], names: ["Jordan Lee", "Jordan Lee"], same_surface_name: true }] });
  expect(grade.cross_session_positive_pair_recall).toEqual({ true_positive: 1, total: 1, recall: 1 });
  expect(grade.selective_risk_at_coverage).toEqual({ accuracy: 3 / 5, risk: 2 / 5, coverage: 5 / 6, confidently_placed: 5, total: 6 });
});
