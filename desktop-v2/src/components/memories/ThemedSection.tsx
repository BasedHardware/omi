import { useState } from "react";
import { ChevronDown } from "lucide-react";
import type { Memory } from "../../stores/memoryStore";
import type { ThemeDef } from "./themes";
import { MemoryCard } from "./MemoryCard";

type Props = {
  theme: ThemeDef;
  memories: Memory[];
  onDelete: (id: string) => void;
  defaultOpen?: boolean;
};

export function ThemedSection({ theme, memories, onDelete, defaultOpen = false }: Props) {
  const [open, setOpen] = useState(defaultOpen);

  if (memories.length === 0) return null;

  const preview = memories[0]?.content ?? "";
  const Icon = theme.icon;

  return (
    <div className="themed-section">
      <button
        type="button"
        className="themed-section-trigger"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <div className="themed-section-head">
          <Icon className="themed-section-icon" />
          <span className="themed-section-label">{theme.label}</span>
          <span className="themed-section-count">{memories.length}</span>
        </div>
        <div className="themed-section-right">
          {!open && (
            <span className="themed-section-preview">{preview}</span>
          )}
          <ChevronDown
            className={
              open
                ? "themed-section-chevron themed-section-chevron-open"
                : "themed-section-chevron"
            }
          />
        </div>
      </button>
      {open && (
        <div className="themed-section-body">
          {memories.map((memory) => (
            <MemoryCard
              key={memory.id}
              memory={memory}
              onDelete={() => onDelete(memory.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
