import { useEffect, useRef, useState } from "react";
import { Check, Lightbulb, Minus, Pencil, Plus, Trash2 } from "lucide-react";
import type { Goal } from "@/stores/goalStore";
import { getEmojiForTitle } from "./emoji";

interface Props {
  goal: Goal;
  onEdit: () => void;
  onUpdateProgress: (value: number) => void;
  onDelete: () => void;
  onGetAdvice?: () => void;
}

/** 0-1 fraction → hex color ramp (matches Swift `progressColor`). */
function colorForProgress(progress: number): string {
  if (progress >= 1) return "#22C55E"; // green (complete)
  if (progress >= 0.8) return "#4ADE80"; // emerald
  if (progress >= 0.6) return "#84CC16"; // lime
  if (progress >= 0.4) return "#FACC15"; // yellow
  if (progress >= 0.2) return "#F97316"; // orange
  return "#60A5FA"; // blue (just started)
}

export function GoalRow({
  goal,
  onEdit,
  onUpdateProgress,
  onDelete,
  onGetAdvice,
}: Props) {
  const [dragFraction, setDragFraction] = useState<number | null>(null);
  const trackRef = useRef<HTMLDivElement | null>(null);
  const isDragging = dragFraction !== null;

  const span = goal.target_value - goal.min_value;
  const baseFraction = span > 0 ? (goal.current_value - goal.min_value) / span : 0;
  const displayFraction = Math.max(0, Math.min(1, dragFraction ?? baseFraction));

  const displayCurrent = isDragging
    ? Math.round(goal.min_value + displayFraction * span)
    : Math.round(goal.current_value);

  const fillColor = colorForProgress(displayFraction);
  const percent = Math.round(displayFraction * 100);
  const isComplete = displayFraction >= 1;

  const computeFraction = (clientX: number): number => {
    const el = trackRef.current;
    if (!el) return displayFraction;
    const rect = el.getBoundingClientRect();
    return Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
  };

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    setDragFraction(computeFraction(e.clientX));
  };

  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (dragFraction === null) return;
    setDragFraction(computeFraction(e.clientX));
  };

  const onPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (dragFraction === null) return;
    e.currentTarget.releasePointerCapture(e.pointerId);
    const frac = computeFraction(e.clientX);
    const raw = goal.min_value + frac * span;
    const clamped = Math.max(goal.min_value, Math.min(raw, goal.target_value));
    const rounded = Math.round(clamped);
    if (Math.abs(rounded - goal.current_value) >= 0.5) {
      onUpdateProgress(rounded);
    }
    setDragFraction(null);
  };

  const step = (delta: number) => {
    const next = Math.max(
      goal.min_value,
      Math.min(goal.target_value, goal.current_value + delta),
    );
    if (next !== goal.current_value) {
      onUpdateProgress(next);
    }
  };

  useEffect(() => {
    const el = trackRef.current;
    if (!el) return;
    const handler = (e: KeyboardEvent) => {
      if (document.activeElement !== el) return;
      if (e.key === "ArrowLeft" || e.key === "ArrowDown") {
        e.preventDefault();
        step(-1);
      } else if (e.key === "ArrowRight" || e.key === "ArrowUp") {
        e.preventDefault();
        step(1);
      }
    };
    el.addEventListener("keydown", handler);
    return () => el.removeEventListener("keydown", handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [goal.current_value, goal.min_value, goal.target_value]);

  const hasDescription = Boolean(goal.description && goal.description.trim());
  const targetLabel = `${Math.round(goal.target_value)}${goal.unit ? ` ${goal.unit}` : ""}`;
  const currentLabel = `${displayCurrent}${goal.unit ? ` ${goal.unit}` : ""}`;

  return (
    <div className={`goal-card${isComplete ? " goal-card-complete" : ""}`}>
      <div className="goal-card-head">
        <button
          type="button"
          className="goal-emoji"
          onClick={onEdit}
          aria-label="Edit goal"
          title="Edit"
        >
          <span>{getEmojiForTitle(goal.title)}</span>
          {isComplete && (
            <span className="goal-emoji-check">
              <Check size={10} strokeWidth={3} />
            </span>
          )}
        </button>

        <div className="goal-card-text">
          <button
            type="button"
            className="goal-card-title"
            onClick={onEdit}
            title="Edit goal"
          >
            {goal.title}
          </button>
          {hasDescription && (
            <p className="goal-card-desc">{goal.description}</p>
          )}
        </div>

        <div className="goal-card-actions">
          {onGetAdvice && (
            <button
              type="button"
              className="goal-card-action goal-card-action-advice"
              onClick={onGetAdvice}
              aria-label="Get advice"
              title="Get advice"
            >
              <Lightbulb size={14} />
            </button>
          )}
          <button
            type="button"
            className="goal-card-action"
            onClick={onEdit}
            aria-label="Edit goal"
            title="Edit"
          >
            <Pencil size={14} />
          </button>
          <button
            type="button"
            className="goal-card-action goal-card-action-danger"
            onClick={onDelete}
            aria-label="Delete goal"
            title="Delete"
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>

      <div className="goal-card-progress">
        <div className="goal-card-progress-head">
          <div className="goal-card-progress-numbers">
            <span
              className={`goal-card-current${isDragging ? " goal-card-current-live" : ""}`}
              style={{ color: isComplete ? fillColor : undefined }}
            >
              {currentLabel}
            </span>
            <span className="goal-card-target">/ {targetLabel}</span>
          </div>
          <span
            className="goal-card-percent"
            style={{
              color: fillColor,
              backgroundColor: `${fillColor}1A`,
            }}
          >
            {percent}%
          </span>
        </div>

        <div
          ref={trackRef}
          className={`goal-track${isDragging ? " goal-track-dragging" : ""}`}
          role="slider"
          tabIndex={0}
          aria-valuemin={goal.min_value}
          aria-valuemax={goal.target_value}
          aria-valuenow={goal.current_value}
          aria-label={`${goal.title} progress`}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
        >
          <div
            className="goal-track-fill"
            style={{
              width: `${displayFraction * 100}%`,
              background: `linear-gradient(90deg, ${fillColor}B3, ${fillColor})`,
            }}
          />
          <div
            className="goal-track-thumb"
            style={{
              left: `calc(${displayFraction * 100}% - 8px)`,
              borderColor: fillColor,
            }}
          />
        </div>

        <div className="goal-card-stepper">
          <button
            type="button"
            className="goal-step-btn"
            onClick={() => step(-1)}
            disabled={goal.current_value <= goal.min_value}
            aria-label="Decrease"
          >
            <Minus size={14} />
          </button>
          <button
            type="button"
            className="goal-step-btn"
            onClick={() => step(1)}
            disabled={goal.current_value >= goal.target_value}
            aria-label="Increase"
          >
            <Plus size={14} />
          </button>
        </div>
      </div>
    </div>
  );
}
