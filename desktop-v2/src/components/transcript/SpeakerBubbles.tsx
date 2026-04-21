/**
 * SpeakerBubbles — chat-style live transcript mirroring the Swift
 * `LiveTranscriptView` / `SpeakerBubbleView`.
 *
 * Each speaker's segments are grouped into a left/right-aligned bubble
 * stream with a coloured avatar, a speaker label, and a start timestamp.
 * Unknown speakers (those without an entry in `useSpeakerStore`) show an
 * "Identify" pencil affordance — tapping it fires `onSpeakerTapped`, which
 * the parent wires to `LiveNameSpeakerSheet`.
 *
 * The component also surfaces any currently-streaming partials per speaker
 * so the transcript feels live — partials render italic with reduced
 * opacity and do not get a timestamp.
 */

import { useEffect, useMemo, useRef } from "react";
import { Mic, Pencil } from "lucide-react";
import { useSpeakerStore, formatSpeakerDisplayName } from "@/stores/speakerStore";
import { cn } from "@/lib/utils";

/**
 * Shape of a live transcript segment consumed by `<SpeakerBubbles>`.
 *
 * Declared locally (instead of importing from `audioStore`) so the
 * component doesn't hard-depend on the audio store's evolving shape, and
 * so callers with their own transcript format can still use it.
 */
export interface LiveSegment {
  text: string;
  speaker: string;
  speakerId: number;
  isUser: boolean;
  start: number;
  end: number;
}

export interface SpeakerBubblesProps {
  segments: LiveSegment[];
  partialBySpeaker?: Record<string, string>;
  /** Called when the user wants to identify an unknown speaker. */
  onSpeakerTapped?: (segment: LiveSegment) => void;
  /** Tight variant used inside the Floating Bar — smaller padding, compact avatars. */
  compact?: boolean;
  className?: string;
}

// Consistent per-speaker colours — keyed by speaker index.
const SPEAKER_BG = [
  "bg-blue-500/15 border-blue-400/30",
  "bg-emerald-500/15 border-emerald-400/30",
  "bg-amber-500/15 border-amber-400/30",
  "bg-purple-500/15 border-purple-400/30",
  "bg-rose-500/15 border-rose-400/30",
  "bg-cyan-500/15 border-cyan-400/30",
  "bg-orange-500/15 border-orange-400/30",
  "bg-teal-500/15 border-teal-400/30",
];

const AVATAR_BG = [
  "bg-blue-500/30 text-blue-100",
  "bg-emerald-500/30 text-emerald-100",
  "bg-amber-500/30 text-amber-100",
  "bg-purple-500/30 text-purple-100",
  "bg-rose-500/30 text-rose-100",
  "bg-cyan-500/30 text-cyan-100",
  "bg-orange-500/30 text-orange-100",
  "bg-teal-500/30 text-teal-100",
];

function formatTime(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function getBubbleStyle(
  isUser: boolean,
  speakerIndex: number,
): { bubble: string; avatar: string } {
  if (isUser) {
    return {
      bubble: "bg-primary/20 border-primary/30",
      avatar: "bg-primary text-primary-foreground",
    };
  }
  const idx = speakerIndex >= 0 ? speakerIndex % SPEAKER_BG.length : 0;
  return {
    bubble: SPEAKER_BG[idx],
    avatar: AVATAR_BG[idx],
  };
}

function avatarInitial(displayName: string): string {
  const first = displayName.trim().charAt(0);
  return first ? first.toUpperCase() : "?";
}

interface Bubble {
  key: string;
  speaker: string;
  speakerId: number;
  isUser: boolean;
  text: string;
  start: number;
  end: number;
  isPartial: boolean;
  /** The first segment for this speaker — used by the identify callback. */
  anchorSegment: LiveSegment;
}

export function SpeakerBubbles({
  segments,
  partialBySpeaker = {},
  onSpeakerTapped,
  compact = false,
  className,
}: SpeakerBubblesProps) {
  const names = useSpeakerStore((s) => s.names);

  // Drop segments with a missing speaker — backend sometimes serves these
  // for historic conversations pre-diarization and they'd crash downstream.
  const safeSegments = useMemo(
    () => segments.filter((s): s is SpeakerBubblesProps["segments"][number] =>
      typeof s?.speaker === "string" && s.speaker.length > 0,
    ),
    [segments],
  );

  // Stable ordering of speaker labels so colours don't jump around.
  const speakerOrder = useMemo(() => {
    const order: string[] = [];
    for (const seg of safeSegments) {
      if (!order.includes(seg.speaker)) order.push(seg.speaker);
    }
    for (const sp of Object.keys(partialBySpeaker)) {
      if (!order.includes(sp)) order.push(sp);
    }
    return order;
  }, [safeSegments, partialBySpeaker]);

  // Group consecutive segments from the same speaker into a single bubble.
  const bubbles = useMemo<Bubble[]>(() => {
    const out: Bubble[] = [];
    for (let i = 0; i < safeSegments.length; i++) {
      const seg = safeSegments[i];
      const last = out[out.length - 1];
      if (last && !last.isPartial && last.speaker === seg.speaker) {
        last.text = `${last.text} ${seg.text}`;
        last.end = seg.end;
        last.key += `-${i}`;
        continue;
      }
      out.push({
        key: `${seg.speaker}-${i}`,
        speaker: seg.speaker,
        speakerId: seg.speakerId,
        isUser: seg.isUser,
        text: seg.text,
        start: seg.start,
        end: seg.end,
        isPartial: false,
        anchorSegment: seg,
      });
    }
    for (const [speaker, text] of Object.entries(partialBySpeaker)) {
      if (!text) continue;
      const prior = safeSegments.find((s) => s.speaker === speaker);
      const last = out[out.length - 1];
      const base: Bubble = {
        key: `partial-${speaker}`,
        speaker,
        speakerId: prior?.speakerId ?? 0,
        isUser: prior?.isUser ?? false,
        text,
        start: prior?.start ?? 0,
        end: prior?.end ?? 0,
        isPartial: true,
        anchorSegment:
          prior ?? {
            speaker,
            speakerId: 0,
            isUser: false,
            text,
            start: 0,
            end: 0,
          },
      };
      if (last && !last.isPartial && last.speaker === speaker) {
        // Partial continues the last bubble visually; render separately but
        // close to the final so the user sees the continuation.
        out.push(base);
      } else {
        out.push(base);
      }
    }
    return out;
  }, [safeSegments, partialBySpeaker]);

  // Auto-scroll the pinned bottom anchor whenever content grows.
  const scrollAnchor = useRef<HTMLDivElement | null>(null);
  const fingerprint = useMemo(() => {
    const last = bubbles[bubbles.length - 1];
    if (!last) return "0";
    return `${bubbles.length}-${last.key}-${last.text.length}`;
  }, [bubbles]);
  useEffect(() => {
    scrollAnchor.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [fingerprint]);

  if (bubbles.length === 0) {
    return (
      <div
        className={cn(
          "flex flex-1 flex-col items-center justify-center gap-3 px-8 text-center",
          className,
        )}
      >
        <Mic className="size-6 text-muted-foreground/60" />
        <p className="max-w-sm text-sm text-muted-foreground">
          Listening — speak and your transcript will appear here.
        </p>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "flex flex-col gap-3",
        compact ? "px-2 py-2" : "px-4 py-4",
        className,
      )}
    >
      {bubbles.map((b) => {
        const speakerIdx = speakerOrder.indexOf(b.speaker);
        const style = getBubbleStyle(b.isUser, speakerIdx);
        const hasName = !!names[b.speaker];
        const displayName = formatSpeakerDisplayName(b.speaker, b.isUser, names);
        const canIdentify = !b.isUser && !hasName && !!onSpeakerTapped;

        return (
          <div
            key={b.key}
            className={cn(
              "flex w-full gap-2",
              b.isUser ? "justify-end" : "justify-start",
            )}
          >
            {!b.isUser && (
              <div
                className={cn(
                  "flex shrink-0 items-center justify-center rounded-full font-semibold",
                  compact ? "size-6 text-[10px]" : "size-8 text-[11px]",
                  style.avatar,
                )}
                aria-hidden="true"
              >
                {avatarInitial(displayName)}
              </div>
            )}
            <div
              className={cn(
                "flex min-w-0 flex-col gap-1",
                b.isUser ? "items-end" : "items-start",
                compact ? "max-w-[85%]" : "max-w-[78%]",
              )}
            >
              <div
                className={cn(
                  "flex items-center gap-1.5 text-[11px] leading-none",
                  b.isUser && "flex-row-reverse",
                )}
              >
                {canIdentify ? (
                  <button
                    type="button"
                    className="inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    onClick={() => onSpeakerTapped?.(b.anchorSegment)}
                    aria-label={`Identify ${displayName}`}
                  >
                    <span className="font-medium">{displayName}</span>
                    <Pencil className="size-3" />
                  </button>
                ) : (
                  <span
                    className={cn(
                      "text-xs font-medium",
                      hasName ? "text-primary" : "text-muted-foreground",
                    )}
                  >
                    {displayName}
                  </span>
                )}
                {!b.isPartial && (
                  <span className="tabular-nums text-muted-foreground/70">
                    {formatTime(b.start)}
                  </span>
                )}
                {b.isPartial && (
                  <span className="inline-flex items-center gap-1 text-muted-foreground/70">
                    <span className="relative flex size-1.5 shrink-0">
                      <span className="absolute inline-flex size-full animate-ping rounded-full bg-red-500/60" />
                      <span className="relative inline-flex size-1.5 rounded-full bg-red-500" />
                    </span>
                    live
                  </span>
                )}
              </div>
              <div
                className={cn(
                  "rounded-2xl border text-[13px] leading-relaxed text-foreground",
                  compact ? "px-3 py-1.5" : "px-3.5 py-2",
                  style.bubble,
                  b.isPartial && "italic opacity-80",
                )}
              >
                {b.text}
              </div>
            </div>
            {b.isUser && (
              <div
                className={cn(
                  "flex shrink-0 items-center justify-center rounded-full font-semibold",
                  compact ? "size-6 text-[10px]" : "size-8 text-[11px]",
                  style.avatar,
                )}
                aria-hidden="true"
              >
                {avatarInitial(displayName)}
              </div>
            )}
          </div>
        );
      })}
      <div ref={scrollAnchor} aria-hidden="true" className="h-px" />
    </div>
  );
}
