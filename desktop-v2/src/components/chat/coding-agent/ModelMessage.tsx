import { GenerativeMarkdown } from "@/components/generative-ui/GenerativeMarkdown";

interface Props {
  text: string;
  isStreaming?: boolean;
}

/**
 * Renders accumulated text events for a single assistant turn.
 * Re-renders as `text` grows during streaming.
 */
export function ModelMessage({ text, isStreaming }: Props) {
  if (!text) return null;

  return (
    <div className="py-1">
      <GenerativeMarkdown content={text} isAnimating={isStreaming} />
    </div>
  );
}
