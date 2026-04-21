/**
 * useWaveformLevel — synthesises a Waveform-friendly audio level by
 * listening to the existing `transcript:partial` event stream.
 *
 * The Rust `audio-capture` plugin does not yet emit real RMS/peak frames,
 * so we fake an organic pulse keyed off transcription activity:
 *   - each partial bumps the level up with a bit of jitter,
 *   - finals spike higher,
 *   - the level decays exponentially while silent.
 *
 * This is a single shared source — all `<Waveform>` instances read the same
 * module-level value so we don't pay for N independent subscriptions.
 */

import { useEffect, useState } from "react";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

interface TranscriptPartialEvent {
  text: string;
  is_final: boolean;
}

let currentLevel = 0;
let subscribers = 0;
let listeners: Set<(level: number) => void> = new Set();
let tickInterval: ReturnType<typeof setInterval> | null = null;
let unlisten: UnlistenFn | null = null;

function broadcast(level: number): void {
  currentLevel = level;
  for (const fn of listeners) fn(level);
}

function pulse(isFinal: boolean): void {
  const base = isFinal ? 0.65 : 0.45;
  const target = Math.min(1, base + Math.random() * 0.3);
  broadcast(Math.max(currentLevel, target));
}

function ensureSubscribed(): void {
  if (tickInterval == null) {
    tickInterval = setInterval(() => {
      if (currentLevel === 0) return;
      const next = Math.max(0, currentLevel * 0.82);
      broadcast(next < 0.005 ? 0 : next);
    }, 80);
  }
  if (unlisten == null) {
    // Fire and forget — the subscription cleans itself up when the
    // module unloads. Tauri's listen returns an `UnlistenFn` we stash
    // so the teardown path (no more subscribers) can cancel it.
    listen<TranscriptPartialEvent>("transcript:partial", (event) => {
      const { text, is_final } = event.payload;
      if (!text) return;
      pulse(is_final);
    })
      .then((fn) => {
        unlisten = fn;
      })
      .catch(() => {
        // ignore — running outside Tauri
      });
  }
}

function teardownIfIdle(): void {
  if (subscribers > 0) return;
  if (tickInterval != null) {
    clearInterval(tickInterval);
    tickInterval = null;
  }
  if (unlisten != null) {
    try {
      unlisten();
    } catch {
      // ignore
    }
    unlisten = null;
  }
  currentLevel = 0;
}

/**
 * Subscribe to the synthesised audio level. The `active` flag lets a
 * caller opt out of subscribing when it has its own level source — this
 * keeps the `transcript:partial` listener off the hot path for anyone
 * who doesn't need it.
 */
export function useWaveformLevel(active = true): number {
  const [level, setLevel] = useState(active ? currentLevel : 0);

  useEffect(() => {
    if (!active) {
      setLevel(0);
      return;
    }
    subscribers += 1;
    ensureSubscribed();
    const fn = (v: number) => setLevel(v);
    listeners.add(fn);
    return () => {
      listeners.delete(fn);
      subscribers = Math.max(0, subscribers - 1);
      teardownIfIdle();
    };
  }, [active]);

  return level;
}
