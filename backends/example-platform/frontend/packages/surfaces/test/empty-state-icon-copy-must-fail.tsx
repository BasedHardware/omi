import { ProductionEmptyState } from "../src/production/ProductionPrimitives.js";

/** Red-proof: a visible sentence is not a ProductionIconName. Must not typecheck. */
export function Proof() {
  return <ProductionEmptyState icon="Some visible sentence" title="x" />;
}
