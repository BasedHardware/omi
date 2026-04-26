import { useCallback, useEffect, useRef, useState } from "react";

export type ShortcutKey = string; // "Cmd","Shift","Space","A",…

interface Options {
  /** Modifier-only chords are valid (e.g. push-to-talk = "Option"). When
   * false, the captured chord must contain at least one non-modifier key. */
  allowModifierOnly?: boolean;
  /** When true, the hook detaches its keyboard listeners. Used after commit
   * so later keystrokes (in other inputs, or the next step) can't overwrite
   * the displayed chord. */
  disabled?: boolean;
}

const MODIFIERS = new Set(["Cmd", "Win", "Ctrl", "Shift", "Option", "Alt", "Right Option", "Fn"]);
const IS_MAC = typeof navigator !== "undefined" && /mac/i.test(navigator.platform);

/** Captures a keyboard chord while the Nooto webview is focused. Uses
 * browser `keydown`/`keyup`, not a global event listener — the onboarding
 * flow runs in our own window so local capture is sufficient and avoids
 * rdev's macOS permissions / crash pitfalls. */
export function useShortcutCapture(opts: Options = {}) {
  const { allowModifierOnly = false, disabled = false } = opts;
  const [held, setHeld] = useState<ShortcutKey[]>([]);
  const [captured, setCaptured] = useState<ShortcutKey[] | null>(null);
  const heldRef = useRef<Set<ShortcutKey>>(new Set());
  // Peak of the held set across the current gesture. Needed because the
  // "commit on final release" path reads the set AFTER a key has been
  // removed — without this, Cmd+Shift released one-by-one would commit "Cmd"
  // instead of "Cmd+Shift".
  const peakRef = useRef<Set<ShortcutKey>>(new Set());

  const reset = useCallback(() => {
    heldRef.current.clear();
    peakRef.current.clear();
    setHeld([]);
    setCaptured(null);
  }, []);

  useEffect(() => {
    if (disabled) return;

    const handleDown = (e: KeyboardEvent) => {
      e.preventDefault();
      if (e.repeat) return;
      const label = normalizeFromEvent(e);
      if (!label) return;

      const set = heldRef.current;

      if (MODIFIERS.has(label)) {
        set.add(label);
        peakRef.current.add(label);
        setHeld(orderChord(Array.from(set)));
        return;
      }

      // Non-modifier pressed — snapshot the chord from the event's modifier
      // flags directly. macOS webviews frequently drop the separate keydown
      // for modifiers when Cmd is held, so the tracked `set` can be empty
      // even though the user IS holding Cmd. The event itself always carries
      // the correct metaKey/ctrlKey/altKey/shiftKey state.
      const chord: ShortcutKey[] = [];
      if (e.metaKey) chord.push(IS_MAC ? "Cmd" : "Win");
      if (e.ctrlKey) chord.push("Ctrl");
      if (e.altKey) chord.push(IS_MAC ? "Option" : "Alt");
      if (e.shiftKey) chord.push("Shift");
      chord.push(label);

      set.clear();
      peakRef.current.clear();
      for (const k of chord) {
        set.add(k);
        peakRef.current.add(k);
      }
      const ordered = orderChord(chord);
      setHeld(ordered);
      setCaptured(ordered);
    };

    const handleUp = (e: KeyboardEvent) => {
      e.preventDefault();
      const label = normalizeFromEvent(e);
      if (!label) return;
      const set = heldRef.current;
      set.delete(label);
      if (set.size === 0) {
        setHeld([]);
        if (allowModifierOnly && peakRef.current.size > 0) {
          const peakChord = orderChord(Array.from(peakRef.current));
          setCaptured(peakChord);
        }
        peakRef.current.clear();
      } else {
        setHeld(orderChord(Array.from(set)));
      }
    };

    const handleBlur = () => {
      heldRef.current.clear();
      peakRef.current.clear();
      setHeld([]);
    };

    window.addEventListener("keydown", handleDown, true);
    window.addEventListener("keyup", handleUp, true);
    window.addEventListener("blur", handleBlur);
    return () => {
      window.removeEventListener("keydown", handleDown, true);
      window.removeEventListener("keyup", handleUp, true);
      window.removeEventListener("blur", handleBlur);
    };
  }, [allowModifierOnly, disabled]);

  return { held, captured, reset };
}

function normalizeFromEvent(e: KeyboardEvent): ShortcutKey | null {
  // `event.code` is layout-independent ("KeyA" even on AZERTY) — the right
  // signal for a shortcut. Modifiers are reported via `event.key` since
  // `code` distinguishes left/right variants we don't care about.
  const code = e.code;
  const key = e.key;

  if (key === "Meta") return IS_MAC ? "Cmd" : "Win";
  if (key === "Control") return "Ctrl";
  if (key === "Shift") return "Shift";
  if (key === "Alt") return IS_MAC ? "Option" : "Alt";
  if (key === "AltGraph") return "Right Option";

  if (code === "Space") return "Space";
  if (code === "Enter") return "Return";
  if (code === "Tab") return "Tab";
  if (code === "Escape") return "Esc";
  if (code === "Backspace") return "Backspace";
  if (code === "CapsLock") return "CapsLock";
  if (code === "ArrowUp") return "↑";
  if (code === "ArrowDown") return "↓";
  if (code === "ArrowLeft") return "←";
  if (code === "ArrowRight") return "→";

  if (/^F\d{1,2}$/.test(code)) return code;
  const letter = code.match(/^Key([A-Z])$/)?.[1];
  if (letter) return letter;
  const digit = code.match(/^Digit(\d)$/)?.[1];
  if (digit) return digit;

  return null;
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
