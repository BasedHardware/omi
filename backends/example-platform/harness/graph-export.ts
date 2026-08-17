import { compareStrings } from "../core/order";
import { readFileSync, writeFileSync } from "node:fs";
import Ajv2020 from "ajv/dist/2020.js";
import { project, walk, type GraphSnapshot } from "../core/retrieve";

export const graphBrowserExport = (snapshot: GraphSnapshot, trajectory: readonly { cycle_id: string; trajectory: object }[]) => {
  const safe = project(snapshot, { reader_account_id: snapshot.owner_account_id, grant: { grant_id: "owner-export", policy_classes: [] } });
  return {
    schema_version: "graph-browser-export-v1",
    owner_account_id: snapshot.owner_account_id,
    graph_generation: Number(snapshot.graph_generation ?? 0),
    entities: snapshot.entities.map((item) => ({ entity_id: item.entity.entity_id, handle: item.entity.handle })).sort((left, right) => compareStrings(left.entity_id, right.entity_id)),
    claims: safe.claims.map((item) => ({ revision_id: item.revision_id, lineage_id: item.claim.claim_lineage_id, predicate: item.claim.predicate })).sort((left, right) => compareStrings(left.revision_id, right.revision_id)),
    walks: snapshot.entities.map((item) => ({ anchor: `entity:${item.entity.entity_id}`, paths: walk(safe, { anchor: `entity:${item.entity.entity_id}`, max_hops: 3, result_cap: 50 }).paths })).sort((left, right) => compareStrings(left.anchor, right.anchor)),
    trajectory,
  };
};

export const validateGraphBrowserExport = (value: unknown): void => {
  const schema = JSON.parse(readFileSync(new URL("./graph-browser.schema.json", import.meta.url), "utf8"));
  const validate = new Ajv2020({ allErrors: true }).compile(schema);
  if (!validate(value)) throw new Error(`invalid graph browser export: ${validate.errors?.map((error) => `${error.instancePath || "/"} ${error.message}`).join("; ")}`);
};

export const writeGraphBrowserExport = (path: string, snapshot: GraphSnapshot, trajectory: readonly { cycle_id: string; trajectory: object }[]) => {
  const output = graphBrowserExport(snapshot, trajectory); validateGraphBrowserExport(output); writeFileSync(path, JSON.stringify(output, null, 2)); return output;
};
