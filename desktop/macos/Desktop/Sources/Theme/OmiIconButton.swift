import SwiftUI

/// A consistent circular icon button for toolbars/headers: neutral at rest, a
/// soft white wash on hover, a brighter fill when active. Matches the app's
/// chip / segmented-control language so every header control reads as one set.
package struct OmiIconButton: View {
  let systemName: String
  var isActive: Bool = false
  var help: String? = nil
  let action: () -> Void

  @State private var isHovering = false

  package init(
    systemName: String,
    isActive: Bool = false,
    help: String? = nil,
    action: @escaping () -> Void
  ) {
    self.systemName = systemName
    self.isActive = isActive
    self.help = help
    self.action = action
  }

  package var body: some View {
    Button(action: action) {
      Image(systemName: systemName)
        .scaledFont(size: OmiType.body, weight: .semibold)
        .foregroundColor(
          isActive || isHovering ? OmiColors.textPrimary : OmiColors.textSecondary
        )
        .frame(width: 34, height: 34)
        .background(
          Circle()
            .fill(
              isActive
                ? Color.white.opacity(0.12)
                : (isHovering ? Color.white.opacity(0.08) : Color.clear))
        )
        .contentShape(Circle())
    }
    .buttonStyle(.plain)
    .onHover { hovering in
      OmiMotion.withGated(.easeOut(duration: 0.12)) { isHovering = hovering }
    }
    .help(help ?? "")
  }
}
