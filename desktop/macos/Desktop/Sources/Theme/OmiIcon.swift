import AppKit
import SwiftUI

/// The deliberately small Lucide subset used by the day-zero dashboard.
/// Sidebar and Settings icons remain SF Symbols in this pass.
package enum OmiIconName: String, CaseIterable {
  case messageCircle = "LucideMessageCircle"
  case listChecks = "LucideListChecks"
  case brain = "LucideBrain"
  case images = "LucideImages"
  case paperclip = "LucidePaperclip"
  case arrowUp = "LucideArrowUp"
  case sparkles = "LucideSparkles"
  case arrowUpRight = "LucideArrowUpRight"
  case arrowRight = "LucideArrowRight"
  case home = "LucideHome"
  case sliders = "LucideSliders"
  case monitor = "LucideMonitor"
  case calendar = "LucideCalendar"
  case mail = "LucideMail"
  case link = "LucideLink"
  case square = "LucideSquare"

  package var hasBundledVector: Bool {
    resourceURL != nil
  }

  fileprivate var resourceURL: URL? {
    Bundle.module.url(
      forResource: resourceName,
      withExtension: resourceExtension,
      subdirectory: "OmiIcons.xcassets/\(rawValue).imageset"
    )
  }

  private var resourceExtension: String {
    switch self {
    case .arrowRight, .home, .sliders, .monitor, .calendar, .mail:
      return "svg"
    default:
      return "pdf"
    }
  }

  private var resourceName: String {
    switch self {
    case .messageCircle: return "lucide-message-circle"
    case .listChecks: return "lucide-list-checks"
    case .brain: return "lucide-brain"
    case .images: return "lucide-images"
    case .paperclip: return "lucide-paperclip"
    case .arrowUp: return "lucide-arrow-up"
    case .sparkles: return "lucide-sparkles"
    case .arrowUpRight: return "lucide-arrow-up-right"
    case .arrowRight: return "lucide-arrow-right"
    case .home: return "lucide-home"
    case .sliders: return "lucide-sliders"
    case .monitor: return "lucide-monitor"
    case .calendar: return "lucide-calendar"
    case .mail: return "lucide-mail"
    case .link: return "lucide-link"
    case .square: return "lucide-square"
    }
  }
}

/// Resolution-independent dashboard icon with explicit accessibility behavior.
/// Pass a label for a standalone icon; omit it when the containing button owns
/// the accessible name.
package struct OmiIcon: View {
  private let name: OmiIconName
  private let accessibilityLabel: String?

  package init(_ name: OmiIconName, accessibilityLabel: String? = nil) {
    self.name = name
    self.accessibilityLabel = accessibilityLabel
  }

  @ViewBuilder
  package var body: some View {
    if let accessibilityLabel {
      icon.accessibilityLabel(accessibilityLabel)
    } else {
      icon.accessibilityHidden(true)
    }
  }

  private var icon: some View {
    Image(nsImage: OmiIconAssetStore.image(for: name))
      .renderingMode(.template)
      .resizable()
      .scaledToFit()
  }
}

private enum OmiIconAssetStore {
  private static let images: [OmiIconName: NSImage] = {
    var loaded: [OmiIconName: NSImage] = [:]
    for name in OmiIconName.allCases {
      guard let url = name.resourceURL, let image = NSImage(contentsOf: url) else { continue }
      image.isTemplate = true
      loaded[name] = image
    }
    return loaded
  }()

  static func image(for name: OmiIconName) -> NSImage {
    images[name] ?? NSImage(systemSymbolName: "questionmark", accessibilityDescription: nil) ?? NSImage()
  }
}
