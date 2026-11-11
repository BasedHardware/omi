import { describe, expect, it, vi } from "vitest";

import { patchPromptActive } from "@/lib/desktop-prompts-toggle";

describe("patchPromptActive (kill-switch honesty)", () => {
  it("reports success only when the PATCH succeeded", async () => {
    const fetchImpl = vi.fn(async () => ({ ok: true }) as Response);
    await expect(patchPromptActive(fetchImpl, "p1", false)).resolves.toEqual({
      ok: true,
    });
    expect(fetchImpl).toHaveBeenCalledWith(
      "/api/omi/desktop-prompts/p1",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ active: false }),
      }),
    );
  });

  it("reports a failed kill-switch request instead of pretending it landed", async () => {
    const fetchImpl = vi.fn(
      async () => ({ ok: false, status: 502 }) as Response,
    );
    await expect(patchPromptActive(fetchImpl, "p1", false)).resolves.toEqual({
      ok: false,
      error: "toggle failed (502)",
    });
  });

  it("reports network failures the same way", async () => {
    const fetchImpl = vi.fn(async () => {
      throw new Error("offline");
    });
    await expect(patchPromptActive(fetchImpl, "p1", true)).resolves.toEqual({
      ok: false,
      error: "offline",
    });
  });
});
