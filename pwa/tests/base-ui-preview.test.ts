import { afterAll, beforeAll, expect, test } from "bun:test";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { createRequire } from "node:module";
import { join, resolve } from "node:path";

let directory: string;
let render: (props: {
  empty?: boolean;
  completeFirst?: boolean;
  initialPhase?: string;
  mobile?: boolean;
}) => string;

// Like chat-markdown.test, resolve real React instead of the PWA's type-only
// TS alias. Keep the bundled runtime isolated from other tests' RN mocks.
beforeAll(async () => {
  const root = resolve(import.meta.dir, "../..");
  directory = await mkdtemp(join(tmpdir(), "omi-base-ui-"));
  const entry = join(directory, "entry.tsx");
  await writeFile(
    entry,
    `
    import React from "react";
    import {renderToStaticMarkup} from ${JSON.stringify(
      join(root, "node_modules/react-dom/server.bun.js")
    )};
    import {Preview} from ${JSON.stringify(
      join(root, "pwa/src/base-ui/Preview.tsx")
    )};
    import {previewOutcomes} from ${JSON.stringify(
      join(root, "pwa/src/base-ui/fixtures.ts")
    )};
    export function render({empty, completeFirst, ...props}) {
      const initialOutcomes = previewOutcomes(empty);
      if (completeFirst) initialOutcomes.tasks.value.items[0].completed = true;
      return renderToStaticMarkup(React.createElement(Preview, {...props, initialOutcomes}));
    }
  `
  );
  const built = await Bun.build({
    entrypoints: [entry],
    target: "node",
    format: "cjs",
    plugins: [
      {
        name: "web-runtime",
        setup(build) {
          build.onResolve({ filter: /^react$/ }, () => ({
            path: join(root, "node_modules/react/index.js"),
          }));
        },
      },
    ],
  });
  expect(built.success).toBe(true);
  const module = { exports: {} as { render: typeof render } };
  new Function("module", "exports", "require", await built.outputs[0]!.text())(
    module,
    module.exports,
    createRequire(import.meta.url)
  );
  render = module.exports.render;
});

afterAll(async () => {
  if (directory) await rm(directory, { recursive: true, force: true });
});

test("owned Base UI surface renders the next unfinished task, not generic hero copy", () => {
  const html = render({ completeFirst: true });
  expect(html).toContain("<h1>Review the ideas for the next release</h1>");
  expect(html).toContain("On your list · 1 open task");
  expect(html).toContain('aria-label="Main navigation"');
  expect(html).toContain('role="checkbox"');
  expect(html).not.toContain("YOUR PERSONAL CONTEXT");
  expect(html).not.toContain("Enter to submit");
});

test("loading and failed reads cannot masquerade as an empty day", () => {
  for (const [initialPhase, title] of [
    ["initial-loading", "Getting your day ready"],
    ["unavailable", "Your daily brief is waiting"],
  ] as const) {
    const html = render({ empty: true, initialPhase });
    expect(html).toContain(`<h1>${title}</h1>`);
    expect(html).toContain("Tasks are not loaded yet.");
    expect(html).not.toContain("No tasks yet.");
  }
  const empty = render({ empty: true });
  expect(empty).toContain("<h1>What’s on your mind?</h1>");
  expect(empty).toContain("No tasks yet.");
});

test("mobile retains Search default and labels the local-only fixture boundary", () => {
  const html = render({ mobile: true });
  expect(html).toContain('aria-label="Search history"');
  expect(html).toContain('data-theme="dark"');
  expect(html).toContain("Edits stay in this preview");
  expect(html).not.toContain('aria-label="Ask Omi"');
});

test("desktop chrome separates window decoration and icon actions from navigation", () => {
  const html = render({});
  expect(html).toContain(
    'aria-label="macOS window controls (visual preview only)"'
  );
  const settings = html.match(
    /<button\b[^>]*aria-label="Settings"[^>]*>(.*?)<\/button>/s
  );
  expect(settings).not.toBeNull();
  expect(settings![1]).toContain("<svg");
  expect(settings![1].replace(/<[^>]*>/g, "").trim()).toBe("");
  const recall = html.match(
    /<button\b[^>]*aria-label="Recall capture preview"[^>]*>(.*?)<\/button>/s
  );
  expect(recall?.[0]).toContain('aria-pressed="false"');
  expect(recall?.[1]).toContain("lucide-monitor");
});

test.each([false, true])(
  "all three input modes are labelled icon-only buttons (mobile=%s)",
  (mobile) => {
    const html = render({ mobile });
    for (const mode of ["Ask", "Search", "Recall"]) {
      const button = html.match(
        new RegExp(
          `<button\\b[^>]*aria-label="${mode} mode"[^>]*>(.*?)<\\/button>`,
          "s"
        )
      );
      expect(button).not.toBeNull();
      expect(button![1]).toContain("<svg");
      expect(button![1].replace(/<[^>]*>/g, "").trim()).toBe("");
      expect(button![0]).toContain(
        `aria-pressed="${mode === (mobile ? "Search" : "Ask")}"`
      );
    }
    if (mobile) expect(html).not.toContain('class="traffic-lights"');
  }
);
