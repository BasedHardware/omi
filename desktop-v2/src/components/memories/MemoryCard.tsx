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

export function MemoryCard({ memory, onDelete }: { memory: Memory; onDelete: () => void }) {
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
