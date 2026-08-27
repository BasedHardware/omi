import { describe, expect, it } from "vitest";

import { boardUrl } from "@/app/(protected)/dashboard/page";

describe("/dashboard platform deep links", () => {
  it("routes ?platform=macos and ?platform=mobile to their boards", () => {
    expect(boardUrl("macos")).toBe("/grafana/d/omi-tv-macos/?refresh=5m");
    expect(boardUrl("mobile")).toBe("/grafana/d/omi-tv-mobile/?refresh=5m");
  });

  it("defaults to the All-platforms board", () => {
    expect(boardUrl(null)).toBe("/grafana/d/omi-tv/?refresh=5m");
    expect(boardUrl("nonsense")).toBe("/grafana/d/omi-tv/?refresh=5m");
  });
});
