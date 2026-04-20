/**
 * CitationList — horizontal strip of CitationCards rendered beneath an
 * assistant message. Scrolls horizontally on overflow so the message bubble
 * keeps its width constraint intact.
 */

import { Quote } from "lucide-react";
import type { Citation } from "@/stores/chatStore";
import { CitationCard } from "./CitationCard";

export interface CitationListProps {
  citations: Citation[];
  onSelect?: (citation: Citation) => void;
}

export function CitationList({ citations, onSelect }: CitationListProps) {
  if (!citations || citations.length === 0) return null;

  return (
    <div className="citation-list">
      <div className="citation-list__header">
        <Quote className="size-3" aria-hidden="true" />
        <span>Sources</span>
      </div>
      <div className="citation-list__strip" role="list">
        {citations.map((c) => (
          <div role="listitem" key={c.id} className="citation-list__item">
            <CitationCard citation={c} onSelect={onSelect} />
          </div>
        ))}
      </div>
    </div>
  );
}
