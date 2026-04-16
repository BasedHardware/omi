import { useMemo } from "react";
import { cn } from "../../lib/utils";
import { MessageResponse } from "../ai-elements/message";
import { parseGenerativeContent } from "./parser";
import type { ContentSegment } from "./types";
import { RichList } from "./components/RichList";
import { Chart } from "./components/Chart";
import { Accordion } from "./components/Accordion";
import { Highlight } from "./components/Highlight";
import { TableView } from "./components/TableView";
import { StoryBriefing } from "./components/StoryBriefing";

interface Props {
  content: string;
  className?: string;
  isAnimating?: boolean;
}

export function GenerativeMarkdown({ content, className, isAnimating }: Props) {
  const segments = useMemo(() => parseGenerativeContent(content), [content]);

  return (
    <div className={cn("space-y-0", className)}>
      {segments.map((seg, i) => (
        <SegmentRenderer key={i} segment={seg} isAnimating={isAnimating} />
      ))}
    </div>
  );
}

function SegmentRenderer({
  segment,
  isAnimating,
}: {
  segment: ContentSegment;
  isAnimating?: boolean;
}) {
  switch (segment.kind) {
    case "markdown":
      return (
        <MessageResponse
          isAnimating={isAnimating}
          className="prose-headings:mt-5 prose-headings:mb-2 prose-h1:text-xl prose-h2:text-lg prose-h3:text-base"
        >
          {segment.content}
        </MessageResponse>
      );
    case "richList":
      return <RichList items={segment.items} />;
    case "chart":
      return <Chart data={segment.data} />;
    case "accordion":
      return <Accordion data={segment.data} />;
    case "highlight":
      return <Highlight data={segment.data} />;
    case "table":
      return <TableView data={segment.data} />;
    case "storyBriefing":
      return <StoryBriefing data={segment.data} />;
  }
}
