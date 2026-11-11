import { describe, expect, it, vi } from "vitest";
import { createStdoutLineSender } from "../src/stdout-line-sender.js";

describe("createStdoutLineSender", () => {
  it("writes queued lines immediately while the pipe accepts data", () => {
    const written: string[] = [];
    const send = createStdoutLineSender(
      (chunk) => {
        written.push(chunk);
        return true;
      },
      () => {
        throw new Error("drain should not be needed");
      }
    );

    send("a\n");
    send("b\n");
    expect(written).toEqual(["a\n", "b\n"]);
  });

  it("waits for drain when write signals backpressure, then flushes the rest", () => {
    const written: string[] = [];
    let drainListener: (() => void) | undefined;
    let accept = false;
    const send = createStdoutLineSender(
      (chunk) => {
        written.push(chunk);
        return accept;
      },
      (listener) => {
        drainListener = listener;
      }
    );

    send("one\n");
    send("two\n");
    send("three\n");
    expect(written).toEqual(["one\n"]);
    expect(drainListener).toBeTypeOf("function");

    accept = true;
    drainListener?.();
    expect(written).toEqual(["one\n", "two\n", "three\n"]);
  });

  it("continues after a write error instead of wedging the queue", () => {
    const written: string[] = [];
    const errors: unknown[] = [];
    let calls = 0;
    const send = createStdoutLineSender(
      (chunk) => {
        calls += 1;
        if (calls === 1) throw new Error("EPIPE");
        written.push(chunk);
        return true;
      },
      () => {},
      (error) => {
        errors.push(error);
      }
    );

    send("bad\n");
    send("good\n");
    expect(errors).toHaveLength(1);
    expect(written).toEqual(["good\n"]);
  });
});
