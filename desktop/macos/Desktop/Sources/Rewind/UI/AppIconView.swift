@preconcurrency import AppKit
import OmiTheme
import SwiftUI

/// View that displays the icon for an application by name
struct AppIconView: View {
  let appName: String
  let size: CGFloat

  @State private var icon: NSImage? = nil

  /// The first character of the app's name, folded to uppercase. Empty for an empty name, which
  /// still draws the disc — a coloured blank is a mark; a hole in the row is not.
  private var monogram: String {
    String(appName.trimmingCharacters(in: .whitespacesAndNewlines).prefix(1)).uppercased()
  }

  var body: some View {
    Group {
      if let icon = icon {
        Image(nsImage: icon)
          // Stated, never inferred. A resized `NSImage` loses nothing about its own artwork, but
          // SwiftUI's default rendering mode is decided by the *asset*, and an image built by
          // `resizeIcon` carries no asset metadata — so the default can flatten a real app icon to
          // a single-colour silhouette, which is a logo the user cannot recognise. `.original` says
          // the artwork ships as its author drew it. A genuine stencil (`isTemplate`, which a few
          // system agents ship) keeps `.template` and takes the surrounding label colour, because
          // that is what its author asked for.
          .renderingMode(icon.isTemplate ? .template : .original)
          .resizable()
          .aspectRatio(contentMode: .fit)
          .frame(width: size, height: size)
      } else {
        // Fallback: letter monogram on the app's own colour. The app isn't installed (or isn't
        // findable), so the mark has to carry the identity by itself — a neutral placeholder makes
        // every unresolvable app look like the same app. `RewindPalette` is the single source of
        // that colour, so this disc, the timeline badge behind it and any per-app accent all agree.
        Circle()
          .fill(RewindPalette.color(forApp: appName))
          .frame(width: size, height: size)
          .overlay(
            Text(monogram)
              .font(.system(size: size * 0.5, weight: .semibold, design: .rounded))
              // Fixed white on a mid-brightness colour chip, in both appearances: the chip is not a
              // semantic surface, so a label colour that inverts would go invisible against it in
              // one of the two. Every swatch the palette can emit clears 3:1 against white.
              .foregroundStyle(.white)
          )
      }
    }
    .task(id: appName) {
      icon = AppIconCache.shared.getIcon(for: appName, size: size)
    }
  }
}

/// Cache for app icons to avoid repeated lookups
/// Uses NSCache for automatic memory management under pressure
@MainActor
final class AppIconCache {
  static let shared = AppIconCache()

  private let cache: NSCache<NSString, NSImage> = {
    let cache = NSCache<NSString, NSImage>()
    cache.countLimit = 100  // Max 100 app icons cached
    cache.totalCostLimit = 50 * 1024 * 1024  // 50MB limit
    return cache
  }()

  func getIcon(for appName: String, size: CGFloat) -> NSImage? {
    // Keyed on the rendered size as well as the name. Rewind draws the same app at 14, 16, 18, 20
    // and 24 pt on one screen, and a name-only key served whichever size was requested first —
    // so a 24 pt timeline badge could be a 14 pt render upscaled, which is visibly soft.
    let cacheKey = "\(appName)@\(Int(size.rounded()))" as NSString

    // Check cache first
    if let cached = cache.object(forKey: cacheKey) {
      return cached
    }

    // Try to find the app and get its icon
    let icon = loadIcon(for: appName)

    if let icon = icon {
      // Resize to requested size
      let resized = resizeIcon(icon, to: CGFloat(size * 2))  // 2x for retina
      cache.setObject(resized, forKey: cacheKey)
      return resized
    }

    return nil
  }

  /// System apps that were renamed across macOS versions — stored names may
  /// predate the rename, so resolve through the current name too.
  private static let renamedApps: [String: String] = [
    "System Preferences": "System Settings"
  ]

  private func loadIcon(for appName: String) -> NSImage? {
    // Try to find the app by name
    let workspace = NSWorkspace.shared
    let appName = Self.renamedApps[appName] ?? appName

    // Common app locations (CoreServices hosts Finder, Archive Utility, …)
    let searchPaths = [
      "/Applications",
      "/System/Applications",
      "/System/Applications/Utilities",
      "/Applications/Utilities",
      "/System/Library/CoreServices",
      "/System/Library/CoreServices/Applications",
      NSHomeDirectory() + "/Applications",
    ]

    let fileManager = FileManager.default

    // Try exact match first
    for basePath in searchPaths {
      let appPath = "\(basePath)/\(appName).app"
      if fileManager.fileExists(atPath: appPath) {
        return workspace.icon(forFile: appPath)
      }
    }

    // Try case-insensitive search
    for basePath in searchPaths {
      if let contents = try? fileManager.contentsOfDirectory(atPath: basePath) {
        for item in contents where item.hasSuffix(".app") {
          let name = item.replacingOccurrences(of: ".app", with: "")
          if name.lowercased() == appName.lowercased() || name.lowercased().contains(appName.lowercased()) {
            let appPath = "\(basePath)/\(item)"
            return workspace.icon(forFile: appPath)
          }
        }
      }
    }

    // Try getting icon from running applications
    for app in workspace.runningApplications {
      if let name = app.localizedName,
        name.lowercased() == appName.lowercased() || name.lowercased().contains(appName.lowercased()),
        let bundleURL = app.bundleURL
      {
        return workspace.icon(forFile: bundleURL.path)
      }
    }

    // Try using bundle identifier patterns
    let possibleBundleIds = [
      "com.apple.\(appName.lowercased())",
      "com.apple.\(appName.lowercased().replacingOccurrences(of: " ", with: ""))",
    ]

    for bundleId in possibleBundleIds {
      if let path = workspace.urlForApplication(withBundleIdentifier: bundleId)?.path {
        return workspace.icon(forFile: path)
      }
    }

    return nil
  }

  private func resizeIcon(_ icon: NSImage, to size: CGFloat) -> NSImage {
    let newSize = NSSize(width: size, height: size)
    let newImage = NSImage(size: newSize)
    newImage.lockFocus()
    icon.draw(
      in: NSRect(origin: .zero, size: newSize),
      from: NSRect(origin: .zero, size: icon.size),
      operation: .copy,
      fraction: 1.0
    )
    newImage.unlockFocus()
    // Carried across explicitly. A stencil says so on the image, not on its pixels, and a freshly
    // constructed `NSImage` starts out saying no — which would silently make `AppIconView`'s
    // `.template` branch unreachable and draw a system agent's stencil as flat black artwork.
    newImage.isTemplate = icon.isTemplate
    return newImage
  }
}

#if canImport(PreviewsMacros)
  #Preview {
    HStack(spacing: OmiSpacing.lg) {
      AppIconView(appName: "Safari", size: 32)
      AppIconView(appName: "Xcode", size: 32)
      AppIconView(appName: "Finder", size: 32)
      AppIconView(appName: "Terminal", size: 32)
    }
    .padding()
    .background(Ink.surface)
  }
#endif
