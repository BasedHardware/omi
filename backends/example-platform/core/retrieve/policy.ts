import type { PolicyClass } from "./index";

type PolicyDimension = keyof PolicyClass;

// Each dimension is a diamond partial order: generic is bottom, restricted is top,
// and every concrete label (including unknown labels) is an opaque peer.
export const policyDominates = (dimension: PolicyDimension, effective: string, contributor: string): boolean => {
  void dimension;
  return effective === contributor || effective === "restricted" || contributor === "generic";
};

const joinDimension = (dimension: PolicyDimension, values: readonly string[]): string => values.reduce((effective, value) => {
  if (policyDominates(dimension, effective, value)) return effective;
  if (policyDominates(dimension, value, effective)) return value;
  return "restricted";
}, "generic");

/** Least upper bound in the policy lattice, independent of contributor ordering. */
export const restrictivePolicyJoin = (contributors: readonly PolicyClass[]): PolicyClass => ({
  subject_class: joinDimension("subject_class", contributors.map((item) => item.subject_class)),
  sensitivity: joinDimension("sensitivity", contributors.map((item) => item.sensitivity)),
  capture_class: joinDimension("capture_class", contributors.map((item) => item.capture_class)),
});

/** A result may only be rendered at the same or a stricter policy in every dimension. */
export const validateRestrictiveJoin = (effective: PolicyClass, contributors: readonly PolicyClass[]): boolean =>
  contributors.every((item) => (policyDominates("subject_class", effective.subject_class, item.subject_class) && policyDominates("sensitivity", effective.sensitivity, item.sensitivity) && policyDominates("capture_class", effective.capture_class, item.capture_class)));
