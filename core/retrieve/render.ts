import { compareStrings } from "../order";
import { sha256CanonicalRedacted } from "../ledger";
import { policyPartitionLabel, type PolicyClass, type TreeInputSnapshot } from "./index";
import type { DependencyManifest, StructuralNode, StructuralTree } from "./tree";
import { restrictivePolicyJoin, validateRestrictiveJoin } from "./policy";
import { sha256CanonicalContent } from "./content-digest";
import { deepFreezePlainJson, normalizePlainJson } from "./plain-json";

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
const immutableClone = <Value>(value: Value): Value => deepFreezePlainJson(normalizePlainJson(value));
const samePolicy = (left: PolicyClass, right: PolicyClass): boolean =>
  left.subject_class === right.subject_class && left.sensitivity === right.sensitivity && left.capture_class === right.capture_class;
const sameContent = (left: unknown, right: unknown): boolean => sha256CanonicalContent(left) === sha256CanonicalContent(right);
const renderHash = (render: Pick<RenderNode,
  "owner_account_id" | "graph_generation" | "reader_projection_digest" | "projection_authorization_digest"
  | "projected_content_digest" | "node_id" | "rendered_from_digest" | "rendered_from_manifest"
  | "summary_text" | "citations" | "effective_policy">): string => sha256CanonicalRedacted({
  owner_account_id: render.owner_account_id,
  graph_generation: render.graph_generation,
  reader_projection_digest: render.reader_projection_digest,
  projection_authorization_digest: render.projection_authorization_digest,
  projected_content_digest: render.projected_content_digest,
  node_id: render.node_id,
  rendered_from_digest: render.rendered_from_digest,
  rendered_from_manifest: render.rendered_from_manifest,
  summary_text: render.summary_text,
  citations: [...render.citations].sort(),
  effective_policy: render.effective_policy,
});

const validatedCacheHit = (
  candidate: RenderNode | undefined,
  expected: {
    input: TreeInputSnapshot;
    node: StructuralNode;
    manifest: DependencyManifest;
    rendered_from_digest: string;
    effective_policy: PolicyClass;
    child_stale: boolean;
    model_version: string;
    source_language: string;
  },
): RenderNode | null => {
  if (!candidate) return null;
  try {
    const cached = normalizePlainJson(candidate);
    const citations = [...cached.citations];
    const canonicalCitations = [...new Set(citations)].sort();
    if (cached.owner_account_id !== expected.input.owner_account_id
      || cached.graph_generation !== expected.input.graph_generation
      || cached.reader_projection_digest !== expected.input.reader_projection_digest
      || cached.projection_authorization_digest !== expected.input.projection_authorization_digest
      || cached.projected_content_digest !== expected.input.projected_content_digest
      || cached.node_id !== expected.node.node_id
      || cached.rendered_from_digest !== expected.rendered_from_digest
      || cached.policy_partition_label !== expected.node.policy_partition_label
      || cached.model_version !== expected.model_version
      || cached.source_language !== expected.source_language
      || cached.stale !== expected.child_stale
      || cached.failure !== null
      || (cached.status !== "ready" && cached.status !== "empty")
      || (cached.status === "ready" ? typeof cached.summary_text !== "string" || cached.summary_text.length === 0 : cached.summary_text !== null)
      || cached.render_hash === null
      || cached.render_generation !== `render-v1:${cached.render_hash}`
      || !sameContent(cached.rendered_from_manifest, expected.manifest)
      || !samePolicy(cached.effective_policy, expected.effective_policy)
      || citations.length !== canonicalCitations.length
      || citations.some((citation, index) => citation !== canonicalCitations[index])
      || cached.render_hash !== renderHash(cached)) return null;
    return deepFreezePlainJson(cached);
  } catch { return null; }
};

/** Persists observed child render dependencies without changing anchor-derived structural identity. */
export const withChildRenderHashes = (tree: StructuralTree, renders: readonly RenderNode[]): StructuralTree => {
  const byNodeId = new Map(renders.map((render) => [render.node_id, render]));
  for (const node of tree.nodes) node.dependency_manifest = { ...node.dependency_manifest,
    child_render_hashes: node.child_node_ids.map((child) => byNodeId.get(child)?.render_hash ?? "missing-child-render").sort() };
  return tree;
};

export const renderStructuralTree = async (tree: StructuralTree, input: TreeInputSnapshot, model: RenderModelPort, options: RenderOptions, cache: RenderCache = new Map()): Promise<readonly RenderNode[]> => {
  const suppliedTree = tree;
  tree = normalizePlainJson(tree);
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
    const childStale = manifest.child_render_hashes.some((hash) => hash === "missing-child-render" || children.some((child) => child.render_hash === hash && (child.stale || child.status === "failed")));
    const sourceLanguage = claims[0]?.source_language ?? "und";
    const cached = validatedCacheHit(cache.get(rendered_from_digest), {
      input, node, manifest, rendered_from_digest, effective_policy: effective, child_stale: childStale,
      model_version: options.model_version, source_language: sourceLanguage,
    });
    if (cached) { rendered.set(node.node_id, cached); return cached; }
    try {
      const request = immutableClone({ strategy: options.strategy, version: options.model_version,
        input: { node: { ...nodeWithChildHashes, dependency_manifest: manifest }, claims, child_summaries: children.map((child) => child.summary_text) } });
      const response = normalizePlainJson(await model.render(request));
      if (typeof response.summary_text !== "string" || !Array.isArray(response.citations)
        || response.citations.some((citation) => typeof citation !== "string")) throw new TypeError("render model returned invalid plain JSON");
      const summary_text = response.summary_text;
      const storedSummary = summary_text || null;
      const citations = Object.freeze([...new Set(response.citations)].sort());
      const status: RenderStatus = summary_text ? "ready" : "empty";
      const render_hash = renderHash({ owner_account_id: input.owner_account_id, graph_generation: input.graph_generation,
        reader_projection_digest: input.reader_projection_digest, projection_authorization_digest: input.projection_authorization_digest,
        projected_content_digest: input.projected_content_digest,
        node_id: node.node_id, rendered_from_digest, rendered_from_manifest: manifest, summary_text: storedSummary,
        citations, effective_policy: effective });
      const result: RenderNode = deepFreezePlainJson({ owner_account_id: input.owner_account_id, graph_generation: input.graph_generation,
        reader_projection_digest: input.reader_projection_digest, projection_authorization_digest: input.projection_authorization_digest,
        projected_content_digest: input.projected_content_digest,
        node_id: node.node_id, policy_partition_label: node.policy_partition_label,
        render_generation: `render-v1:${render_hash}`, summary_text: storedSummary, citations, model_version: options.model_version,
        rendered_from_digest, rendered_from_manifest: manifest, render_hash, effective_policy: effective, status, failure: null,
        stale: childStale, source_language: sourceLanguage } satisfies RenderNode);
      rendered.set(node.node_id, result); return result;
    } catch (error) {
      const result: RenderNode = deepFreezePlainJson({ owner_account_id: input.owner_account_id, graph_generation: input.graph_generation,
        reader_projection_digest: input.reader_projection_digest, projection_authorization_digest: input.projection_authorization_digest,
        projected_content_digest: input.projected_content_digest,
        node_id: node.node_id, policy_partition_label: node.policy_partition_label, render_generation: `render-v1:failed:${rendered_from_digest}`,
        summary_text: null, citations: [], model_version: options.model_version, rendered_from_digest, rendered_from_manifest: manifest, render_hash: null,
        effective_policy: effective, status: "failed", failure: error instanceof Error ? error.message : String(error), stale: true, source_language: sourceLanguage } satisfies RenderNode);
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
