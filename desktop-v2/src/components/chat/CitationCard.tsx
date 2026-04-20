/**
 * CitationCard — compact card displaying a single citation source attached
 * to an assistant message. Clicking logs the target (or invokes the
 * provided handler) so the consumer can route the user to the underlying
 * conversation, memory, note, or web URL.
 */

import {
  BookOpen,
  ChevronRight,
  FileText,
  Globe,
  MessageSquare,
  Sparkles,
} from "lucide-react";
import type { ComponentType, SVGProps } from "react";
import type { Citation } from "@/stores/chatStore";
import { cn } from "@/lib/utils";

type IconComponent = ComponentType<SVGProps<SVGSVGElement>>;

const ICON_BY_TYPE: Record<Citation["sourceType"], IconComponent> = {
  conversation: MessageSquare,
  memory: Sparkles,
  note: FileText,
  web: Globe,
};

const LABEL_BY_TYPE: Record<Citation["sourceType"], string> = {
  conversation: "Conversation",
  memory: "Memory",
  note: "Note",
  web: "Web",
};

export interface CitationCardProps {
  citation: Citation;
  onSelect?: (citation: Citation) => void;
  className?: string;
}

export function CitationCard({ citation, onSelect, className }: CitationCardProps) {
  const Icon: IconComponent = ICON_BY_TYPE[citation.sourceType] ?? BookOpen;

  const handleClick = () => {
    if (onSelect) {
      onSelect(citation);
      return;
    }
    // Graceful default when no target is wired up yet.
    console.log("[CitationCard] clicked", {
      id: citation.id,
      type: citation.sourceType,
      target: citation.target,
    });
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      className={cn("citation-card", className)}
      aria-label={`Open citation: ${citation.title}`}
    >
      <span className="citation-card__icon" aria-hidden="true">
        <Icon className="size-3.5" />
      </span>
      <span className="citation-card__body">
        <span className="citation-card__title">{citation.title}</span>
        <span className="citation-card__meta">
          <span className="citation-card__source">
            {LABEL_BY_TYPE[citation.sourceType] ?? "Source"}
          </span>
          {citation.preview && (
            <>
              <span className="citation-card__dot" aria-hidden="true">
                ·
              </span>
              <span className="citation-card__preview">{citation.preview}</span>
            </>
          )}
        </span>
      </span>
      <ChevronRight className="citation-card__chevron size-3" aria-hidden="true" />
    </button>
  );
}
