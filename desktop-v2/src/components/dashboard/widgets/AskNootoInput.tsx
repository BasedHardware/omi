import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowUp, Sparkles } from "lucide-react";
import { useChatStore } from "@/stores/chatStore";

const SUGGESTIONS = [
  "What did I work on today?",
  "Summarize my screen time",
  "What's next on my plate?",
];

/**
 * Compact "Ask Nooto anything" input shown on the dashboard. Mirrors the
 * upstream change in v0.11.276 that replaced the dashboard Conversations list
 * with an embedded chat entry point. Submitting fires a message via the
 * chatStore and then navigates to `/chat` so the user lands on the streaming
 * response.
 */
export function AskNootoInput() {
  const navigate = useNavigate();
  const sendMessage = useChatStore((s) => s.sendMessage);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const [text, setText] = useState("");

  const submit = (payload: string) => {
    const trimmed = payload.trim();
    if (!trimmed || isStreaming) return;
    setText("");
    // Fire-and-forget: chatStore persists the message + streams the response,
    // so by the time /chat mounts it picks up the in-flight exchange.
    void sendMessage(trimmed);
    navigate("/chat");
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit(text);
    }
  };

  return (
    <section className="dashboard-ask">
      <div className="dashboard-ask-label">
        <Sparkles size={13} />
        <span>Ask Nooto anything</span>
      </div>
      <div className="dashboard-ask-input-wrap">
        <textarea
          className="dashboard-ask-input"
          placeholder="What's on your mind? Press Enter to send"
          value={text}
          rows={1}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isStreaming}
        />
        <button
          type="button"
          className="dashboard-ask-submit"
          onClick={() => submit(text)}
          disabled={!text.trim() || isStreaming}
          aria-label="Send message"
          title="Send (Enter)"
        >
          <ArrowUp size={14} />
        </button>
      </div>
      <div className="dashboard-ask-suggestions">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            type="button"
            className="dashboard-ask-chip"
            onClick={() => submit(s)}
            disabled={isStreaming}
          >
            {s}
          </button>
        ))}
      </div>
    </section>
  );
}
