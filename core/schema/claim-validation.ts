import { CanonicalClaimSchema, ProvisionalClaimSchema, hasDistinctArgumentSlotIds, type CanonicalClaim, type ProvisionalClaim } from "./index";
import { validateStrict } from "./json";

/**
 * Canonical claim validation shared by ingestion and ledger writes. The
 * explicit semantic check is retained alongside the JSON Schema extension so
 * a future validator implementation cannot silently weaken slot uniqueness.
 */
export const validateCanonicalClaim = (value: unknown): value is CanonicalClaim =>
  validateStrict(CanonicalClaimSchema, value)
  && hasDistinctArgumentSlotIds(value.arguments);

export const validateProvisionalClaim = (value: unknown): value is ProvisionalClaim =>
  validateStrict(ProvisionalClaimSchema, value)
  && hasDistinctArgumentSlotIds(value.arguments);
