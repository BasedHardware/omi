import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const captured = vi.hoisted(() => ({ swrOptions: null as unknown }));

vi.mock("swr", () => ({
  default: vi.fn((_key: unknown, _fetcher: unknown, options: unknown) => {
    captured.swrOptions = options;
    return { data: null, error: null, isLoading: false };
  }),
}));
vi.mock("@/hooks/useAuthToken", () => ({
  useAuthToken: () => ({ token: "token", loading: false }),
  authenticatedFetcher: vi.fn(),
}));

import useSWR from "swr";
import { useAdminAccess } from "@/hooks/useAdminAccess";

describe("useAdminAccess", () => {
  it("follows role changes without a reload: revalidates on focus and every minute", () => {
    renderHook(() => useAdminAccess());
    expect(vi.mocked(useSWR)).toHaveBeenCalledTimes(1);
    expect(captured.swrOptions).toMatchObject({
      revalidateOnFocus: true,
      refreshInterval: 60_000,
    });
  });

  it("asks for the member's own access with their token", () => {
    renderHook(() => useAdminAccess());
    expect(vi.mocked(useSWR).mock.calls[0][0]).toEqual([
      "/api/omi/access",
      "token",
    ]);
  });
});
