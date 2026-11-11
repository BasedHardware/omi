// The Hub's base layer — the lit "stage" the Home content sits on.
//
// Ported 1:1 from the Mac app (DashboardPage.swift HomeCanvasBackground): a solid
// paper fill, three radial glows (one white key light from the top, two violet
// stage glows), a radial vignette that darkens the frame edges, and a faint linear
// wash across the bottom. Six layers, back to front, in the same order.
//
// It is STATIC on Mac — no animation, no state, and it does NOT react to the home
// stage mode (hub/chat/connect), hover, or focus. It renders identically in every
// mode, so it is a pure presentational component with no props. Keep it that way:
// this element is full-bleed and always mounted, so anything animated here costs
// paint on every frame of every Home interaction.
//
// The violet is HomePalette.stageGlow (#7A4DF2) and is intentional — the Windows
// app ports the Mac purple as-is under the INV-UI-1 Windows carve-out (ruling B).
//
// Mac's radial radii are in POINTS, measured against its stage; CSS radial-gradient
// takes a length, so the radii below are those point values as px. They are NOT
// scaled to the viewport — that is faithful: on Mac these are fixed-size pools of
// light on a stage that grows around them, not gradients that stretch with it.

export function HomeCanvasBackground(): React.JSX.Element {
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 -z-10 bg-home-paper"
      style={{
        // CSS paints background-image layers FIRST-ON-TOP, the opposite of a
        // SwiftUI ZStack, so the Mac's back-to-front order is reversed here: the
        // bottom wash (Mac's topmost layer) is listed first. The paper fill is the
        // element's background-color (bg-home-paper), i.e. the bottom-most layer.
        backgroundImage: [
          // 6. bottom wash: transparent to 50%, then a whisper of glow + white.
          `linear-gradient(to bottom,
             transparent 50%,
             rgb(var(--home-stage-glow-rgb) / 0.026) 78%,
             rgb(255 255 255 / 0.014) 90%,
             transparent 100%)`,
          // 5. vignette: clear core, then paper, then black at the frame edges.
          // Mac blends its 3 stops across 470->900; the middle stop lands halfway.
          `radial-gradient(circle 900px at 50% 48%,
             transparent 470px,
             rgb(var(--home-paper-rgb) / 0.88) 685px,
             rgb(0 0 0 / 0.62) 900px)`,
          // 4. stage glow, lower-left.
          `radial-gradient(circle 560px at 20% 78%,
             rgb(var(--home-stage-glow-rgb) / 0.04) 100px,
             transparent 560px)`,
          // 3. stage glow, upper — the brightest of the three.
          `radial-gradient(circle 680px at 48% 24%,
             rgb(var(--home-stage-glow-rgb) / 0.075) 0px,
             transparent 680px)`,
          // 2. white key light from the top.
          `radial-gradient(circle 560px at 50% 16%,
             rgb(255 255 255 / 0.04) 0px,
             transparent 560px)`
        ].join(', ')
      }}
    />
  )
}
