import { CompanionOrb } from "@/components/companion/CompanionOrb";

/**
 * Live dictation HUD — just the always-animating opal Rive orb. Shows while
 * the user is holding AltGr so they have a visual cue Nooto is listening.
 * The transcript is routed to the focused app via paste and recorded to
 * the Whispr history page for review.
 *
 * Renders on a fully-transparent window (no opaque pill behind the orb).
 * The orb itself is the only visible affordance — same look as the new
 * Companion buddy. Lifecycle is driven from the main window's `usePttSession`:
 *   - On ptt:start the hook calls `show_whispr_hud` and the window appears.
 *   - On ptt:stop the hook calls `hide_whispr_hud` and the window hides.
 *
 * The orb runs a continuous "thinking" animation regardless of PTT state —
 * the show/hide of the window itself is the listening signal.
 */
export function WhisprLiveHUD() {
  return (
    <div className="whispr-hud">
      <div className="whispr-hud-inner">
        <div className="whispr-hud-orb" aria-hidden>
          <CompanionOrb size={64} />
        </div>
      </div>
    </div>
  );
}
