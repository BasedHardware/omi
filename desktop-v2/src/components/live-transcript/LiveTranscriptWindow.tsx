import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { ChevronDown, ChevronUp, Mic, X } from "lucide-react";
import {
  SpeakerBubbles,
  type LiveSegment,
} from "@/components/transcript/SpeakerBubbles";
import { OrbIndicator } from "@/components/feedback/OrbIndicator";
import "./LiveTranscriptWindow.css";

/**
 * Shape returned by `poll_live_transcript_segments` (Rust). Field names use
 * camelCase because the Rust struct renames them with `#[serde(rename)]`.
 */
interface BufferedSegment {
  text: string;
  isFinal: boolean;
  speaker: string;
  speakerId: number;
  isUser: boolean;
  start: number;
  end: number;
}

const POLL_INTERVAL_MS = 250;
/** Keep only the last N final segments in view. Older lines scroll off. */
const MAX_VISIBLE_SEGMENTS = 6;

export function LiveTranscriptWindow() {
  const [segments, setSegments] = useState<LiveSegment[]>([]);
  const [partial, setPartial] = useState<Record<string, string>>({});
  const [collapsed, setCollapsed] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const bodyRef = useRef<HTMLDivElement | null>(null);

  // Poll the Rust buffer. See commands/live_transcript.rs for why polling
  // instead of `listen("transcript:partial", …)`.
  useEffect(() => {
    let cancelled = false;

    const tick = async () => {
      if (cancelled) return;
      try {
        const buffered = await invoke<BufferedSegment[]>(
          "poll_live_transcript_segments",
        );
        if (cancelled) return;
        if (buffered.length > 0) {
          setSegments((prevSegments) => {
            let nextSegments = prevSegments;
            setPartial((prevPartial) => {
              const nextPartial = { ...prevPartial };
              for (const seg of buffered) {
                if (!seg.text || !seg.speaker) continue;
                if (seg.isFinal) {
                  delete nextPartial[seg.speaker];
                  nextSegments = [
                    ...nextSegments,
                    {
                      text: seg.text,
                      speaker: seg.speaker,
                      speakerId: seg.speakerId,
                      isUser: seg.isUser,
                      start: seg.start,
                      end: seg.end,
                    },
                  ];
                } else {
                  nextPartial[seg.speaker] = seg.text;
                }
              }
              return nextPartial;
            });
            return nextSegments;
          });
        }
      } catch {
        // Non-fatal; next tick retries.
      }
      if (!cancelled) {
        window.setTimeout(tick, POLL_INTERVAL_MS);
      }
    };

    tick();
    return () => {
      cancelled = true;
    };
  }, []);

  // Match the Tauri window height to the rendered content so the glass
  // surface hugs the transcript.
  useLayoutEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    let frame = 0;
    const push = () => {
      frame = 0;
      const height = Math.ceil(el.getBoundingClientRect().height);
      if (height > 0) {
        invoke("resize_live_transcript", { height }).catch(() => {});
      }
    };
    const schedule = () => {
      if (frame) return;
      frame = requestAnimationFrame(push);
    };
    const observer = new ResizeObserver(schedule);
    observer.observe(el);
    schedule();
    return () => {
      observer.disconnect();
      if (frame) cancelAnimationFrame(frame);
    };
  }, [segments, partial, collapsed]);

  // Auto-scroll the transcript body to the bottom whenever new text arrives.
  useEffect(() => {
    if (collapsed) return;
    const el = bodyRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [segments, partial, collapsed]);

  const dismiss = () => invoke("hide_live_transcript").catch(() => {});
  const toggleCollapsed = () => setCollapsed((c) => !c);

  // Only show the most recent N finalized segments — older lines are
  // kept in memory but scroll off the visible window.
  const visibleSegments =
    segments.length > MAX_VISIBLE_SEGMENTS
      ? segments.slice(-MAX_VISIBLE_SEGMENTS)
      : segments;

  const isEmpty =
    segments.length === 0 &&
    Object.values(partial).every((t) => !t || !t.trim());

  // -------- Collapsed: Opal listening orb pill --------
  if (collapsed) {
    // Find the latest partial or finalized line for a one-line preview.
    const latestPartial = Object.values(partial).find((t) => t && t.trim());
    const latestFinal = segments[segments.length - 1]?.text;
    const preview = (latestPartial || latestFinal || "Listening…").trim();

    return (
      <div ref={rootRef} className="lt-root lt-root-collapsed">
        <button
          type="button"
          onClick={toggleCollapsed}
          aria-label="Expand live transcript"
          className="lt-collapsed-pill"
          title="Expand live transcript"
        >
          <OrbIndicator state="listening" variant="opal" size="sm" />
          <span className="lt-collapsed-preview">{preview}</span>
          <ChevronUp size={12} className="lt-collapsed-caret" />
        </button>
      </div>
    );
  }

  // -------- Expanded: full glass card --------
  return (
    <div ref={rootRef} className="lt-root">
      <div className="lt-card">
        <header className="lt-header">
          <div className="lt-title">
            <span className="lt-pulse" aria-hidden>
              <span className="lt-pulse-ping" />
              <span className="lt-pulse-dot" />
            </span>
            <Mic size={12} />
            <span>Live transcript</span>
          </div>
          <div className="lt-header-actions">
            <button
              type="button"
              onClick={toggleCollapsed}
              aria-label="Collapse to orb"
              title="Collapse"
              className="lt-iconbtn"
            >
              <ChevronDown size={13} />
            </button>
            <button
              type="button"
              onClick={dismiss}
              aria-label="Hide live transcript"
              title="Hide"
              className="lt-iconbtn"
            >
              <X size={13} />
            </button>
          </div>
        </header>
        <div ref={bodyRef} className="lt-body">
          {isEmpty ? (
            <p className="lt-empty">Listening… speak and your words land here.</p>
          ) : (
            <SpeakerBubbles
              segments={visibleSegments}
              partialBySpeaker={partial}
              compact
            />
          )}
        </div>
      </div>
    </div>
  );
}
