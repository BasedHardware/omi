import { expect, test } from "bun:test";

const source = await Bun.file(new URL("./dev-server.ts", import.meta.url)).text();

const occurrences = (pattern: RegExp): number => source.match(pattern)?.length ?? 0;

test("dev-server composes one SQLite store set into its one registered service", () => {
  expect(occurrences(/\bBun\.serve\s*\(/g)).toBe(1);
  expect(occurrences(/\bcreateSqliteLocalServiceStores\s*\(\s*db\s*\)/g)).toBe(1);
  expect(source).toContain("stores,");
  expect(source).toContain("fetch: service.app.fetch");
  expect(source).toContain("websocket: service.websocket");
  expect(source.indexOf("createSqliteLocalServiceStores(db)")).toBeLessThan(
    source.indexOf("createLocalDevService({"),
  );
  expect(source).toContain("databasePath: process.env.OMI_QA_DB || \":memory:\"");
});

test("dev-server keeps the producer endpoint inside the registered local composition", () => {
  expect(source).not.toMatch(/registerQaEvidenceRoutes|\/v1\/qa\/evidence/);
  expect(source).not.toMatch(/integration\/server|write-journey-door|qa-api-server/);
});

test("producer evidence has one composition site: the registered local service", async () => {
  const root = new URL("../../../", import.meta.url);
  const callers: string[] = [];
  for await (const relative of new Bun.Glob("apps/service/**/*.ts").scan({ cwd: root.pathname })) {
    if (relative.endsWith(".test.ts") || relative.endsWith("routes/qa-evidence.ts")) continue;
    const code = await Bun.file(new URL(relative, root)).text();
    if (/\bregisterQaEvidenceRoutes\s*\(/.test(code)) callers.push(relative);
  }
  expect(callers).toEqual(["apps/service/app-facing.ts"]);
});
