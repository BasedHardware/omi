import { useEffect, useMemo, useState } from "react";
import { ChevronDown, Search, X, RotateCw } from "lucide-react";
import {
  useKnowledgeGraphStore,
  type KnowledgeNode,
  type KnowledgeEdge,
  type NodeType,
} from "../../stores/knowledgeGraphStore";
import { useMemoryStore } from "../../stores/memoryStore";
import { MemoryCard } from "./MemoryCard";

type EntityGroup = {
  key: NodeType;
  label: string;
  nodes: KnowledgeNode[];
};

type Summary = {
  node: KnowledgeNode;
  lines: string[];
  memoryCount: number;
};

const GROUP_ORDER: { key: NodeType; label: string }[] = [
  { key: "person", label: "People" },
  { key: "place", label: "Places" },
  { key: "organization", label: "Organizations" },
  { key: "thing", label: "Things" },
  { key: "concept", label: "Concepts" },
];

const MAX_RELATIONSHIPS = 4;

function summarizeNode(
  node: KnowledgeNode,
  edges: KnowledgeEdge[],
  nodeById: Map<string, KnowledgeNode>,
): Summary {
  const lines: string[] = [];
  const seen = new Set<string>();
  const memoryIds = new Set<string>(node.memory_ids ?? []);

  for (const edge of edges) {
    if (edge.source_id === node.id) {
      const target = nodeById.get(edge.target_id);
      if (!target) continue;
      const key = `${edge.label}→${target.label}`;
      if (seen.has(key)) continue;
      seen.add(key);
      lines.push(`${edge.label} ${target.label}`);
      (edge.memory_ids ?? []).forEach((id) => memoryIds.add(id));
    } else if (edge.target_id === node.id) {
      const source = nodeById.get(edge.source_id);
      if (!source) continue;
      const key = `${source.label}→${edge.label}`;
      if (seen.has(key)) continue;
      seen.add(key);
      lines.push(`${source.label} ${edge.label}`);
      (edge.memory_ids ?? []).forEach((id) => memoryIds.add(id));
    }
  }

  return {
    node,
    lines: lines.slice(0, MAX_RELATIONSHIPS),
    memoryCount: memoryIds.size,
  };
}

export function PeopleAndThings() {
  const nodes = useKnowledgeGraphStore((s) => s.nodes);
  const edges = useKnowledgeGraphStore((s) => s.edges);
  const isLoading = useKnowledgeGraphStore((s) => s.isLoading);
  const isRebuilding = useKnowledgeGraphStore((s) => s.isRebuilding);
  const hasLoaded = useKnowledgeGraphStore((s) => s.hasLoaded);
  const loadGraph = useKnowledgeGraphStore((s) => s.loadGraph);
  const rebuildGraph = useKnowledgeGraphStore((s) => s.rebuildGraph);

  const memories = useMemoryStore((s) => s.memories);
  const deleteMemory = useMemoryStore((s) => s.deleteMemory);

  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    if (!hasLoaded) loadGraph();
  }, [hasLoaded, loadGraph]);

  const nodeById = useMemo(() => {
    const m = new Map<string, KnowledgeNode>();
    for (const n of nodes) m.set(n.id, n);
    return m;
  }, [nodes]);

  const memoryById = useMemo(() => {
    const m = new Map<string, (typeof memories)[number]>();
    for (const mem of memories) m.set(mem.id, mem);
    return m;
  }, [memories]);

  const summaries = useMemo(() => {
    const map = new Map<string, Summary>();
    for (const node of nodes) {
      map.set(node.id, summarizeNode(node, edges, nodeById));
    }
    return map;
  }, [nodes, edges, nodeById]);

  const groups: EntityGroup[] = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filteredNodes = q
      ? nodes.filter((n) => {
          if (n.label.toLowerCase().includes(q)) return true;
          const summary = summaries.get(n.id);
          return summary?.lines.some((l) => l.toLowerCase().includes(q)) ?? false;
        })
      : nodes;

    return GROUP_ORDER.map(({ key, label }) => ({
      key,
      label,
      nodes: filteredNodes
        .filter((n) => n.node_type === key)
        .sort((a, b) => {
          const am = summaries.get(a.id)?.memoryCount ?? 0;
          const bm = summaries.get(b.id)?.memoryCount ?? 0;
          if (am !== bm) return bm - am;
          return a.label.localeCompare(b.label);
        }),
    })).filter((g) => g.nodes.length > 0);
  }, [nodes, summaries, query]);

  if (!hasLoaded && isLoading) {
    return (
      <div className="people-things">
        <div className="page-empty">Loading your knowledge map…</div>
      </div>
    );
  }

  if (isRebuilding && nodes.length === 0) {
    return (
      <div className="people-things">
        <div className="page-empty">
          <RotateCw className="kg-empty-spinner" />
          <div className="kg-empty-title">Building your knowledge map…</div>
          <div className="kg-empty-sub">
            Extracting people, places, and things from your memories.
            This can take a minute or two.
          </div>
        </div>
      </div>
    );
  }

  if (hasLoaded && nodes.length === 0) {
    return (
      <div className="people-things">
        <div className="page-empty">
          <div className="kg-empty-title">Nothing here yet</div>
          <div className="kg-empty-sub">
            As memories accumulate, people and things you mention will appear here.
          </div>
          <button
            type="button"
            className="kg-rebuild-inline"
            onClick={() => rebuildGraph()}
            disabled={isRebuilding}
          >
            <RotateCw className="kg-rebuild-icon" />
            Rebuild from existing memories
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="people-things">
      <div className="people-things-toolbar">
        <div className="memories-search">
          <Search className="memories-search-icon" />
          <input
            className="memories-search-input"
            placeholder="Search people, places, things"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          {query.length > 0 && (
            <button
              type="button"
              className="memories-search-clear"
              onClick={() => setQuery("")}
              aria-label="Clear search"
            >
              <X className="memories-search-clear-icon" />
            </button>
          )}
        </div>
        <button
          type="button"
          className="kg-rebuild-button"
          onClick={() => rebuildGraph()}
          title="Rebuild from existing memories"
          disabled={isRebuilding}
        >
          <RotateCw
            className={isRebuilding ? "kg-rebuild-icon kg-rebuild-spinning" : "kg-rebuild-icon"}
          />
        </button>
      </div>

      {isRebuilding && nodes.length > 0 && (
        <div className="kg-rebuild-banner">
          <RotateCw className="kg-rebuild-icon kg-rebuild-spinning" />
          <span>Rebuilding knowledge map. Existing entries stay visible until it finishes.</span>
        </div>
      )}

      {groups.length === 0 ? (
        <div className="page-empty">No matches.</div>
      ) : (
        <div className="people-things-groups">
          {groups.map((group) => (
            <section key={group.key} className="people-things-group">
              <div className="people-things-group-header">
                <span className="people-things-group-label">{group.label}</span>
                <span className="people-things-group-count">{group.nodes.length}</span>
              </div>
              <div className="people-things-rows">
                {group.nodes.map((node) => {
                  const summary = summaries.get(node.id);
                  const lines = summary?.lines ?? [];
                  const memoryCount = summary?.memoryCount ?? 0;
                  const isOpen = expanded === node.id;
                  const relatedMemories = isOpen
                    ? Array.from(
                        new Set([
                          ...(node.memory_ids ?? []),
                          ...edges
                            .filter(
                              (e) => e.source_id === node.id || e.target_id === node.id,
                            )
                            .flatMap((e) => e.memory_ids ?? []),
                        ]),
                      )
                        .map((id) => memoryById.get(id))
                        .filter((m): m is NonNullable<typeof m> => m !== undefined)
                    : [];

                  return (
                    <div key={node.id} className="entity-row-wrap">
                      <button
                        type="button"
                        className={
                          isOpen ? "entity-row entity-row-open" : "entity-row"
                        }
                        onClick={() => setExpanded(isOpen ? null : node.id)}
                        aria-expanded={isOpen}
                      >
                        <div className="entity-row-name">{node.label}</div>
                        <div className="entity-row-summary">
                          {lines.length > 0 ? lines.join(" · ") : (
                            <span className="entity-row-summary-empty">
                              no relationships yet
                            </span>
                          )}
                        </div>
                        <div className="entity-row-meta">
                          <span className="entity-row-count">
                            {memoryCount} {memoryCount === 1 ? "memory" : "memories"}
                          </span>
                          <ChevronDown
                            className={
                              isOpen
                                ? "entity-row-chevron entity-row-chevron-open"
                                : "entity-row-chevron"
                            }
                          />
                        </div>
                      </button>
                      {isOpen && (
                        <div className="entity-row-body">
                          {relatedMemories.length === 0 ? (
                            <div className="entity-row-empty">
                              No memories linked to this entity are loaded.
                            </div>
                          ) : (
                            <div className="entity-row-memories">
                              {relatedMemories.map((memory) => (
                                <MemoryCard
                                  key={memory.id}
                                  memory={memory}
                                  onDelete={() => deleteMemory(memory.id)}
                                />
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
