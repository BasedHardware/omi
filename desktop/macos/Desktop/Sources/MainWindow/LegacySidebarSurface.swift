//
//  LegacySidebarSurface.swift — the one ground under the old Home sidebar slot.
//

import OmiTheme
import SwiftUI

/// Hosts the old Home navigation slot on its own piece of glass.
///
/// `ShellWindowChrome` leaves the top-level window transparent and `PageGlassLane` grounds only the
/// destination beside this slot. Keeping the surface here means the primary navigation and the
/// Settings menu share one owner for both their visible glass and their mouse-hit region.
struct LegacySidebarSurface<Content: View>: View {
  private let content: Content

  init(@ViewBuilder content: () -> Content) {
    self.content = content()
  }

  var body: some View {
    content
      .fixedSize(horizontal: true, vertical: false)
      .clipped()
      .inkGlassPanel(cornerRadius: 0, shadow: nil)
  }
}
