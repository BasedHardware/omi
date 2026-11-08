import { describe, expect, it } from "vitest";
import {
  darkVendorBalance,
  isVendorBalanceDark,
  VENDOR_BALANCE_DARK_REASON,
} from "../wall-finops";
import { bigQueryFailure } from "../wall-source-error";

const TABLES = [
  "omi_finops.vendor_balance_snapshot",
  "omi_finops.vendor_balance_spend_daily",
];
const FALLBACK = "Soniox measured STT unavailable (balance line dark)";

describe("vendor balance dark state", () => {
  it("marks a missing vendor-balance table as dark with a non-error reason", () => {
    const failure = bigQueryFailure(
      {
        code: 404,
        message:
          "Not found: Table based-hardware:omi_finops.vendor_balance_snapshot was not found",
      },
      TABLES,
      FALLBACK
    );
    expect(failure.message).toBe(
      "omi_finops.vendor_balance_snapshot not found (table not created yet)"
    );
    expect(isVendorBalanceDark(failure)).toBe(true);
  });

  it("keeps a grant denial on a vendor-balance table as an error", () => {
    const failure = bigQueryFailure(
      {
        code: 403,
        message:
          "Access Denied: Table based-hardware:omi_finops.vendor_balance_spend_daily: User does not have permission",
      },
      TABLES,
      FALLBACK
    );
    expect(failure.message).toContain("missing dataViewer grant");
    expect(isVendorBalanceDark(failure)).toBe(false);
  });

  it("keeps an unnamed or unrelated failure as an error", () => {
    const unnamed = bigQueryFailure(
      { code: 404, message: "Not found" },
      TABLES,
      FALLBACK
    );
    expect(isVendorBalanceDark(unnamed)).toBe(false);
    expect(unnamed.message).toBe(FALLBACK);

    const timeout = bigQueryFailure(
      { code: 500, message: "Job timed out" },
      TABLES,
      FALLBACK
    );
    expect(isVendorBalanceDark(timeout)).toBe(false);
  });

  it("returns an empty history carrying the dark reason", () => {
    const dark = darkVendorBalance();
    expect(dark.dark).toBe(VENDOR_BALANCE_DARK_REASON);
    expect(dark.dark).toBe("Soniox balance not tracked (org key off)");
    expect(dark.snapshots).toBe(0);
    expect(dark.spend).toEqual({});
    expect(dark.flags).toEqual({});
  });
});
