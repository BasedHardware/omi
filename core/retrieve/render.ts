import { compareStrings } from "../order";
import { sha256CanonicalRedacted } from "../ledger";
import { policyPartitionLabel, type PolicyClass, type TreeInputSnapshot } from "./index";
import type { DependencyManifest, StructuralNode, StructuralTree } from "./tree";
import { restrictivePolicyJoin, validateRestrictiveJoin } from "./policy";

export { restrictivePolicyJoin, validateRestrictiveJoin } from "./policy";

export type RenderStatus = "ready" | "empty" | "failed";
export interface RenderNode {
  owner_account_id: string;
  graph_generation: string;
  reader_projection_digest: string | null;
  projection_authorization_digest: string | null;
  projected_content_digest: string;
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
const deepFreeze = <Value>(value: Value): Value => {
  if (value !== null && typeof value === "object" && !Object.isFrozen(value)) {
    for (const nested of Object.values(value)) deepFreeze(nested);
    Object.freeze(value);
  }
  return value;
};
const immutableClone = <Value>(value: Value): Value => deepFreeze(structuredClone(value));

/** Persists observed child render dependencies without changing anchor-derived structural identity. */
export const withChildRenderHashes = (tree: StructuralTree, renders: readonly RenderNode[]): StructuralTree => {
  const byNodeId = new Map(renders.map((render) => [render.node_id, render]));
  for (const node of tree.nodes) node.dependency_manifest = { ...node.dependency_manifest,
    child_render_hashes: node.child_node_ids.map((child) => byNodeId.get(child)?.render_hash ?? "missing-child-render").sort() };
  return tree;
};

export const renderStructuralTree = async (tree: StructuralTree, input: TreeInputSnapshot, model: RenderModelPort, options: RenderOptions, cache: RenderCache = new Map()): Promise<readonly RenderNode[]> => {
  const suppliedTree = tree;
  tree = structuredClone(tree);
  input = immutableClone(input);
  options = immutableClone(options);
  cache = new Map(cache);
  if (tree.input_generation !== input.graph_generation) throw new Error("render tree/input generation mismatch");
  const rendered = new Map<string, RenderNode>();
  const visit = async (node: StructuralNode): Promise<RenderNode> => {
    if (node.graph_generation !== input.graph_generation) throw new Error(`render node/input generation mismatch for ${node.node_id}`);
    const existing = rendered.get(node.node_id);
    if (existing) return existing;
    const children = await Promise.all(node.child_node_ids.map((id) => visit(tree.nodes.find((item) => item.node_id === id)!)));
    const claims = nodeClaims(node, input);
    const effective = restrictivePolicyJoin(claims.map((claim) => claim.policy_class));
    // Persist the parent manifest before request construction; this is the structural
    // dependency record used for later parent invalidation, not a request-only copy.
    const nodeWithChildHashes = withChildRenderHashes({ ...tree, nodes: [node] }, children).nodes[0]!;
    const manifest = immutableClone(node.dependency_manifest);
    const rendered_from_digest = sha256CanonicalRedacted({ owner_account_id: input.owner_account_id, graph_generation: input.graph_generation,
      reader_projection_digest: input.reader_projection_digest, projection_authorization_digest: input.projection_authorization_digest,
      projected_content_digest: input.projected_content_digest,
      node_id: node.node_id, manifest, strategy: options.strategy, model_version: options.model_version, prompt_version: options.prompt_version, policy_version: options.policy_version, schema_version: options.schema_version });
    if (!validateRestrictiveJoin(effective, claims.map((claim) => claim.policy_class))) throw new Error(`restrictive policy join failed for ${node.node_id}`);
    const cached = cache.get(rendered_from_digest);
    if (cached && cached.owner_account_id === input.owner_account_id && cached.graph_generation === input.graph_generation
      && cached.reader_projection_digest === input.reader_projection_digest && cached.projection_authorization_digest === input.projection_authorization_digest
      && cached.projected_content_digest === input.projected_content_digest
      && cached.node_id === node.node_id && cached.rendered_from_digest === rendered_from_digest) { rendered.set(node.node_id, cached); return cached; }
    const childStale = manifest.child_render_hashes.some((hash) => hash === "missing-child-render" || children.some((child) => child.render_hash === hash && (child.stale || child.status === "failed")));
    try {
      const request = immutableClone({ strategy: options.strategy, version: options.model_version,
        input: { node: { ...nodeWithChildHashes, dependency_manifest: manifest }, claims, child_summaries: children.map((child) => child.summary_text) } });
      const response = await model.render(request);
      const summary_text = String(response.summary_text);
      const citations = Object.freeze([...response.citations].map(String).sort());
      const status: RenderStatus = summary_text ? "ready" : "empty";
      const render_hash = sha256CanonicalRedacted({ owner_account_id: input.owner_account_id, graph_generation: input.graph_generation,
        reader_projection_digest: input.reader_projection_digest, projection_authorization_digest: input.projection_authorization_digest,
        projected_content_digest: input.projected_content_digest,
        node_id: node.node_id, rendered_from_digest, rendered_from_manifest: manifest, summary_text: response.summary_text,
        citations, effective_policy: effective });
      const result: RenderNode = deepFreeze({ owner_account_id: input.owner_account_id, graph_generation: input.graph_generation,
        reader_projection_digest: input.reader_projection_digest, projection_authorization_digest: input.projection_authorization_digest,
        projected_content_digest: input.projected_content_digest,
        node_id: node.node_id, policy_partition_label: node.policy_partition_label,
        render_generation: `render-v1:${render_hash}`, summary_text: summary_text || null, citations, model_version: options.model_version,
        rendered_from_digest, rendered_from_manifest: manifest, render_hash, effective_policy: effective, status, failure: null,
        stale: childStale, source_language: claims[0]?.source_language ?? "und" } satisfies RenderNode);
      rendered.set(node.node_id, result); return result;
    } catch (error) {
      const result: RenderNode = deepFreeze({ owner_account_id: input.owner_account_id, graph_generation: input.graph_generation,
        reader_projection_digest: input.reader_projection_digest, projection_authorization_digest: input.projection_authorization_digest,
        projected_content_digest: input.projected_content_digest,
        node_id: node.node_id, policy_partition_label: node.policy_partition_label, render_generation: `render-v1:failed:${rendered_from_digest}`,
        summary_text: null, citations: [], model_version: options.model_version, rendered_from_digest, rendered_from_manifest: manifest, render_hash: null,
        effective_policy: effective, status: "failed", failure: error instanceof Error ? error.message : String(error), stale: true, source_language: claims[0]?.source_language ?? "und" } satisfies RenderNode);
      rendered.set(node.node_id, result); return result;
    }
  };
  await Promise.all(tree.nodes.map(visit));
  for (const suppliedNode of suppliedTree.nodes) {
    const renderedNode = tree.nodes.find((node) => node.node_id === suppliedNode.node_id);
    if (renderedNode) suppliedNode.dependency_manifest = structuredClone(renderedNode.dependency_manifest);
  }
  return [...rendered.values()].sort((left, right) => compareStrings(left.node_id, right.node_id));
};
