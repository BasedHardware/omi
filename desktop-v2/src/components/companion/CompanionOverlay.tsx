/**
 * CompanionOverlay — fullscreen click-through canvas that renders animated
 * pointer sprites at coordinates Gemini returned.
 *
 * One overlay window per display, created by Rust (`companion_ensure_overlays`).
 * Listens for `companion:points` events and animates each point in sequence.
 *
 * Points arrive pre-mapped to overlay-window-local CSS points (see
 * `coordinateMap.imageToOverlayPoint`). The sprite uses `transform: translate3d`
 * with an `animationDelay` per-sprite to stagger.
 *
 * Note: events are broadcast to all overlay windows (the frontend uses
 * CGDirectDisplayID while Rust uses monitor-index for labels, so per-window
 * routing is brittle). Sprites whose coordinates fall outside this display's
 * bounds are clipped naturally by `overflow: hidden` on #root.
 */
import { useEffect, useState } from "react";
import { listen } from "@tauri-apps/api/event";

interface Point {
  x: number;
  y: number;
  label?: string;
}

interface PointsEvent {
  points: Point[];
  duration_ms: number;
  /** Monotonic session id so each new emit remounts the sprites with fresh animations. */
  session: number;
}

/** Live chain state pushed by `companionAssistant.ts::runChain` so the
 *  overlay can render a progress HUD alongside the per-step ring. */
interface ChainState {
  steps: Array<{ instruction: string; target_label: string }>;
  /** Index of the currently-active step (the one with the live ring). */
  currentIndex: number;
  /** True while we're between steps — re-screenshotting, grounding, prepping
   *  the next ring. The HUD swaps the current step's dot for a spinner so the
   *  user knows the system isn't frozen. */
  loading?: boolean;
}

/** Stagger between sprites (ms). */
const STAGGER_MS = 400;

export function CompanionOverlay() {
  const [event, setEvent] = useState<PointsEvent | null>(null);
  const [chain, setChain] = useState<ChainState | null>(null);

  useEffect(() => {
    let sessionCounter = 0;
    // Track chain-active state via ref so the click-dismiss listener can
    // observe it without re-running the effect on each toggle.
    const chainActiveRef = { current: false };

    const unlistenPoints = listen<{ points: Point[]; duration_ms: number }>(
      "companion:points",
      ({ payload }) => {
        sessionCounter += 1;
        setEvent({
          points: payload.points,
          duration_ms: payload.duration_ms,
          session: sessionCounter,
        });
      },
    );
    // The rdev listener emits this on any global mouse click; when the
    // "keep pointer until clicked" setting is on, we render with
    // duration_ms = -1 so the timer effect doesn't auto-clear, and we rely
    // on this event instead. While a chain is active, the chain controller
    // owns ring lifecycle (advance vs. stay-parked), so we ignore
    // click-dismiss and let `companion:points` from the controller drive
    // the rendered ring.
    const unlistenDismiss = listen("companion:click-dismiss", () => {
      if (chainActiveRef.current) return;
      setEvent(null);
    });
    const unlistenChainActive = listen<{ active: boolean }>(
      "companion:chain-active",
      ({ payload }) => {
        chainActiveRef.current = payload.active === true;
        if (!payload.active) setChain(null);
      },
    );
    const unlistenChainState = listen<ChainState>(
      "companion:chain-state",
      ({ payload }) => {
        setChain(payload);
      },
    );

    return () => {
      unlistenPoints.then((fn) => fn()).catch(() => {});
      unlistenDismiss.then((fn) => fn()).catch(() => {});
      unlistenChainActive.then((fn) => fn()).catch(() => {});
      unlistenChainState.then((fn) => fn()).catch(() => {});
    };
  }, []);

  // Clear sprites after the last one has finished, unless duration_ms is the
  // sentinel -1 ("persist until click-dismiss").
  useEffect(() => {
    if (!event) return;
    if (event.duration_ms < 0) return; // persistent mode — no auto-clear
    const lifetime = event.points.length * STAGGER_MS + event.duration_ms + 200;
    const t = window.setTimeout(() => setEvent(null), lifetime);
    return () => window.clearTimeout(t);
  }, [event]);

  return (
    <div className="fixed inset-0 overflow-hidden pointer-events-none">
      {chain ? <ChainHud chain={chain} /> : null}
      {event?.points.map((p, i) => (
        <PointerSprite
          key={`${event.session}-${i}`}
          x={p.x}
          y={p.y}
          label={p.label}
          delayMs={i * STAGGER_MS}
          lifetimeMs={event.duration_ms}
        />
      ))}
    </div>
  );
}

function PointerSprite({
  x,
  y,
  label,
  delayMs,
  lifetimeMs,
}: {
  x: number;
  y: number;
  label?: string;
  delayMs: number;
  lifetimeMs: number;
}) {
  // Use a 0×0 anchor div pinned to (x, y) so the ring + label children, which
  // are absolutely positioned, can be centered/offset relative to that exact
  // point. A naive `translate(-50%, -50%)` on a container that wraps the ring
  // AND the label centers the whole bounding box — pulling the ring upward
  // by half the label's height. Anchoring at 0×0 avoids that.
  // lifetimeMs < 0 → persistent mode: pop in and hold until click-dismissed.
  // The pop-in transition is fixed at 600 ms regardless of how long it stays.
  const persistent = lifetimeMs < 0;
  const animation = persistent
    ? `companion-point-pop-hold 600ms ease-out ${delayMs}ms both`
    : `companion-point-pop ${lifetimeMs}ms ease-out ${delayMs}ms both`;

  return (
    <div
      className="absolute"
      style={{
        left: `${x}px`,
        top: `${y}px`,
        width: 0,
        height: 0,
        animation,
      }}
    >
      {/* Outer ring: centered on (x, y) via translate(-50%, -50%). */}
      <div
        className="absolute rounded-full"
        style={{
          left: 0,
          top: 0,
          width: 56,
          height: 56,
          marginLeft: -28,
          marginTop: -28,
          border: "3px solid #3b82f6",
          boxShadow:
            "0 0 0 1.5px rgba(255,255,255,0.55), 0 0 18px 4px rgba(59, 130, 246, 0.55)",
        }}
      />
      {/* Center dot — also centered on (x, y). */}
      <div
        className="absolute rounded-full"
        style={{
          left: 0,
          top: 0,
          width: 12,
          height: 12,
          marginLeft: -6,
          marginTop: -6,
          background: "#3b82f6",
          boxShadow: "0 0 0 2px #fff",
        }}
      />
      {label ? (
        <div
          className="absolute -translate-x-1/2 whitespace-nowrap rounded-md px-2 py-1 text-xs font-medium"
          style={{
            left: 0,
            top: 36, // ring radius (28) + 8 px gap; sits below the ring without affecting its center
            background: "rgba(10, 12, 18, 0.9)",
            color: "white",
            border: "1px solid rgba(255,255,255,0.15)",
            backdropFilter: "blur(8px)",
            WebkitBackdropFilter: "blur(8px)",
          }}
        >
          {label}
        </div>
      ) : null}
    </div>
  );
}

/** Floating chain progress HUD — pinned to the top-center of the overlay
 *  while a multi-step chain is in flight. Lists every step with a state
 *  marker (✓ done, ● current, ○ pending) and the target_label so the user
 *  knows where they are and what's coming next. Click-through (parent has
 *  `pointer-events-none`) so it doesn't intercept the user's actual clicks
 *  on the dock or app windows. */
function ChainHud({ chain }: { chain: ChainState }) {
  if (chain.steps.length === 0) return null;
  const total = chain.steps.length;

  return (
    <div
      className="fixed left-1/2 top-6 -translate-x-1/2"
      style={{
        background: "rgba(10, 12, 18, 0.92)",
        border: "1px solid rgba(255, 255, 255, 0.12)",
        borderRadius: 14,
        padding: "10px 14px",
        minWidth: 320,
        maxWidth: 480,
        boxShadow: "0 10px 40px rgba(0,0,0,0.45)",
        backdropFilter: "blur(14px)",
        WebkitBackdropFilter: "blur(14px)",
        color: "white",
      }}
    >
      <div className="flex items-center justify-between gap-3 pb-1.5">
        <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: 0.4, opacity: 0.6 }}>
          GUIDED STEPS
        </span>
        <span
          style={{
            fontSize: 11,
            fontWeight: 600,
            color: "#3b82f6",
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {Math.min(chain.currentIndex + 1, total)} of {total}
        </span>
      </div>
      <ol style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {chain.steps.map((s, i) => {
          let status: "done" | "current" | "pending" | "loading";
          if (i < chain.currentIndex) status = "done";
          else if (i === chain.currentIndex) status = chain.loading ? "loading" : "current";
          else status = "pending";
          return <ChainStepRow key={i} step={s} index={i} status={status} />;
        })}
      </ol>
      <div
        style={{
          marginTop: 8,
          fontSize: 10,
          opacity: 0.5,
          textAlign: "center",
        }}
      >
        {chain.loading ? "Looking for the next step…" : "Press Esc to cancel"}
      </div>
    </div>
  );
}

function ChainStepRow({
  step,
  index,
  status,
}: {
  step: { instruction: string; target_label: string };
  index: number;
  status: "done" | "current" | "pending" | "loading";
}) {
  const isActive = status === "current" || status === "loading";
  const dotColor =
    status === "done"
      ? "#22c55e"
      : isActive
        ? "#3b82f6"
        : "rgba(255,255,255,0.25)";
  const dotFill = status === "done" ? "#22c55e" : status === "current" ? "#3b82f6" : "transparent";
  const textOpacity = status === "pending" ? 0.5 : status === "done" ? 0.65 : 1;
  const fontWeight = isActive ? 600 : 500;

  return (
    <li
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: 10,
        opacity: textOpacity,
      }}
    >
      <span
        style={{
          width: 18,
          flexShrink: 0,
          fontSize: 11,
          fontVariantNumeric: "tabular-nums",
          opacity: 0.5,
          paddingTop: 1,
        }}
      >
        {index + 1}.
      </span>
      {status === "loading" ? (
        <Spinner />
      ) : (
        <span
          style={{
            width: 14,
            height: 14,
            flexShrink: 0,
            borderRadius: "50%",
            border: `2px solid ${dotColor}`,
            background: dotFill,
            marginTop: 2,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "white",
            fontSize: 9,
            fontWeight: 800,
            lineHeight: 1,
          }}
        >
          {status === "done" ? "✓" : ""}
        </span>
      )}
      <div style={{ flexGrow: 1, minWidth: 0 }}>
        <div style={{ fontSize: 12, fontWeight, lineHeight: 1.35 }}>{step.instruction}</div>
        <div
          style={{
            fontSize: 10.5,
            opacity: 0.55,
            marginTop: 1,
            fontFamily: "ui-monospace, SFMono-Regular, monospace",
          }}
        >
          {step.target_label}
        </div>
      </div>
    </li>
  );
}

/** 14×14 indeterminate spinner used while the chain controller is busy
 *  re-screenshotting + grounding the next step. CSS keyframe lives in
 *  `globals.css` (companion-spin). */
function Spinner() {
  return (
    <span
      style={{
        width: 14,
        height: 14,
        flexShrink: 0,
        borderRadius: "50%",
        border: "2px solid rgba(59, 130, 246, 0.25)",
        borderTopColor: "#3b82f6",
        marginTop: 2,
        animation: "companion-spin 0.8s linear infinite",
      }}
    />
  );
}
