import { useEffect, useReducer } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "motion/react";
import { useGoalCelebrationStore } from "@/stores/goalCelebrationStore";
import { getEmojiForTitle } from "./emoji";

/**
 * Fullscreen goal-completion celebration. Ports
 * `desktop/Desktop/Sources/MainWindow/Components/GoalCelebrationView.swift`.
 *
 * Lifecycle: subscribed to `useGoalCelebrationStore.queuedGoal`. When a goal
 * becomes queued, run a 4-phase animation (dim → confetti → text → fadeout),
 * then clear the queue.
 */

type Phase = "idle" | "dim" | "confetti" | "text" | "fadeOut";

interface State {
  phase: Phase;
  goalTitle: string;
  goalEmoji: string;
}

type Action = { type: "start"; title: string } | { type: "advance" } | { type: "reset" };

const TIMINGS: Record<Exclude<Phase, "idle">, number> = {
  dim: 300,
  confetti: 500,
  text: 2200,
  fadeOut: 500,
};

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "start":
      return { phase: "dim", goalTitle: action.title, goalEmoji: getEmojiForTitle(action.title) };
    case "advance": {
      const order: Phase[] = ["idle", "dim", "confetti", "text", "fadeOut", "idle"];
      const i = order.indexOf(state.phase);
      const next = order[i + 1] ?? "idle";
      return { ...state, phase: next };
    }
    case "reset":
      return { phase: "idle", goalTitle: "", goalEmoji: "" };
  }
}

const CONFETTI_COUNT = 40;
const CONFETTI_COLORS = [
  "#FDE047", "#F59E0B", "#22C55E", "#3B82F6", "#EC4899",
  "#F97316", "#22D3EE", "#10B981", "#8B5CF6",
];

function makeConfetti() {
  return Array.from({ length: CONFETTI_COUNT }, (_, i) => {
    const angle = Math.random() * Math.PI * 2;
    const distance = 80 + Math.random() * 220;
    return {
      id: i,
      x: Math.cos(angle) * distance,
      y: Math.sin(angle) * distance,
      rot: Math.random() * 1080 - 540,
      scale: 0.6 + Math.random() * 0.9,
      color: CONFETTI_COLORS[i % CONFETTI_COLORS.length],
      isSquare: i % 3 === 0,
      delay: Math.random() * 0.12,
    };
  });
}

export function GoalCelebrationOverlay() {
  const queued = useGoalCelebrationStore((s) => s.queuedGoal);
  const clear = useGoalCelebrationStore((s) => s.clear);
  const [state, dispatch] = useReducer(reducer, {
    phase: "idle",
    goalTitle: "",
    goalEmoji: "",
  });

  useEffect(() => {
    if (!queued) return;
    dispatch({ type: "start", title: queued.title });
  }, [queued]);

  useEffect(() => {
    if (state.phase === "idle") return;
    const dur = TIMINGS[state.phase];
    const timer = setTimeout(() => {
      if (state.phase === "fadeOut") {
        dispatch({ type: "reset" });
        clear();
      } else {
        dispatch({ type: "advance" });
      }
    }, dur);
    return () => clearTimeout(timer);
  }, [state.phase, clear]);

  if (state.phase === "idle") return null;

  const showOverlay = state.phase !== "fadeOut";
  const showConfetti = state.phase === "confetti" || state.phase === "text";
  const showText = state.phase === "text";

  // Generate confetti once per celebration.
  const confetti = showConfetti ? makeConfetti() : [];

  return createPortal(
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 9999,
        pointerEvents: "none",
      }}
    >
      <AnimatePresence>
        {showOverlay && (
          <motion.div
            key="dim"
            initial={{ opacity: 0 }}
            animate={{ opacity: 0.55 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.4 }}
            style={{ position: "absolute", inset: 0, background: "black" }}
          />
        )}
      </AnimatePresence>

      {showConfetti && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {confetti.map((c) => (
            <motion.div
              key={c.id}
              initial={{ x: 0, y: 0, rotate: 0, scale: 0, opacity: 1 }}
              animate={{
                x: c.x,
                y: c.y,
                rotate: c.rot,
                scale: c.scale,
                opacity: 0,
              }}
              transition={{ duration: 1.6, delay: c.delay, ease: "easeOut" }}
              style={{
                position: "absolute",
                width: 10,
                height: 10,
                background: c.color,
                borderRadius: c.isSquare ? 2 : "50%",
              }}
            />
          ))}
        </div>
      )}

      <AnimatePresence>
        {showText && (
          <motion.div
            key="text"
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 1.05 }}
            transition={{ type: "spring", stiffness: 220, damping: 18 }}
            style={{
              position: "absolute",
              inset: 0,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: 14,
            }}
          >
            <div style={{ fontSize: 64 }}>{state.goalEmoji}</div>
            <div
              style={{
                fontSize: 32,
                fontWeight: 700,
                backgroundImage:
                  "linear-gradient(90deg, #FDE047 0%, #F97316 50%, #FDE047 100%)",
                WebkitBackgroundClip: "text",
                backgroundClip: "text",
                color: "transparent",
              }}
            >
              Goal Completed!
            </div>
            <div
              style={{
                fontSize: 16,
                color: "rgba(255,255,255,0.85)",
                textAlign: "center",
                maxWidth: 480,
                padding: "0 20px",
              }}
            >
              {state.goalTitle}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>,
    document.body,
  );
}
