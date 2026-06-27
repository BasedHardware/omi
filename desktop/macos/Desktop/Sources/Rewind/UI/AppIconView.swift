import SwiftUI
import AppKit

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
                // Fallback icon
                Image(systemName: "app.fill")
                    .resizable()
                    .aspectRatio(contentMode: .fit)
                    .frame(width: size, height: size)
                    .foregroundColor(OmiColors.textTertiary)
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

    private func loadIcon(for appName: String) async -> NSImage? {
        // Try to find the app by name
        let workspace = NSWorkspace.shared

        // Common app locations
        let searchPaths = [
            "/Applications",
            "/System/Applications",
            "/System/Applications/Utilities",
            "/Applications/Utilities",
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

#Preview {
    HStack(spacing: 16) {
        AppIconView(appName: "Safari", size: 32)
        AppIconView(appName: "Xcode", size: 32)
        AppIconView(appName: "Finder", size: 32)
        AppIconView(appName: "Terminal", size: 32)
    }
    .padding()
    .background(OmiColors.backgroundPrimary)
}
