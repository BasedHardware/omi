import AppKit
import SwiftUI

/// Status-tinted provider logo (Hermes, OpenClaw, …) used as the identity
/// mark for subagents in the unified floating chat surface.
struct AgentProviderLogoMark: View {
  let provider: AgentHarnessMode?
  let statusColor: Color
  let size: CGFloat

  var body: some View {
    Group {
      if let logo = Self.logo(for: provider) {
        Image(nsImage: logo)
          .resizable()
          .renderingMode(.template)
          .interpolation(.high)
          .aspectRatio(contentMode: .fit)
          .foregroundStyle(statusColor)
      } else if provider != nil {
        // Catch-all for provider agents without a dedicated logo: a flat,
        // status-tinted robot. The emoji glyph is used purely as an alpha
        // mask so it renders as a single flat color like the other marks.
        statusColor
          .mask(
            Text("🤖")
              .font(.system(size: size))
              .frame(width: size, height: size)
          )
      } else {
        Circle().fill(statusColor)
      }
    }
    .frame(width: size, height: size)
  }

  private static func logo(for provider: AgentHarnessMode?) -> NSImage? {
    switch provider {
    case .hermes:
      return hermesLogo
    case .openclaw:
      return openClawLogo
    default:
      return nil
    }
  }

  private static let hermesLogo = load("hermes_logo_flat")
  private static let openClawLogo = load("openclaw_logo_flat")

  private static func load(_ name: String) -> NSImage? {
    guard let url = Bundle.resourceBundle.url(forResource: name, withExtension: "png") else {
      return nil
    }
    return NSImage(contentsOf: url)
  }
}
