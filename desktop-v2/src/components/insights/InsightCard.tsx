import { type ComponentType } from "react";
import { EyeOff, Trash2 } from "lucide-react";
import type { StoredInsight } from "@/stores/insightStore";
import { formatRelative } from "./formatRelative";

interface Props {
  insight: StoredInsight;
  categoryIcon: ComponentType<{ size?: number; className?: string }>;
  onOpen: () => void;
  onDismiss: () => void;
  onDelete: () => void;
}

/**
 * Card-style insight renderer — same shape as MemoryCard so the Insights
 * page feels like a sibling of the Memories page.
 */
export function InsightCard({
  insight,
  categoryIcon: Icon,
  onOpen,
  onDismiss,
  onDelete,
}: Props) {
  const stop =
    (fn: () => void) =>
    (e: React.MouseEvent<HTMLButtonElement>) => {
      e.stopPropagation();
      fn();
    };

  return (
    <button
      type="button"
      className={[
        "memory-card",
        "insight-card-surface",
        insight.isDismissed ? "insight-card-dismissed" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      onClick={onOpen}
    >
      <div className="memory-card-header">
        <span className="memory-card-title">
          {!insight.isRead && <span className="insight-card-unread-dot" />}
          <Icon size={13} className="insight-card-title-icon" />
          <span className="insight-card-title-text">
            {insight.headline || insight.sourceApp}
          </span>
        </span>
      </div>
      <p className="memory-card-content">{insight.content}</p>
      <div className="memory-card-actions">
        <span className="memory-card-date">
          {formatRelative(insight.createdAt)}
        </span>
        <div className="insight-card-hover-actions">
          {!insight.isDismissed && (
            <button
              type="button"
              className="memory-delete-button"
              onClick={stop(onDismiss)}
              aria-label="Dismiss"
              title="Dismiss"
            >
              <EyeOff size={13} />
            </button>
          )}
          <button
            type="button"
            className="memory-delete-button"
            onClick={stop(onDelete)}
            aria-label="Delete"
            title="Delete"
          >
            <Trash2 size={13} />
          </button>
        </div>
      </div>
    </button>
  );
}
