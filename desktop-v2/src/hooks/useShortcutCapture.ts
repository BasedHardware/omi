import { useCallback, useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

export type ShortcutKey = string; // normalized label from Rust ("Cmd","Shift",…)

interface ShortcutKeyEvent {
  kind: "press" | "release";
  label: ShortcutKey;
  raw: string;
}

interface Options {
  /** Modifier-only chords are valid (e.g. push-to-talk = "Option"). When
   * false, the captured chord must contain at least one non-modifier key. */
  allowModifierOnly?: boolean;
  /** Called once a stable chord is captured (all keys held simultaneously
   * after at least one key is released, OR a non-modifier was pressed while
   * modifiers were held). Caller decides what to do with it. */
  onCaptured?: (chord: ShortcutKey[]) => void;
}

const MODIFIERS = new Set(["Cmd", "Win", "Ctrl", "Shift", "Option", "Alt", "Right Option", "Fn"]);

/** Captures a global keyboard chord during onboarding. Arms the Rust
 * shortcut-capture listener on mount, disarms on unmount. Returns the
 * currently-held keys (live) and the last captured chord (stable). */
export function useShortcutCapture(opts: Options = {}) {
  const { allowModifierOnly = false, onCaptured } = opts;
  const [held, setHeld] = useState<ShortcutKey[]>([]);
  const [captured, setCaptured] = useState<ShortcutKey[] | null>(null);
  const heldRef = useRef<Set<ShortcutKey>>(new Set());
  const onCapturedRef = useRef(onCaptured);
  onCapturedRef.current = onCaptured;

  const reset = useCallback(() => {
    heldRef.current.clear();
    setHeld([]);
    setCaptured(null);
  }, []);

  useEffect(() => {
    let unlisten: UnlistenFn | null = null;
    let cancelled = false;

    (async () => {
      try {
        await invoke("start_shortcut_capture");
      } catch (err) {
        console.warn("[shortcut_capture] arm failed:", err);
      }
      try {
        unlisten = await listen<ShortcutKeyEvent>(
          "onboarding:shortcut_key",
          (e) => {
            if (cancelled) return;
            const { kind, label } = e.payload;
            const set = heldRef.current;

            if (kind === "press") {
              set.add(label);
              const arr = orderChord(Array.from(set));
              setHeld(arr);

              // Capture as soon as a non-modifier joins held modifiers — that's
              // a complete chord like Cmd+Shift+Space. For modifier-only mode,
              // wait for release to capture (so users can pick "Option").
              if (!MODIFIERS.has(label) && arr.length >= 1) {
                setCaptured(arr);
                onCapturedRef.current?.(arr);
              }
            } else {
              // release: commit the just-released chord when the user lets go
              // of every key. In modifier-only mode, the chord IS the set of
              // modifiers that were held. We always overwrite the previous
              // captured chord — the user re-pressing keys to "change" it
              // means the new combination wins.
              const wasHeld = orderChord(Array.from(set));
              set.delete(label);
              if (set.size === 0) {
                setHeld([]);
                if (allowModifierOnly && wasHeld.length > 0) {
                  setCaptured(wasHeld);
                  onCapturedRef.current?.(wasHeld);
                }
              } else {
                setHeld(orderChord(Array.from(set)));
              }
            }
          },
        );
      } catch (err) {
        console.warn("[shortcut_capture] listen failed:", err);
      }
    })();

    return () => {
      cancelled = true;
      if (unlisten) unlisten();
      invoke("stop_shortcut_capture").catch(() => {});
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allowModifierOnly]);

  return { held, captured, reset };
}

/** Sort chord so modifiers come first (Cmd → Ctrl → Option → Shift → key). */
function orderChord(keys: ShortcutKey[]): ShortcutKey[] {
  const order = ["Cmd", "Win", "Ctrl", "Option", "Alt", "Right Option", "Shift", "Fn"];
  return [...keys].sort((a, b) => {
    const ai = order.indexOf(a);
    const bi = order.indexOf(b);
    if (ai === -1 && bi === -1) return a.localeCompare(b);
    if (ai === -1) return 1;
    if (bi === -1) return -1;
    return ai - bi;
  });
}
