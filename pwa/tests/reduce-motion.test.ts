import { expect, test } from "bun:test";
import { createRequire } from "node:module";
import type { ReactTestRenderer } from "react-test-renderer";

// The PWA tsconfig maps "react" to its declarations; use the actual runtime.
const require = createRequire(import.meta.url);
const React = require("../../node_modules/react") as typeof import("react");
const Renderer =
  require("../../node_modules/react-test-renderer") as typeof import("react-test-renderer");
const { act } = Renderer;

test("each motion consumer follows live preference changes after another unmounts", async () => {
  const previousWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
  const previousAct = Object.getOwnPropertyDescriptor(
    globalThis,
    "IS_REACT_ACT_ENVIRONMENT"
  );
  const listeners = new Set<() => void>();
  const media = {
    matches: true,
    addEventListener: (_event: string, listener: () => void) =>
      listeners.add(listener),
    removeEventListener: (_event: string, listener: () => void) =>
      listeners.delete(listener),
  };
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: { matchMedia: () => media },
  });
  Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", {
    configurable: true,
    value: true,
  });
  let renderer: ReactTestRenderer | undefined;
  try {
    const { useReduceMotion } = await import(
      "../../react-native/src/app/useReduceMotion.web"
    );
    function Probe() {
      return React.createElement("span", null, String(useReduceMotion()));
    }
    const tree = (first: boolean) =>
      React.createElement(
        React.Fragment,
        null,
        first ? React.createElement(Probe, { key: "first" }) : null,
        React.createElement(Probe, { key: "second" })
      );
    await act(async () => {
      renderer = Renderer.create(tree(true));
    });
    const values = () =>
      renderer!.root
        .findAllByType("span")
        .map((node) => node.children.join(""));
    expect(values()).toEqual(["true", "true"]);
    expect(listeners.size).toBe(2);
    await act(async () => {
      renderer!.update(tree(false));
    });
    expect(listeners.size).toBe(1);
    for (const matches of [false, true]) {
      await act(async () => {
        media.matches = matches;
        listeners.forEach((listener) => listener());
      });
      expect(values()).toEqual([String(matches)]);
    }
    await act(async () => {
      renderer!.unmount();
    });
    renderer = undefined;
    expect(listeners.size).toBe(0);
  } finally {
    if (renderer)
      await act(async () => {
        renderer!.unmount();
      });
    if (previousWindow)
      Object.defineProperty(globalThis, "window", previousWindow);
    else Reflect.deleteProperty(globalThis, "window");
    if (previousAct)
      Object.defineProperty(
        globalThis,
        "IS_REACT_ACT_ENVIRONMENT",
        previousAct
      );
    else Reflect.deleteProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT");
  }
});
