import { useEffect, useState } from "react";
import { listen } from "@tauri-apps/api/event";
import { Persona, type PersonaState } from "@/components/ai-elements/persona";

/**
 * Live dictation HUD — just the Persona orb. Shows while the user is
 * holding AltGr so they have a visual cue Nooto is listening. The
 * transcript is routed to the focused app via paste and recorded to
 * the Whispr history page for review.
 *
 * Lifecycle is driven from the main window's `usePttSession` hook:
 *   - On ptt:start the hook calls `show_whispr_hud` and the window appears.
 *   - On ptt:stop the hook calls `hide_whispr_hud` and the window hides.
 */
export function WhisprLiveHUD() {
  const [active, setActive] = useState(false);

  useEffect(() => {
    const unlisteners: Array<() => void> = [];

    listen("ptt:start", () => setActive(true)).then((u) => unlisteners.push(u));
    listen("ptt:stop", () => setActive(false)).then((u) => unlisteners.push(u));

    return () => unlisteners.forEach((u) => u());
  }, []);

  const personaState: PersonaState = active ? "listening" : "idle";

  return (
    <div className="whispr-hud">
      <div className="whispr-hud-inner">
        <div className="whispr-hud-orb" aria-hidden>
          <Persona
            variant="opal"
            state={personaState}
            className="whispr-persona"
          />
        </div>
      </div>
    </div>
  );
}
