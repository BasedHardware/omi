//
//  ActivityBackButton.swift — the way back from a page the Brain chip row opened.
//
//  The chip row is a one-way door: pressing `Memories` leaves Brain, and the row goes with it,
//  because the row lives on Brain's panel. The top-bar `Brain` pill does come back, but a pill
//  in the window's chrome is a different gesture from the control that brought you here — you have
//  to know the pill is the answer, and nothing on the page says so.
//
//  So the page you land on says it. One control, leading edge, naming where it goes rather than a
//  bare chevron, matching the `‹ Back` affordance the conversation detail already uses.
//
//  Brand: `Ink` semantics only (INV-UI-1).
//

import OmiTheme
import SwiftUI

/// A back control that returns to the Brain spine.
struct ActivityBackButton: View {
  let action: () -> Void

  @State private var isHovering = false

  var body: some View {
    Button(action: action) {
      HStack(spacing: 5) {
        Image(systemName: "chevron.left")
          .scaledFont(size: OmiType.micro, weight: .semibold)
        Text("Brain")
          .scaledFont(size: OmiType.caption, weight: .semibold)
      }
      .foregroundStyle(GlassShell.controlLabel(isProminent: isHovering))
      .padding(.horizontal, 12)
      .frame(height: QueryShellLayout.chipHeight + 2)
      .glassChip(isActive: false)
    }
    .buttonStyle(.plain)
    .onHover { isHovering = $0 }
    .help("Back to Brain")
    .accessibilityLabel("Back to Brain")
    .accessibilityIdentifier("activity-back-button")
  }
}
