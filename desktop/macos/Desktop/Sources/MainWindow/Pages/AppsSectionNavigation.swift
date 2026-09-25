//
//  AppsSectionNavigation.swift — the Apps page's section chips.
//
//  Apps carries two catalogs that are not apps: MCP servers and skills. They used to be stacked
//  under Imports and Exports on one scroll, which left the page's search field and filters with no
//  single subject.
//
//  The chips follow Brain's rule (see `ActivityDestinationChip`): every chip here switches the
//  page, none narrows a list. `Imports` and `Exports` therefore stay in the Kind menu beside them,
//  which is a filter, rather than being promoted to chips they would not behave like.
//

import OmiTheme
import SwiftUI

/// One chip in the Apps row. Every case is a section; none is a filter.
enum AppsSectionDestination: Int, CaseIterable, Identifiable {
  /// Raw values persist in `AppStorage`, so this order is storage identity: append only.
  case apps
  case mcp
  case skills

  static let storageKey = "appsSectionDestination"

  var id: Int { rawValue }

  var title: String {
    switch self {
    case .apps: return "Apps"
    case .mcp: return "MCP"
    case .skills: return "Skills"
    }
  }

  /// Stable suffix for accessibility identifiers, so selectors do not ride on raw values.
  var automationID: String {
    switch self {
    case .apps: return "apps"
    case .mcp: return "mcp"
    case .skills: return "skills"
    }
  }
}

/// The Apps section chips, sized to sit in the page toolbar's trailing actions slot.
struct AppsSectionNavigation: View {
  let selected: AppsSectionDestination
  let onSelect: (AppsSectionDestination) -> Void

  var body: some View {
    HStack(spacing: QueryShellLayout.chipSpacing) {
      ForEach(AppsSectionDestination.allCases) { section in
        AppsSectionChip(
          title: section.title,
          isActive: section == selected,
          action: { onSelect(section) }
        )
        .accessibilityIdentifier("apps-section-\(section.automationID)")
      }
    }
    .accessibilityElement(children: .contain)
    .accessibilityIdentifier("apps-section-navigation")
  }
}

/// Visually identical to Brain's section chip; kept local so the toolbar row can own its own
/// height without Brain's page layout having to accommodate a second caller.
private struct AppsSectionChip: View {
  let title: String
  let isActive: Bool
  let action: () -> Void

  @State private var isHovering = false

  var body: some View {
    Button(action: action) {
      Text(title)
        .scaledFont(size: OmiType.caption, weight: isActive ? .semibold : .regular)
        .foregroundStyle(GlassShell.controlLabel(isProminent: isActive || isHovering))
        .padding(.horizontal, 12)
        .frame(height: QueryShellLayout.chipHeight)
        .glassChip(isActive: isActive)
    }
    .buttonStyle(.plain)
    .contentShape(Capsule(style: .continuous))
    .onHover { isHovering = $0 }
    .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.press)), value: isActive)
    .accessibilityAddTraits(isActive ? .isSelected : [])
  }
}
