import { expect, test } from "bun:test";
import { fileURLToPath } from "node:url";
import { runInNewContext } from "node:vm";
import viteConfig from "../vite.config";

test("browser animation cleanup cancels frames without a Node global", async () => {
  const config = viteConfig({ command: "build" });
  const output = await Bun.build({
    entrypoints: [
      fileURLToPath(
        import.meta.resolve(
          "react-native-web/dist/vendor/react-native/Animated/animations/TimingAnimation.js"
        )
      ),
    ],
    target: "browser",
    format: "cjs",
    define: { ...config.define, "process.env.NODE_ENV": '"production"' },
  });
  const cancelled: number[] = [];
  const ended: unknown[] = [];
  const context = {
    cancelAnimationFrame: (id: number) => cancelled.push(id),
    requestAnimationFrame: () => 42,
    clearTimeout,
    setTimeout,
    ended,
    module: { exports: {} },
    exports: {},
  };
  runInNewContext(
    `${await output.outputs[0]!.text()}
      const animation = new module.exports.default({toValue: 1, useNativeDriver: false});
      animation.start(0, () => {}, (result) => ended.push(result));
      animation.stop();`,
    context
  );
  expect(cancelled).toEqual([42]);
  expect(ended).toEqual([{ finished: false }]);
});
