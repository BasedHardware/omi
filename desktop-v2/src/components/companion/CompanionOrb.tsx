/**
 * CompanionOrb — the always-animating Rive "opal" orb for the buddy window.
 *
 * Uses `@rive-app/react-canvas` (Canvas2D) instead of `react-webgl2` because
 * Tauri transparent windows on macOS Sonoma+ disable hardware-accelerated GL
 * contexts — WebGL2 silently fails to paint there. The Canvas2D pipeline is
 * a few percent slower but renders cleanly on transparent surfaces, which is
 * what we need so the orb floats on the desktop without an opaque buddy box.
 *
 * Always pushes the "thinking" state-machine input to true so the orb has
 * continuous ambient motion regardless of the assistant's logical state. The
 * caller can override by passing `forceState` if they want the input to
 * follow companionStore (kept for future, unused today).
 */
import { useEffect } from "react";
import { useRive, useStateMachineInput } from "@rive-app/react-canvas";

const OPAL_SRC =
  "https://ejiidnob33g9ap1r.public.blob.vercel-storage.com/orb-1.2.riv";
const STATE_MACHINE = "default";

export function CompanionOrb({ size = 96 }: { size?: number }) {
  const { rive, RiveComponent } = useRive({
    src: OPAL_SRC,
    stateMachines: STATE_MACHINE,
    autoplay: true,
  });

  // Drive the "thinking" boolean to true so the orb keeps moving. Opal has
  // no data-binding model (hasModel: false in the existing Persona config),
  // so we just toggle the SM input and let Rive idle-loop on it.
  const thinking = useStateMachineInput(rive, STATE_MACHINE, "thinking");
  useEffect(() => {
    if (thinking) thinking.value = true;
  }, [thinking]);

  return (
    <RiveComponent
      style={{
        width: size,
        height: size,
        // Canvas Rive paints with a transparent background by default; no
        // extra CSS needed.
      }}
    />
  );
}
