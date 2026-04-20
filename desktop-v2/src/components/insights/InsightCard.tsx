import { useState, type ComponentType } from "react";
import { BarChart3, EyeOff, Monitor, Trash2 } from "lucide-react";
import type { StoredInsight } from "@/stores/insightStore";
import { formatRelative } from "./formatRelative";

interface Props {
  insight: StoredInsight;
  categoryIcon: ComponentType<{ size?: number; className?: string }>;
  onOpen: () => void;
  onDismiss: () => void;
  onDelete: () => void;
}

export function InsightCard({
  insight,
  categoryIcon: Icon,
  onOpen,
  onDismiss,
  onDelete,
}: Props) {
  const [hovering, setHovering] = useState(false);

  const confidencePct = Math.round(insight.confidence * 100);

  return (
    <button
      type="button"
      className={[
        "insight-card",
        insight.isDismissed ? "insight-card-dismissed" : "",
        hovering ? "insight-card-hover" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      onClick={onOpen}
      onMouseEnter={() => setHovering(true)}
      onMouseLeave={() => setHovering(false)}
    >
      <span className="insight-card-icon">
        <Icon size={16} />
      </span>

      <div className="insight-card-body">
        <div className="insight-card-headline">
          {!insight.isRead && <span className="insight-card-unread-dot" />}
          <span className="insight-card-text">{insight.content}</span>
        </div>
        <div className="insight-card-meta">
          <span className="insight-card-meta-item">
            <Monitor size={11} />
            <span>{insight.sourceApp}</span>
          </span>
          <span className="insight-card-meta-item">
            <BarChart3 size={11} />
            <span>{confidencePct}%</span>
          </span>
          <span className="insight-card-meta-spacer" />
          <span className="insight-card-meta-date">
            {formatRelative(insight.createdAt)}
          </span>
        </div>
      </div>

      {hovering && (
        <div
          className="insight-card-actions"
          onClick={(e) => e.stopPropagation()}
        >
          {!insight.isDismissed && (
            <button
              type="button"
              className="insight-card-action"
              onClick={onDismiss}
              aria-label="Dismiss"
              title="Dismiss"
            >
              <EyeOff size={14} />
            </button>
          )}
          <button
            type="button"
            className="insight-card-action"
            onClick={onDelete}
            aria-label="Delete"
            title="Delete"
          >
            <Trash2 size={14} />
          </button>
        </div>
      )}
    </button>
  );
}
