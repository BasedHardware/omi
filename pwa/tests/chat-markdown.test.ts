import { expect, test } from "bun:test";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { createRequire } from "node:module";
import { join, resolve } from "node:path";

test("Streamdown renders incremental markdown without remote images, raw HTML or unsafe links", async () => {
  const root = resolve(import.meta.dir, "../..");
  const directory = await mkdtemp(join(tmpdir(), "omi-markdown-"));
  try {
    const entry = join(directory, "entry.tsx");
    await writeFile(
      entry,
      `
      import React from "react";
      import {renderToStaticMarkup} from ${JSON.stringify(
        join(root, "node_modules/react-dom/server.bun.js")
      )};
      import {ChatMessageContent} from ${JSON.stringify(
        join(root, "react-native/src/ui/ChatMessageContent.web.tsx")
      )};
      export function renderCases(cases) {return cases.map(props => renderToStaticMarkup(React.createElement(ChatMessageContent, props)));}
    `
    );
    const built = await Bun.build({
      entrypoints: [entry],
      outdir: directory,
      naming: "[name].[ext]",
      target: "node",
      format: "cjs",
      plugins: [
        {
          name: "web-runtime",
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
    const output = built.outputs.find((file) => file.path.endsWith(".js"))!;
    const module = {
      exports: {} as { renderCases: (cases: unknown[]) => string[] },
    };
    new Function("module", "exports", "require", await output.text())(
      module,
      module.exports,
      createRequire(import.meta.url)
    );
    const { renderCases } = module.exports;
    const [partial, complete, hostile, decorated] = renderCases([
      { text: "**Hello", streaming: true, reduceMotion: true },
      {
        text: "**Hello world**\n\n- first\n- second\n\n```js\nconst x = 1;\n```",
        streaming: false,
      },
      {
        text: '[safe](https://example.com/path) [bad](javascript:alert(1)) [credentials](https://user:pass@example.com) ![private image](https://attacker.invalid/pixel)\n\n<img src="https://attacker.invalid/raw" onerror="alert(1)"><iframe src="https://attacker.invalid/frame"></iframe>',
        streaming: false,
      },
      {
        text: "*italic* ~~removed~~\n\n- [x] done",
        streaming: true,
        reduceMotion: false,
      },
    ]);
    expect(decorated).toContain("<em>");
    expect(decorated).toContain("<del>");
    expect(decorated).toContain('type="checkbox"');
    expect(decorated).toContain('aria-label="Completed task"');
    expect(decorated).toContain("data-sd-animate");
    expect(partial).toContain("<strong");
    expect(partial).toContain("Hello");
    expect(partial).not.toContain("data-sd-animate");
    expect(complete).toContain("Hello world");
    expect(complete).toContain("<li");
    expect(complete).toContain("<pre");
    expect(complete).toContain("const x = 1;");
    expect(hostile).toContain('href="https://example.com/path"');
    expect(hostile).toContain('rel="noopener noreferrer"');
    expect(hostile).toContain("private image");
    expect(hostile).not.toContain('href="javascript:');
    expect(hostile).not.toContain('href="https://user:pass');
    expect(hostile).not.toMatch(/<(img|iframe|script)\b/i);
    expect(hostile).not.toContain('src="https://attacker.invalid');
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
