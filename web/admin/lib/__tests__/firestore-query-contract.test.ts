import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import path from "node:path";
import ts from "typescript";
import { describe, expect, it } from "vitest";

type Shape = {
  collection: string;
  scope: string;
  filters: [string, string][];
  orders: [string, string][];
  sums: string[];
  sites: Set<number>;
};
type Manifest = {
  indexes: {
    collectionGroup: string;
    queryScope: string;
    fields: { fieldPath: string; order?: string; arrayConfig?: string }[];
  }[];
  fieldOverrides: {
    collectionGroup: string;
    fieldPath: string;
    indexes?: { queryScope?: string; order?: string; arrayConfig?: string }[];
  }[];
};
const root = path.resolve(process.cwd());
const manifest: Manifest = JSON.parse(
  readFileSync(path.resolve(root, "../../firestore.indexes.json"), "utf8")
);
const methods = new Set(["collectionGroup", "where", "orderBy", "aggregate"]);

function files(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    if (
      entry.name.startsWith(".") ||
      ["node_modules", "__tests__"].includes(entry.name)
    )
      return [];
    const full = path.join(directory, entry.name);
    return entry.isDirectory()
      ? files(full)
      : /\.tsx?$/.test(full) && !/\.test\./.test(full)
      ? [full]
      : [];
  });
}

function extract(source: string): { shapes: Shape[]; uncovered: string[] } {
  const tree = ts.createSourceFile(
    "server.ts",
    source,
    ts.ScriptTarget.Latest,
    true
  );
  const declarations = new Map<string, ts.Expression | null>();
  const constants = new Set<string>();
  const calls: ts.CallExpression[] = [];
  const visit = (node: ts.Node) => {
    if (
      ts.isVariableDeclaration(node) &&
      ts.isIdentifier(node.name) &&
      node.initializer
    ) {
      declarations.set(
        node.name.text,
        declarations.has(node.name.text) ? null : node.initializer
      );
      if (
        ts.isVariableDeclarationList(node.parent) &&
        node.parent.flags & ts.NodeFlags.Const
      )
        constants.add(node.name.text);
    }
    if (ts.isCallExpression(node)) calls.push(node);
    ts.forEachChild(node, visit);
  };
  visit(tree);
  const literal = (node: ts.Expression | undefined): string | null => {
    if (!node) return null;
    if (ts.isStringLiteralLike(node)) return node.text;
    if (ts.isIdentifier(node)) {
      if (!constants.has(node.text)) return null;
      const value = declarations.get(node.text);
      return value && value !== node ? literal(value) : null;
    }
    if (
      ts.isCallExpression(node) &&
      ts.isPropertyAccessExpression(node.expression) &&
      node.expression.name.text === "documentId"
    )
      return "__name__";
    return null;
  };
  const resolve = (
    node: ts.Expression,
    seen = new Set<string>()
  ): Shape | null => {
    if (
      ts.isAsExpression(node) ||
      ts.isParenthesizedExpression(node) ||
      ts.isTypeAssertionExpression(node)
    )
      return resolve(node.expression, seen);
    if (ts.isIdentifier(node)) {
      if (seen.has(node.text)) return null;
      const value = declarations.get(node.text);
      return value
        ? resolve(value, new Set(Array.from(seen).concat(node.text)))
        : null;
    }
    if (
      !ts.isCallExpression(node) ||
      !ts.isPropertyAccessExpression(node.expression)
    )
      return null;
    const method = node.expression.name.text;
    if (method === "collection" || method === "collectionGroup") {
      const collection = literal(node.arguments[0]);
      if (!collection) return null;
      return {
        collection,
        scope: method === "collectionGroup" ? "COLLECTION_GROUP" : "COLLECTION",
        filters: [],
        orders: [],
        sums: [],
        sites: new Set(method === "collectionGroup" ? [node.pos] : []),
      };
    }
    const shape = resolve(node.expression.expression, seen);
    if (!shape) return null;
    if (method === "where") {
      const field = literal(node.arguments[0]);
      const op = literal(node.arguments[1]);
      if (!field || !op) return null;
      shape.filters.push([field, op]);
      shape.sites.add(node.pos);
    } else if (method === "orderBy") {
      const field = literal(node.arguments[0]);
      const direction = node.arguments[1] ? literal(node.arguments[1]) : "asc";
      if (!field || !direction || !["asc", "desc"].includes(direction))
        return null;
      shape.orders.push([
        field,
        direction === "desc" ? "DESCENDING" : "ASCENDING",
      ]);
      shape.sites.add(node.pos);
    } else if (method === "aggregate") {
      if (
        node.arguments.length !== 1 ||
        !ts.isObjectLiteralExpression(node.arguments[0]) ||
        node.arguments[0].properties.some(
          (property) =>
            !ts.isPropertyAssignment(property) ||
            !ts.isCallExpression(property.initializer)
        )
      )
        return null;
      let valid = true;
      const aggregates = (child: ts.Node) => {
        if (
          ts.isCallExpression(child) &&
          ts.isPropertyAccessExpression(child.expression) &&
          ts.isIdentifier(child.expression.expression) &&
          child.expression.expression.text === "AggregateField"
        ) {
          if (child.expression.name.text === "sum") {
            const field = literal(child.arguments[0]);
            if (field) shape.sums.push(field);
            else valid = false;
          } else if (child.expression.name.text !== "count") valid = false;
        } else if (ts.isCallExpression(child)) valid = false;
        ts.forEachChild(child, aggregates);
      };
      node.arguments.forEach(aggregates);
      if (!valid) return null;
      shape.sites.add(node.pos);
    } else if (
      !["get", "count", "limit", "select", "startAfter", "offset"].includes(
        method
      )
    ) {
      return null;
    }
    return shape;
  };
  const shapes: Shape[] = [];
  const handled = new Set<number>();
  for (const call of calls) {
    if (
      !ts.isPropertyAccessExpression(call.expression) ||
      call.expression.name.text !== "get"
    )
      continue;
    const shape = resolve(call);
    if (shape) {
      shapes.push(shape);
      shape.sites.forEach((site) => handled.add(site));
    }
  }
  const uncovered = calls
    .filter(
      (call) =>
        ts.isPropertyAccessExpression(call.expression) &&
        methods.has(call.expression.name.text) &&
        !handled.has(call.pos)
    )
    .map((call) => call.getText(tree));
  return { shapes, uncovered };
}

function served(shape: Shape, config = manifest): boolean {
  const equality = new Set(
    shape.filters
      .filter(([, op]) => ["==", "in"].includes(op))
      .map(([field]) => field)
      .filter((field) => field !== "__name__")
  );
  const ranges = new Set(
    shape.filters
      .filter(([, op]) => ["<", "<=", ">", ">=", "!=", "not-in"].includes(op))
      .map(([field]) => field)
  );
  if (
    shape.filters.some(
      ([, op]) =>
        !["==", "in", "<", "<=", ">", ">=", "!=", "not-in"].includes(op)
    )
  )
    return false;
  const orders = [...shape.orders];
  const direction = orders.at(-1)?.[1] ?? "ASCENDING";
  for (const field of Array.from(ranges).sort())
    if (!orders.some(([existing]) => existing === field))
      orders.push([field, direction]);
  const nameDirection =
    orders.find(([field]) => field === "__name__")?.[1] ?? direction;
  const fields: [string, string][] = Array.from(equality)
    .sort()
    .map((field) => [field, "ASCENDING"]);
  for (const [field, mode] of orders)
    if (
      field !== "__name__" &&
      !fields.some(([existing]) => existing === field)
    )
      fields.push([field, mode]);
  for (const field of shape.sums.sort())
    if (!fields.some(([existing]) => existing === field))
      fields.push([field, "ASCENDING"]);
  fields.push(["__name__", nameDirection]);
  if (
    config.indexes.some((index) => {
      if (
        index.collectionGroup !== shape.collection ||
        index.queryScope !== shape.scope ||
        index.fields.length !== fields.length
      )
        return false;
      const prefix = index.fields.slice(0, equality.size);
      if (
        prefix.some(
          (field) =>
            !equality.has(field.fieldPath) ||
            !["ASCENDING", "DESCENDING"].includes(field.order ?? "")
        )
      )
        return false;
      return index.fields
        .slice(equality.size)
        .every(
          (field, i) =>
            field.fieldPath === fields[equality.size + i][0] &&
            field.order === fields[equality.size + i][1]
        );
    })
  )
    return true;
  const automatic = (field: string, mode: string) => {
    const overrides = config.fieldOverrides
      .filter(
        (entry) =>
          entry.collectionGroup === shape.collection &&
          (entry.fieldPath === "*" ||
            entry.fieldPath === field ||
            field.startsWith(entry.fieldPath + ".")) &&
          entry.indexes !== undefined
      )
      .sort((a, b) => b.fieldPath.length - a.fieldPath.length);
    const override = overrides[0];
    if (!override) return shape.scope === "COLLECTION";
    return override.indexes!.some(
      (index) =>
        (index.queryScope ?? "COLLECTION") === shape.scope &&
        index.order === mode
    );
  };
  if (fields.length === 1 && nameDirection === "ASCENDING") return true;
  if (!ranges.size && !shape.orders.length && !shape.sums.length)
    return Array.from(equality).every(
      (field) => automatic(field, "ASCENDING") || automatic(field, "DESCENDING")
    );
  return (
    fields.length === 2 &&
    !shape.sums.length &&
    nameDirection === fields[0][1] &&
    automatic(fields[0][0], fields[0][1])
  );
}

const dynamicFiles = {
  "app/api/omi/fair-use/flagged/route.ts":
    "aefe1efc684ab222398480099ab3ca1ea8a91072e6fb26cc9a2984ead97d6456",
  "lib/services/gateway-ledger.ts":
    "7968ba2d236bfeb8f26f403c43d6cb37d78051140662f1cfabb12bea6d646e2f",
} as const;

function dynamicFingerprint(source: string): string {
  const tree = ts.createSourceFile(
    "server.ts",
    source,
    ts.ScriptTarget.Latest,
    true
  );
  return createHash("sha256")
    .update(ts.createPrinter({ removeComments: true }).printFile(tree))
    .digest("hex");
}

function dynamicShapes(file: string, source: string): Shape[] {
  const blank = (collection: string, scope = "COLLECTION"): Shape => ({
    collection,
    scope,
    filters: [],
    orders: [],
    sums: [],
    sites: new Set(),
  });
  if (file === "app/api/omi/fair-use/flagged/route.ts") {
    expect(source).toMatch(/collectionGroup\(['"]fair_use_state['"]\)/);
    expect(source).toMatch(/where\(['"]stage['"],\s*['"]==['"],\s*stage\)/);
    expect(source).toMatch(
      /where\(['"]stage['"],\s*['"]in['"],\s*\[['"]warning['"],\s*['"]throttle['"],\s*['"]restrict['"]\]\)/
    );
    expect(source).toMatch(/orderBy\(['"]updated_at['"],\s*['"]desc['"]\)/);
    const builders = extract(source).uncovered;
    expect(builders).toHaveLength(3);
    return ["==", "in"].map((op) => ({
      ...blank("fair_use_state", "COLLECTION_GROUP"),
      filters: [["stage", op]],
      orders: [["updated_at", "DESCENDING"]],
    }));
  }
  expect(source).toMatch(/const COLLECTION = ["']llm_gateway_attempts["']/);
  expect(source).toMatch(/const COST_FIELD = ["']estimated_cost_micro_usd["']/);
  expect(source).toMatch(/query = query\.where\(field, ["']==["'], value\)/);
  expect(source).toMatch(/AggregateField\.sum\(COST_FIELD\)/);
  expect(source).toMatch(
    /const filters: Filter\[\] = \[\[["']date["'], date\]\]/
  );
  expect(source).toMatch(/if \(extra\) filters\.push\(extra\)/);
  expect(source).toMatch(
    /if \(payerScoped\) filters\.push\(\[["']payer["'], ["']omi["']\]\)/
  );
  expect(source).toMatch(
    /dayFilters\(date, payerScoped, \[["']provider["'], p\]\)/
  );
  expect(source).toMatch(
    /dayFilters\(date, payerScoped, \[["']feature["'], f\]\)/
  );
  expect(extract(source).uncovered).toHaveLength(1);
  return [false, true].flatMap((payer) =>
    [null, "provider", "feature"].map((extra) => ({
      ...blank("llm_gateway_attempts"),
      filters: [
        "date",
        ...(extra ? [extra] : []),
        ...(payer ? ["payer"] : []),
      ].map((field): [string, string] => [field, "=="]),
      sums: ["estimated_cost_micro_usd"],
    }))
  );
}

describe("server Firestore manifest contract: static chains, aliases, and reviewed dynamic profiles", () => {
  it("extracts every server query builder or fails closed for review", () => {
    const inventory: Record<string, number> = {};
    const sources = files(root);
    const shapesByFile: Record<string, Omit<Shape, "sites">[]> = {};
    for (const file of sources) {
      const source = readFileSync(file, "utf8");
      if (/^[\s]*["']use client["']/.test(source)) continue;
      const relative = path.relative(root, file).split(path.sep).join("/");
      const capture = extract(source);
      let shapes = capture.shapes;
      if (relative in dynamicFiles) {
        expect(
          dynamicFingerprint(source),
          `${relative}: review the dynamic caller profiles before repinning`
        ).toBe(dynamicFiles[relative as keyof typeof dynamicFiles]);
        shapes = dynamicShapes(relative, source);
      } else expect(capture.uncovered, relative).toEqual([]);
      if (!shapes.length) continue;
      inventory[relative] = shapes.length;
      shapesByFile[relative] = shapes.map(({ sites, ...shape }) => shape);
      for (const shape of shapes)
        expect(
          served(shape),
          `${relative}: ${JSON.stringify({ ...shape, sites: undefined })}`
        ).toBe(true);
    }
    expect(
      inventory["app/api/omi/stats/notifications/route.ts"]
    ).toBeGreaterThanOrEqual(7);
    expect(Object.keys(inventory)).toContain(
      "app/api/omi/stats/message-ratings/route.ts"
    );
    expect(Object.keys(inventory)).toContain("lib/services/gateway-ledger.ts");
    const exportPath = process.env.FIRESTORE_ADMIN_SHAPES_EXPORT;
    if (exportPath)
      writeFileSync(exportPath, JSON.stringify(shapesByFile, null, 2) + "\n");
  });

  it("detects notification count-range scope and direction regressions", () => {
    const { shapes } = extract(
      readFileSync(
        path.join(root, "app/api/omi/stats/notifications/route.ts"),
        "utf8"
      )
    );
    const notifications = shapes.filter(
      (shape) =>
        shape.collection === "messages" && shape.scope === "COLLECTION_GROUP"
    );
    expect(notifications).toHaveLength(2);
    expect(notifications.map((shape) => shape.filters)).toEqual(
      Array(2).fill([
        ["app_id", "=="],
        ["created_at", ">="],
        ["created_at", "<="],
      ])
    );
    const without = {
      ...manifest,
      indexes: manifest.indexes.filter(
        (index) =>
          !(
            index.collectionGroup === "messages" &&
            index.queryScope === "COLLECTION_GROUP" &&
            index.fields.map((field) => field.fieldPath).join(",") ===
              "app_id,created_at,__name__"
          )
      ),
    };
    expect(notifications.every((shape) => served(shape))).toBe(true);
    expect(notifications.every((shape) => !served(shape, without))).toBe(true);
  });

  it("removing an additive single-field override refuses the group scans it serves", () => {
    const cases: [string, string, string][] = [
      [
        "app/api/omi/fair-use/case/[caseRef]/route.ts",
        "fair_use_events",
        "case_ref",
      ],
      ["app/api/omi/stats/infra-costs/route.ts", "llm_usage", "date"],
    ];
    for (const [relative, collection, field] of cases) {
      const shapes = extract(
        readFileSync(path.join(root, relative), "utf8")
      ).shapes.filter(
        (shape) =>
          shape.collection === collection && shape.scope === "COLLECTION_GROUP"
      );
      expect(shapes.length, relative).toBeGreaterThan(0);
      const removed: Manifest = {
        ...manifest,
        fieldOverrides: manifest.fieldOverrides.filter(
          (entry) =>
            !(entry.collectionGroup === collection && entry.fieldPath === field)
        ),
      };
      const collectionsOnly: Manifest = {
        ...manifest,
        fieldOverrides: manifest.fieldOverrides.map((entry) =>
          entry.collectionGroup === collection && entry.fieldPath === field
            ? {
                ...entry,
                indexes: (entry.indexes ?? []).filter(
                  (index) =>
                    (index.queryScope ?? "COLLECTION") !== "COLLECTION_GROUP"
                ),
              }
            : entry
        ),
      };
      for (const shape of shapes) {
        expect(served(shape), relative).toBe(true);
        expect(served(shape, removed), relative).toBe(false);
        expect(served(shape, collectionsOnly), relative).toBe(false);
      }
    }
  });

  it("refuses unresolved dynamic fields and newly reassigned query modifiers", () => {
    expect(
      extract("const q=db.collection('c'); q.where(field,'==',v).get();")
        .uncovered
    ).toHaveLength(1);
    expect(
      extract("let q=db.collection('c'); q=q.where('f','==',v); q.get();")
        .uncovered
    ).toHaveLength(1);
    expect(
      extract("db.collection('c').orderBy('t', direction).get();").uncovered
    ).toHaveLength(1);
    expect(
      extract(
        "db.collection('c').aggregate({value: AggregateField.average('x')}).get();"
      ).uncovered
    ).toHaveLength(1);
    expect(
      extract(
        "function a(){const q=db.collection('a');q.where('f','==',v).get();} function b(){const q=db.collection('b');q.where('f','==',v).get();}"
      ).uncovered
    ).toHaveLength(2);
    const capture = extract(
      "const ref=db.collection('c'); ref.where('f','==',v).orderBy('t','desc').count().get();"
    );
    expect(capture.uncovered).toEqual([]);
    expect(served(capture.shapes[0], { indexes: [], fieldOverrides: [] })).toBe(
      false
    );
  });
});
