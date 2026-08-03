import { sha256CanonicalRedacted } from "../ledger";
import { policyPartitionLabel, type PolicyClass, type TreeInputSnapshot } from "./index";
import type { DependencyManifest, StructuralNode, StructuralTree } from "./tree";
import { restrictivePolicyJoin, validateRestrictiveJoin } from "./policy";

export { restrictivePolicyJoin, validateRestrictiveJoin } from "./policy";

export type RenderStatus = "ready" | "empty" | "failed";
export interface RenderNode {
  node_id: string;
  policy_partition_label: string;
  render_generation: string;
  summary_text: string | null;
  citations: readonly string[];
  model_version: string;
  rendered_from_digest: string;
  rendered_from_manifest: DependencyManifest;
  render_hash: string | null;
  effective_policy: PolicyClass;
  status: RenderStatus;
  failure: string | null;
  stale: boolean;
  source_language: string;
}
/** Narrow core-side port. The driver ModelPort structurally implements it, but core never imports drivers. */
export interface RenderModelPort {
  render(request: { strategy: string; version: string; input: unknown }): Promise<{ summary_text: string; citations: readonly string[] }>;
}
export interface RenderOptions { strategy: string; model_version: string; prompt_version: string; policy_version: string; schema_version: string; }
export type RenderCache = ReadonlyMap<string, RenderNode>;

const nodeClaims = (node: StructuralNode, input: TreeInputSnapshot) => node.member_claim_revision_ids.map((id) => input.claims.find((claim) => claim.claim_revision_id === id)).filter((claim): claim is NonNullable<typeof claim> => claim !== undefined);

/** Persists observed child render dependencies without changing anchor-derived structural identity. */
export const withChildRenderHashes = (tree: StructuralTree, renders: readonly RenderNode[]): StructuralTree => {
  const byNodeId = new Map(renders.map((render) => [render.node_id, render]));
  for (const node of tree.nodes) node.dependency_manifest = { ...node.dependency_manifest,
    child_render_hashes: node.child_node_ids.map((child) => byNodeId.get(child)?.render_hash ?? "missing-child-render").sort() };
  return tree;
};

export const renderStructuralTree = async (tree: StructuralTree, input: TreeInputSnapshot, model: RenderModelPort, options: RenderOptions, cache: RenderCache = new Map()): Promise<readonly RenderNode[]> => {
  const rendered = new Map<string, RenderNode>();
  const visit = async (node: StructuralNode): Promise<RenderNode> => {
    const existing = rendered.get(node.node_id);
    if (existing) return existing;
    const children = await Promise.all(node.child_node_ids.map((id) => visit(tree.nodes.find((item) => item.node_id === id)!)));
    const claims = nodeClaims(node, input);
    const effective = restrictivePolicyJoin(claims.map((claim) => claim.policy_class));
    // Persist the parent manifest before request construction; this is the structural
    // dependency record used for later parent invalidation, not a request-only copy.
    const nodeWithChildHashes = withChildRenderHashes({ ...tree, nodes: [node] }, children).nodes[0]!;
    const manifest = node.dependency_manifest;
    const rendered_from_digest = sha256CanonicalRedacted({ node_id: node.node_id, manifest, strategy: options.strategy, model_version: options.model_version, prompt_version: options.prompt_version, policy_version: options.policy_version, schema_version: options.schema_version });
    if (!validateRestrictiveJoin(effective, claims.map((claim) => claim.policy_class))) throw new Error(`restrictive policy join failed for ${node.node_id}`);
    const cached = cache.get(rendered_from_digest);
    if (cached) { rendered.set(node.node_id, cached); return cached; }
    const childStale = manifest.child_render_hashes.some((hash) => hash === "missing-child-render" || children.some((child) => child.render_hash === hash && (child.stale || child.status === "failed")));
    try {
      const response = await model.render({ strategy: options.strategy, version: options.model_version, input: { node: nodeWithChildHashes, claims, child_summaries: children.map((child) => child.summary_text) } });
      const status: RenderStatus = response.summary_text ? "ready" : "empty";
      const render_hash = sha256CanonicalRedacted({ rendered_from_digest, summary_text: response.summary_text, citations: [...response.citations].sort() });
      const result: RenderNode = { node_id: node.node_id, policy_partition_label: node.policy_partition_label,
        render_generation: `render-v1:${render_hash}`, summary_text: response.summary_text || null, citations: [...response.citations].sort(), model_version: options.model_version,
        rendered_from_digest, rendered_from_manifest: manifest, render_hash, effective_policy: effective, status, failure: null,
        stale: childStale, source_language: claims[0]?.source_language ?? "und" };
      rendered.set(node.node_id, result); return result;
    } catch (error) {
      const result: RenderNode = { node_id: node.node_id, policy_partition_label: node.policy_partition_label, render_generation: `render-v1:failed:${rendered_from_digest}`,
        summary_text: null, citations: [], model_version: options.model_version, rendered_from_digest, rendered_from_manifest: manifest, render_hash: null,
        effective_policy: effective, status: "failed", failure: error instanceof Error ? error.message : String(error), stale: true, source_language: claims[0]?.source_language ?? "und" };
      rendered.set(node.node_id, result); return result;
    }
  };
  await Promise.all(tree.nodes.map(visit));
  return [...rendered.values()].sort((left, right) => left.node_id.localeCompare(right.node_id));
};
