import type { Memory } from "../../stores/memoryStore";
import { MemoryCard } from "./MemoryCard";

type Props = {
  memories: Memory[];
  onDelete: (id: string) => void;
};

export function RecentStrip({ memories, onDelete }: Props) {
  if (memories.length === 0) return null;

  const recent = [...memories]
    .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
    .slice(0, 5);

  return (
    <div className="recent-strip">
      <div className="recent-strip-label">Recent</div>
      <div className="recent-strip-grid">
        {recent.map((memory) => (
          <MemoryCard
            key={memory.id}
            memory={memory}
            onDelete={() => onDelete(memory.id)}
          />
        ))}
      </div>
    </div>
  );
}
