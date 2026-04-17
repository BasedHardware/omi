import { useMemo } from "react";
import { useMemoryStore } from "../../stores/memoryStore";

const MS_PER_DAY = 86_400_000;

function countThisWeek(memories: { created_at: string }[]): number {
  const cutoff = Date.now() - 7 * MS_PER_DAY;
  let n = 0;
  for (const m of memories) {
    const t = Date.parse(m.created_at);
    if (!Number.isNaN(t) && t >= cutoff) n += 1;
  }
  return n;
}

export function IdentityHeader() {
  const memories = useMemoryStore((s) => s.memories);
  const categoryFilter = useMemoryStore((s) => s.categoryFilter);
  const setCategoryFilter = useMemoryStore((s) => s.setCategoryFilter);

  const { total, thisWeek, pills } = useMemo(() => {
    const counts = new Map<string, number>();
    for (const m of memories) {
      const c = m.structured?.category ?? m.category ?? "other";
      counts.set(c, (counts.get(c) ?? 0) + 1);
    }
    const sorted = [...counts.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 4);
    return {
      total: memories.length,
      thisWeek: countThisWeek(memories),
      pills: sorted,
    };
  }, [memories]);

  if (total === 0) return null;

  return (
    <div className="identity-header">
      <div className="identity-header-title">
        What I know about <span className="font-serif italic">you</span>
      </div>
      <div className="identity-header-meta">
        <span>{total} memories</span>
        {thisWeek > 0 && (
          <>
            <span className="identity-header-dot">·</span>
            <span>{thisWeek} this week</span>
          </>
        )}
      </div>
      {pills.length > 0 && (
        <div className="identity-header-pills">
          {pills.map(([cat, count]) => {
            const active = categoryFilter === cat;
            return (
              <button
                key={cat}
                type="button"
                className={
                  active ? "identity-pill identity-pill-active" : "identity-pill"
                }
                onClick={() => setCategoryFilter(active ? null : cat)}
              >
                <span className="identity-pill-label">{cat}</span>
                <span className="identity-pill-count">{count}</span>
              </button>
            );
          })}
          {categoryFilter !== null && (
            <button
              type="button"
              className="identity-pill-clear"
              onClick={() => setCategoryFilter(null)}
            >
              Clear
            </button>
          )}
        </div>
      )}
    </div>
  );
}
