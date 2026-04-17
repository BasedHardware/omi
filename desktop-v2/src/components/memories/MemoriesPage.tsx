import { useEffect, useMemo, useState } from "react";
import { Search, X } from "lucide-react";
import { useMemoryStore } from "../../stores/memoryStore";
import { MemoryCard } from "./MemoryCard";
import { IdentityHeader } from "./IdentityHeader";
import { ThemedSection } from "./ThemedSection";
import { RecentStrip } from "./RecentStrip";
import { PeopleAndThings } from "./PeopleAndThings";
import { classifyByTheme } from "./classifyByTheme";
import { THEMES } from "./themes";

type Tab = "themes" | "people";

export function MemoriesPage() {
  const memories = useMemoryStore((s) => s.memories);
  const isLoading = useMemoryStore((s) => s.isLoading);
  const query = useMemoryStore((s) => s.query);
  const categoryFilter = useMemoryStore((s) => s.categoryFilter);
  const loadMemories = useMemoryStore((s) => s.loadMemories);
  const deleteMemory = useMemoryStore((s) => s.deleteMemory);
  const setQuery = useMemoryStore((s) => s.setQuery);
  const filteredMemoriesFn = useMemoryStore((s) => s.filteredMemories);

  const [tab, setTab] = useState<Tab>("themes");

  useEffect(() => {
    loadMemories();
  }, [loadMemories]);

  const filtered = filteredMemoriesFn();
  const isBrowsing = query.trim() === "" && categoryFilter === null;

  const buckets = useMemo(
    () => (isBrowsing ? classifyByTheme(memories) : null),
    [isBrowsing, memories],
  );

  const orderedThemes = useMemo(() => {
    if (!buckets) return [];
    return THEMES
      .map((t) => ({ theme: t, items: buckets[t.key] }))
      .filter((s) => s.items.length > 0)
      .sort((a, b) => b.items.length - a.items.length);
  }, [buckets]);

  return (
    <div className="memories-page">
      <div className="memories-content">
        {isLoading && memories.length === 0 && (
          <div className="page-empty">Loading memories...</div>
        )}
        {!isLoading && memories.length === 0 && (
          <div className="page-empty">
            No memories yet. Your AI-extracted memories will appear here.
          </div>
        )}
        {memories.length > 0 && (
          <>
            <IdentityHeader />
            <div className="memories-tabs" role="tablist">
              <button
                type="button"
                role="tab"
                aria-selected={tab === "themes"}
                className={
                  tab === "themes" ? "memories-tab memories-tab-active" : "memories-tab"
                }
                onClick={() => setTab("themes")}
              >
                Themes
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={tab === "people"}
                className={
                  tab === "people" ? "memories-tab memories-tab-active" : "memories-tab"
                }
                onClick={() => setTab("people")}
              >
                People &amp; Things
              </button>
            </div>
            {tab === "themes" ? (
              <>
                <div className="memories-search">
                  <Search className="memories-search-icon" />
                  <input
                    className="memories-search-input"
                    placeholder="Search memories"
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
                {isBrowsing ? (
                  <>
                    <div className="themed-sections">
                      {orderedThemes.map(({ theme, items }, i) => (
                        <ThemedSection
                          key={theme.key}
                          theme={theme}
                          memories={items}
                          onDelete={deleteMemory}
                          defaultOpen={i === 0}
                        />
                      ))}
                    </div>
                    <RecentStrip memories={memories} onDelete={deleteMemory} />
                  </>
                ) : (
                  <>
                    {filtered.length === 0 ? (
                      <div className="page-empty">No memories match your filters.</div>
                    ) : (
                      <div className="memories-grid">
                        {filtered.map((memory) => (
                          <MemoryCard
                            key={memory.id}
                            memory={memory}
                            onDelete={() => deleteMemory(memory.id)}
                          />
                        ))}
                      </div>
                    )}
                  </>
                )}
              </>
            ) : (
              <PeopleAndThings />
            )}
          </>
        )}
      </div>
    </div>
  );
}
