import { describe, expect, it, vi } from "vitest";
import { AcpAdapterOwner } from "../src/runtime/acp-adapter-owner.js";

function adapter() {
  return { onProcessExit: undefined as (() => void) | undefined, stop: vi.fn(async () => {}) };
}

describe("bridge ACP adapter ownership", () => {
  it("ignores a retired process exit after its replacement has initialized", async () => {
    const first = adapter();
    const next = adapter();
    let initialized = true;
    let finishStop!: () => void;
    first.stop.mockImplementation(() => new Promise<void>((resolve) => { finishStop = resolve; }));
    const create = vi.fn().mockReturnValueOnce(first).mockReturnValueOnce(next);
    const owner = new AcpAdapterOwner(create, () => { initialized = false; }, vi.fn());

    owner.retire();
    expect(owner.current).toBe(next);
    expect(initialized).toBe(false);
    // The next worker initializes while the retired process is still stopping.
    initialized = true;
    first.onProcessExit!();
    expect(initialized).toBe(true);
    next.onProcessExit!();
    expect(initialized).toBe(false);
    finishStop();
    await owner.stop();
  });

  it("logs a shutdown failure and lets bridge shutdown finish", async () => {
    const current = adapter();
    current.stop.mockRejectedValue(new Error("detached after SIGKILL"));
    const log = vi.fn();
    const owner = new AcpAdapterOwner(() => current, vi.fn(), log);
    await expect(owner.stop()).resolves.toBeUndefined();
    expect(log).toHaveBeenCalledWith("ACP shutdown failed: detached after SIGKILL");
  });

  it("contains a retired adapter stop rejection without replacing the live instance again", async () => {
    const first = adapter();
    const next = adapter();
    first.stop.mockRejectedValue(new Error("retired child survived"));
    const logged = Promise.withResolvers<string>();
    const create = vi.fn().mockReturnValueOnce(first).mockReturnValueOnce(next);
    const owner = new AcpAdapterOwner(create, vi.fn(), logged.resolve);
    owner.retire();
    expect(await logged.promise).toBe("ACP shutdown failed: retired child survived");
    expect(owner.current).toBe(next);
    expect(create).toHaveBeenCalledTimes(2);
  });
});
