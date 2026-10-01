import { compareStrings } from "../core/order";
import type { Entity } from "../core/schema";
import type { EntityTable } from "../core/resolve/entities";
import type { LocalHandle } from "../core/resolve/mentions";
import { invokeEntityStrategy } from "../drivers/model/entity-edge";
import type { ModelPort } from "../drivers/model/port";

export type ResolutionMention = { mention_id: string; name: string; type: "person" | "organization"; session_id: string; examples: string[] };
export type ResolutionBucket = string | "OWNER" | "UNRESOLVED";
export type ResolutionResult = { assignments: Record<string, ResolutionBucket>; clusters: Record<string, { cluster_id: string; label: string }> };
export type ResolutionRunOptions = { owner_account_id: string; owner?: { entity_id?: string; label: string } };

const ownerEntityId = (options: ResolutionRunOptions) => options.owner?.entity_id ?? `owner:${options.owner_account_id}`;
const entityFor = (id: string, owner: string, handle: string, label: string): Entity => ({
  entity_id: id, owner_account_id: owner, entity_revision_id: `${id}:r1`, handle, labels: [label],
});

/** Incrementally resolves a deterministic mention sequence through an injected model edge. */
export const runResolution = async (mentions: readonly ResolutionMention[], port: ModelPort, options: ResolutionRunOptions): Promise<ResolutionResult> => {
  const ids = new Set<string>();
  for (const mention of mentions) {
    if (!mention.mention_id) throw new Error("mention_id must be non-empty");
    if (ids.has(mention.mention_id)) throw new Error(`duplicate mention_id: ${mention.mention_id}`);
    ids.add(mention.mention_id);
  }
  const ownerId = ownerEntityId(options);
  let table: EntityTable = {
    owner_account_id: options.owner_account_id,
    entities: [entityFor(ownerId, options.owner_account_id, "owner", options.owner?.label ?? "OWNER")],
    constraints: [],
  };
  const assignments: Record<string, ResolutionBucket> = {};
  const clusters: Record<string, { cluster_id: string; label: string }> = {};
  const ordered = [...mentions].sort((left, right) => compareStrings(left.session_id, right.session_id) || compareStrings(left.mention_id, right.mention_id));

  for (const mention of ordered) {
    const handle: LocalHandle = { handle: `local:${mention.mention_id}`, mention_ref: mention.mention_id, antecedent_handle: null, uncertainty: [] };
    const evidence = [`Mention name: ${mention.name}`, `Mention type: ${mention.type}`, ...mention.examples];
    const candidates = table.entities.map((entity) => entity.entity_id);
    const resolution = await invokeEntityStrategy(port, table, options.owner_account_id, handle, evidence, candidates);
    if (resolution.outcome === "same") {
      assignments[mention.mention_id] = resolution.entity_id === ownerId ? "OWNER" : resolution.entity_id;
      continue;
    }
    if (resolution.outcome === "abstain") {
      assignments[mention.mention_id] = "UNRESOLVED";
      continue;
    }
    const clusterId = `cluster:${mention.mention_id}`;
    table = { ...table, entities: [...table.entities, entityFor(clusterId, options.owner_account_id, handle.handle, mention.name)] };
    clusters[clusterId] = { cluster_id: clusterId, label: mention.name };
    assignments[mention.mention_id] = clusterId;
  }
  return { assignments, clusters };
};
