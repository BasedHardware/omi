import { readFileSync, readdirSync } from "node:fs";
import { relative, resolve } from "node:path";

/** web/admin — the root the app/ directory lives under. */
export const ROOT = resolve(__dirname, "../../..");

const METHOD =
  /^export (?:async function|const) (GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\b/gm;

export type Handler = {
  key: string;
  file: string;
  method: string;
  path: string;
};

/** Every exported API handler under app/api, keyed as "METHOD /api/path". */
export function handlers(): Handler[] {
  const found: Handler[] = [];
  const visit = (dir: string) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = resolve(dir, entry.name);
      if (entry.isDirectory()) visit(full);
      else if (entry.name === "route.ts") {
        const path =
          "/" + relative(resolve(ROOT, "app"), dir).split("\\").join("/");
        for (const [, method] of Array.from(
          readFileSync(full, "utf8").matchAll(METHOD)
        )) {
          found.push({ key: `${method} ${path}`, file: full, method, path });
        }
      }
    }
  };
  visit(resolve(ROOT, "app/api"));
  return found;
}

/** Route params with every [dynamic] segment resolved to "x1". */
export function paramsFor(path: string) {
  const params: Record<string, string> = {};
  for (const [, name] of Array.from(path.matchAll(/\[(\w+)\]/g)))
    params[name] = "x1";
  return { params: Promise.resolve(params) };
}

export function concrete(path: string) {
  return path.replace(/\[(\w+)\]/g, "x1");
}
