import type { ResolutionMention, ResolutionResult } from "./resolution-run";

export type MentionOutcome = "correct" | "wrong-entity" | "wrong-bucket" | "abstained" | "over-placed";
type BucketKind = "entity" | "OWNER" | "UNRESOLVED";
export type FalseMerge = { mention_ids: [string, string]; names: [string, string]; same_surface_name: boolean };
export type ResolutionGrade = {
  outcomes: Record<string, MentionOutcome>;
  outcome_counts: Record<MentionOutcome, number>;
  pairwise: { true_positive: number; false_positive: number; false_negative: number; precision: number; recall: number; f1: number };
  false_merges: { count: number; offending_name_pairs: FalseMerge[] };
  cross_session_positive_pair_recall: { true_positive: number; total: number; recall: number };
  selective_risk_at_coverage: { accuracy: number; risk: number; coverage: number; confidently_placed: number; total: number };
  confusion_matrix: Record<BucketKind, Record<BucketKind, number>>;
  summary: string;
};

const kindOf = (value: string): BucketKind => value === "OWNER" ? "OWNER" : value === "UNRESOLVED" ? "UNRESOLVED" : "entity";
const ratio = (numerator: number, denominator: number) => denominator === 0 ? 0 : numerator / denominator;

/** Grades identity partitions, never relying on opaque predicted/gold cluster IDs matching. */
export const gradeResolution = (predicted: ResolutionResult, gold: ResolutionResult, mentions: readonly ResolutionMention[]): ResolutionGrade => {
  const byId = new Map(mentions.map((mention) => [mention.mention_id, mention]));
  if (byId.size !== mentions.length) throw new Error("mention IDs must be unique");
  for (const id of byId.keys()) if (!(id in predicted.assignments) || !(id in gold.assignments)) throw new Error(`missing assignment for mention: ${id}`);
  const ids = [...byId.keys()].sort();
  const members = (result: ResolutionResult) => new Map(ids.map((id) => [id, new Set(ids.filter((other) => result.assignments[other] === result.assignments[id]))]));
  const predictedMembers = members(predicted);
  const goldMembers = members(gold);
  const outcomes = {} as Record<string, MentionOutcome>;
  const outcome_counts: Record<MentionOutcome, number> = { correct: 0, "wrong-entity": 0, "wrong-bucket": 0, abstained: 0, "over-placed": 0 };
  const confusion_matrix: Record<BucketKind, Record<BucketKind, number>> = {
    entity: { entity: 0, OWNER: 0, UNRESOLVED: 0 }, OWNER: { entity: 0, OWNER: 0, UNRESOLVED: 0 }, UNRESOLVED: { entity: 0, OWNER: 0, UNRESOLVED: 0 },
  };

  for (const id of ids) {
    const actual = gold.assignments[id];
    const observed = predicted.assignments[id];
    const actualKind = kindOf(actual);
    const observedKind = kindOf(observed);
    confusion_matrix[actualKind][observedKind] += 1;
    let outcome: MentionOutcome;
    if (actualKind === "entity" && observedKind === "UNRESOLVED") outcome = "abstained";
    else if (actualKind === "UNRESOLVED" && observedKind === "entity") outcome = "over-placed";
    else if (actualKind !== observedKind || actualKind !== "entity") outcome = actual === observed ? "correct" : "wrong-bucket";
    else {
      const expected = goldMembers.get(id)!;
      const received = predictedMembers.get(id)!;
      outcome = expected.size === received.size && [...expected].every((member) => received.has(member)) ? "correct" : "wrong-entity";
    }
    outcomes[id] = outcome;
    outcome_counts[outcome] += 1;
  }

  let true_positive = 0; let false_positive = 0; let false_negative = 0;
  let crossSessionTotal = 0; let crossSessionTruePositive = 0;
  const offending_name_pairs: FalseMerge[] = [];
  for (let index = 0; index < ids.length; index += 1) for (let next = index + 1; next < ids.length; next += 1) {
    const left = ids[index]; const right = ids[next];
    if (kindOf(gold.assignments[left]) !== "entity" || kindOf(gold.assignments[right]) !== "entity") continue;
    const actualSame = gold.assignments[left] === gold.assignments[right];
    const observedSame = kindOf(predicted.assignments[left]) === "entity" && predicted.assignments[left] === predicted.assignments[right];
    if (actualSame && observedSame) true_positive += 1;
    else if (!actualSame && observedSame) {
      false_positive += 1;
      const leftName = byId.get(left)!.name; const rightName = byId.get(right)!.name;
      offending_name_pairs.push({ mention_ids: [left, right], names: [leftName, rightName], same_surface_name: leftName.trim().toLocaleLowerCase() === rightName.trim().toLocaleLowerCase() });
    } else if (actualSame) false_negative += 1;
    if (actualSame && byId.get(left)!.session_id !== byId.get(right)!.session_id) {
      crossSessionTotal += 1;
      if (observedSame) crossSessionTruePositive += 1;
    }
  }
  const precision = ratio(true_positive, true_positive + false_positive);
  const recall = ratio(true_positive, true_positive + false_negative);
  const f1 = precision + recall === 0 ? 0 : (2 * precision * recall) / (precision + recall);
  const confidently_placed = ids.filter((id) => predicted.assignments[id] !== "UNRESOLVED").length;
  const confidentCorrect = ids.filter((id) => predicted.assignments[id] !== "UNRESOLVED" && outcomes[id] === "correct").length;
  const accuracy = ratio(confidentCorrect, confidently_placed);
  const coverage = ratio(confidently_placed, ids.length);
  const crossRecall = ratio(crossSessionTruePositive, crossSessionTotal);
  const summary = `mentions=${ids.length} correct=${outcome_counts.correct} wrong_entity=${outcome_counts["wrong-entity"]} wrong_bucket=${outcome_counts["wrong-bucket"]} abstained=${outcome_counts.abstained} over_placed=${outcome_counts["over-placed"]}; pairwise P/R/F1=${precision.toFixed(3)}/${recall.toFixed(3)}/${f1.toFixed(3)}; false_merges=${offending_name_pairs.length}; cross_session_recall=${crossRecall.toFixed(3)}; selective_accuracy=${accuracy.toFixed(3)} coverage=${coverage.toFixed(3)}`;
  return { outcomes, outcome_counts, pairwise: { true_positive, false_positive, false_negative, precision, recall, f1 }, false_merges: { count: offending_name_pairs.length, offending_name_pairs }, cross_session_positive_pair_recall: { true_positive: crossSessionTruePositive, total: crossSessionTotal, recall: crossRecall }, selective_risk_at_coverage: { accuracy, risk: 1 - accuracy, coverage, confidently_placed, total: ids.length }, confusion_matrix, summary };
};
