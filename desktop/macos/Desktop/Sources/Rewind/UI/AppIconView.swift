import SwiftUI
import AppKit
import OmiTheme

/// View that displays the icon for an application by name
struct AppIconView: View {
    let appName: String
    let size: CGFloat

    @State private var icon: NSImage? = nil

    var body: some View {
        Group {
            if let icon = icon {
                Image(nsImage: icon)
                    .resizable()
                    .aspectRatio(contentMode: .fit)
                    .frame(width: size, height: size)
            } else {
                // Fallback: letter monogram — the app isn't installed (or isn't
                // findable), so give the row a distinct mark instead of a generic
                // placeholder.
                RoundedRectangle(cornerRadius: size * 0.22, style: .continuous)
                    .fill(OmiColors.backgroundQuaternary)
                    .frame(width: size, height: size)
                    .overlay(
                        Text(String(appName.prefix(1)).uppercased())
                            .font(.system(size: size * 0.55, weight: .semibold, design: .rounded))
                            .foregroundColor(OmiColors.textSecondary)
                    )
            }
        }
        .task {
            icon = await AppIconCache.shared.getIcon(for: appName, size: size)
        }
    }
}

/// Cache for app icons to avoid repeated lookups
/// Uses NSCache for automatic memory management under pressure
actor AppIconCache {
    static let shared = AppIconCache()

    private let cache: NSCache<NSString, NSImage> = {
        let cache = NSCache<NSString, NSImage>()
        cache.countLimit = 100  // Max 100 app icons cached
        cache.totalCostLimit = 50 * 1024 * 1024  // 50MB limit
        return cache
    }()

    func getIcon(for appName: String, size: CGFloat) async -> NSImage? {
        let cacheKey = appName as NSString

        // Check cache first
        if let cached = cache.object(forKey: cacheKey) {
            return cached
        }

        // Try to find the app and get its icon
        let icon = await loadIcon(for: appName)

        if let icon = icon {
            // Resize to requested size
            let resized = resizeIcon(icon, to: CGFloat(size * 2)) // 2x for retina
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

    private func loadIcon(for appName: String) async -> NSImage? {
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
            NSHomeDirectory() + "/Applications"
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
                    if name.lowercased() == appName.lowercased() ||
                       name.lowercased().contains(appName.lowercased()) {
                        let appPath = "\(basePath)/\(item)"
                        return workspace.icon(forFile: appPath)
                    }
                }
            }
        }

        // Try getting icon from running applications
        for app in workspace.runningApplications {
            if let name = app.localizedName,
               name.lowercased() == appName.lowercased() ||
               name.lowercased().contains(appName.lowercased()),
               let bundleURL = app.bundleURL {
                return workspace.icon(forFile: bundleURL.path)
            }
        }

        // Try using bundle identifier patterns
        let possibleBundleIds = [
            "com.apple.\(appName.lowercased())",
            "com.apple.\(appName.lowercased().replacingOccurrences(of: " ", with: ""))"
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
    .background(OmiColors.backgroundPrimary)
}
#endif
