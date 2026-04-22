/**
 * Waveform — thin audio-level visualiser rendered to a `<canvas>` at 60fps.
 *
 * Mirrors the Swift `AudioLevelWaveformView`: a row of vertical bars that
 * scale with the current input level. Bars in the centre are slightly
 * taller than the edges for an organic look, and each bar has a tiny
 * deterministic offset so the result doesn't look too regular.
 *
 * Accepts an optional `level` prop in the [0, 1] range. When omitted the
 * waveform falls back to the exported `useWaveformLevel` hook, which
 * produces a synthetic pulse from transcription activity until the Rust
 * `audio-capture` plugin exposes real RMS frames.
 */

import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import { useWaveformLevel } from "@/components/transcript/useWaveformLevel";

export interface WaveformProps {
  /** Number of bars. Defaults to 12 (same as Swift). */
  barCount?: number;
  /** Input level in the [0, 1] range. Falls back to `useWaveformLevel()`. */
  level?: number;
  /** When false, the bars sit at their minimum height in a dim tint. */
  isActive?: boolean;
  /** Canvas height in CSS pixels. */
  height?: number;
  /** Extra className on the wrapping canvas. */
  className?: string;
}

const BAR_WIDTH = 3;
const BAR_GAP = 3;
const MIN_BAR = 4;
const CORNER_RADIUS = 1.5;

export function Waveform({
  barCount = 12,
  level: levelProp,
  isActive = true,
  height = 28,
  className,
}: WaveformProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  // Synthesised level from transcription events — only subscribed when the
  // caller hasn't passed in its own signal.
  const synthesisedLevel = useWaveformLevel(levelProp === undefined);
  const displayLevel = levelProp ?? synthesisedLevel;

  // Smoothed value kept in a ref so the animation frame loop reads the
  // latest target without triggering React re-renders.
  const targetRef = useRef(0);
  const smoothedRef = useRef(0);

  useEffect(() => {
    targetRef.current = isActive ? Math.max(0, Math.min(1, displayLevel)) : 0;
  }, [displayLevel, isActive]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const width = barCount * BAR_WIDTH + (barCount - 1) * BAR_GAP;

    // Cache the resolved foreground so the RAF loop doesn't pay a
    // getComputedStyle + style-recalc cost on every bar. Refreshed when
    // `<html>` flips the `.dark` class (MutationObserver below).
    let foreground = getComputedStyle(canvas).color || "rgb(255, 255, 255)";
    const themeObserver = new MutationObserver(() => {
      foreground = getComputedStyle(canvas).color || foreground;
    });
    themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });

    const setSize = () => {
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    setSize();

    let rafId = 0;
    const draw = () => {
      // Exponential smoothing towards target for a silky 60fps feel.
      const target = targetRef.current;
      const current = smoothedRef.current;
      const next =
        Math.abs(target - current) < 0.002
          ? target
          : current + (target - current) * 0.25;
      smoothedRef.current = next;

      // Apply a sensitivity boost so low levels are still visible (matches Swift).
      const boosted = Math.min(1, Math.pow(next, 0.5) * 2.5);

      ctx.clearRect(0, 0, width, height);

      const mid = (barCount - 1) / 2;
      for (let i = 0; i < barCount; i++) {
        // Center bars taller than edges — up to 40% taller.
        const offset = Math.abs(i - mid) / (barCount / 2);
        const variation = 1 - offset * 0.4;
        // Deterministic jitter for an organic feel.
        const hash = Math.sin(i * 1.618 + 0.5);
        const jitter = 0.85 + 0.3 * (hash * 0.5 + 0.5);

        const active = isActive && boosted > 0.02;
        const scaled = boosted * variation * jitter;
        const barHeight = active
          ? Math.max(MIN_BAR, Math.min(height, MIN_BAR + (height - MIN_BAR) * scaled))
          : MIN_BAR;

        const x = i * (BAR_WIDTH + BAR_GAP);
        const y = (height - barHeight) / 2;

        // Colour varies with intensity to match the Swift tiers.
        if (!active) {
          ctx.fillStyle = "rgba(161, 161, 170, 0.35)"; // zinc-400/35
        } else if (boosted > 0.6) {
          ctx.fillStyle = "rgb(59, 130, 246)"; // brand blue
        } else if (boosted > 0.2) {
          ctx.fillStyle = foreground;
        } else {
          ctx.fillStyle = "rgba(161, 161, 170, 0.7)";
        }

        // Rounded rect — tiny radius to match 1.5pt Swift value.
        const r = Math.min(CORNER_RADIUS, BAR_WIDTH / 2);
        ctx.beginPath();
        ctx.moveTo(x + r, y);
        ctx.arcTo(x + BAR_WIDTH, y, x + BAR_WIDTH, y + barHeight, r);
        ctx.arcTo(x + BAR_WIDTH, y + barHeight, x, y + barHeight, r);
        ctx.arcTo(x, y + barHeight, x, y, r);
        ctx.arcTo(x, y, x + BAR_WIDTH, y, r);
        ctx.closePath();
        ctx.fill();
      }

      rafId = requestAnimationFrame(draw);
    };
    rafId = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(rafId);
      themeObserver.disconnect();
    };
  }, [barCount, height, isActive]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className={cn("block shrink-0 text-foreground", className)}
    />
  );
}
