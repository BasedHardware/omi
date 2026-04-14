import { useEffect } from "react";
import { useMemoryStore } from "../../stores/memoryStore";
import type { Memory } from "../../stores/memoryStore";

function formatDate(dateStr: string): string {
  try {
    const date = new Date(dateStr);
    return date.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return "";
  }
}

function MemoryCard({ memory, onDelete }: { memory: Memory; onDelete: () => void }) {
  const title = memory.structured?.title || "Memory";
  const category = memory.structured?.category || memory.category;
  const content = memory.content || "";

  return (
    <div className="memory-card">
      <div className="memory-card-header">
        <span className="memory-card-title">{title}</span>
        {category && <span className="memory-card-category">{category}</span>}
      </div>
      <p className="memory-card-content">{content}</p>
      <div className="memory-card-actions">
        <span className="memory-card-date">{formatDate(memory.created_at)}</span>
        <button className="memory-delete-button" onClick={onDelete}>
          Delete
        </button>
      </div>
    </div>
  );
}

export function MemoriesPage() {
  const { memories, isLoading, loadMemories, deleteMemory } = useMemoryStore();

  useEffect(() => {
    loadMemories();
  }, [loadMemories]);

  return (
    <div className="memories-page">
      <div className="page-header">
        <h2>Memories</h2>
      </div>
      <div className="memories-content">
        {isLoading && memories.length === 0 && (
          <div className="page-empty">Loading memories...</div>
        )}
        {!isLoading && memories.length === 0 && (
          <div className="page-empty">
            No memories yet. Your AI-extracted memories will appear here.
          </div>
        )}
        <div className="memories-grid">
          {memories.map((memory) => (
            <MemoryCard
              key={memory.id}
              memory={memory}
              onDelete={() => deleteMemory(memory.id)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
