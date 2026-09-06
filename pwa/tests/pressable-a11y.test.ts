import { expect, test } from "bun:test";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve, join } from "node:path";

test("shared pressables render native accessibility state as real web ARIA attributes", async () => {
  const directory = await mkdtemp(join(tmpdir(), "omi-pressable-"));
  const root = resolve(import.meta.dir, "../..");
  const entry = join(directory, "entry.tsx");
  try {
    await writeFile(
      entry,
      `
      import React from "react";
      import {renderToStaticMarkup} from ${JSON.stringify(
        join(root, "node_modules/react-dom/server.bun.js")
      )};
      import {FocusPressable} from ${JSON.stringify(
        join(root, "react-native/src/ui/Pressable.tsx")
      )};
      const cases = JSON.parse(await Bun.stdin.text());
      process.stdout.write(JSON.stringify(cases.map(props => renderToStaticMarkup(React.createElement(FocusPressable, props)))));
    `
    );
    const built = await Bun.build({
      entrypoints: [entry],
      outdir: directory,
      naming: "render.js",
      target: "bun",
      plugins: [
        {
          name: "actual-react-native-web",
          setup(build) {
            build.onResolve({ filter: /^react$/ }, () => ({
              path: join(root, "node_modules/react/index.js"),
            }));
            build.onResolve({ filter: /^react-native$/ }, () => ({
              path: join(
                root,
                "node_modules/react-native-web/dist/cjs/index.js"
              ),
            }));
          },
        },
      ],
    });
    expect(built.success).toBe(true);
    const output = join(directory, "render.js");
    await writeFile(output, await built.outputs[0]!.text());
    const cases = [
      {
        accessibilityRole: "checkbox",
        accessibilityState: {
          checked: true,
          selected: false,
          expanded: true,
          busy: false,
          disabled: true,
        },
      },
      { accessibilityRole: "checkbox", accessibilityState: { checked: false } },
      {
        accessibilityRole: "checkbox",
        accessibilityState: { checked: "mixed" },
      },
      {
        accessibilityRole: "checkbox",
        accessibilityState: { checked: true },
        "aria-checked": false,
      },
      { accessibilityRole: "button" },
    ];
    const subprocess = Bun.spawn({
      cmd: [process.execPath, output],
      cwd: directory,
      stdin: new Blob([JSON.stringify(cases)]),
      stdout: "pipe",
      stderr: "pipe",
    });
    const [exitCode, stdout, stderr] = await Promise.all([
      subprocess.exited,
      new Response(subprocess.stdout).text(),
      new Response(subprocess.stderr).text(),
    ]);
    expect({ exitCode, stderr: stderr.slice(0, 2000) }).toEqual({
      exitCode: 0,
      stderr: "",
    });
    const [completed, unchecked, mixed, overridden, button] = JSON.parse(
      stdout
    ) as string[];
    for (const attribute of [
      'role="checkbox"',
      'aria-checked="true"',
      'aria-selected="false"',
      'aria-expanded="true"',
      'aria-busy="false"',
      'aria-disabled="true"',
    ])
      expect(completed).toContain(attribute);
    expect(unchecked).toContain('aria-checked="false"');
    expect(mixed).toContain('aria-checked="mixed"');
    expect(overridden).toContain('aria-checked="false"');
    expect(button).not.toContain("aria-checked");
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
