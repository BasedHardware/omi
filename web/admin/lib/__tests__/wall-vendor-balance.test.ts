import { beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({
  query: vi.fn(),
}));

vi.mock("@/lib/services/gcp-billing", () => ({
  getGcpBillingClient: () => ({ query: state.query }),
}));

import {
  darkVendorBalance,
  fetchVendorBalanceHistory,
  isVendorBalanceDark,
  VENDOR_BALANCE_DARK_REASON,
} from "../wall-finops";
import { bigQueryFailure } from "../wall-source-error";

const TABLES = [
  "omi_finops.vendor_balance_snapshot",
  "omi_finops.vendor_balance_spend_daily",
];
const FALLBACK = "Soniox measured STT unavailable (balance line dark)";

describe("vendor balance dark state: classifier", () => {
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

describe("vendor balance dark state: production catch path", () => {
  beforeEach(() => {
    state.query.mockReset();
  });

  it("resolves dark when the vendor-balance table does not exist yet", async () => {
    state.query.mockRejectedValue({
      code: 404,
      message:
        "Not found: Table based-hardware:omi_finops.vendor_balance_snapshot was not found",
    });
    await expect(fetchVendorBalanceHistory("2026-11-08")).resolves.toEqual(
      darkVendorBalance()
    );
  });

  it("rejects on a grant denial, so the leg stays an error", async () => {
    state.query.mockRejectedValue({
      code: 403,
      message:
        "Access Denied: Table based-hardware:omi_finops.vendor_balance_spend_daily: User does not have permission",
    });
    await expect(fetchVendorBalanceHistory("2026-11-08")).rejects.toThrow(
      /missing dataViewer grant/
    );
  });

  it("rejects on an unrelated failure, so the leg stays an error", async () => {
    state.query.mockRejectedValue({ code: 500, message: "Job timed out" });
    await expect(fetchVendorBalanceHistory("2026-11-08")).rejects.toThrow(
      /balance line dark/
    );
  });
});
