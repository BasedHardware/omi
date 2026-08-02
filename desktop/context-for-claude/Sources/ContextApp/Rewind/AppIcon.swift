import AppKit
import SwiftUI

/// Resolves an application's icon for the badges pinned along the timeline track.
///
/// Resolution is by **bundle identifier first**, which is the change from the implementation this
/// was ported from. That one probes seven directories for `<appName>.app`, then re-walks them
/// case-insensitively accepting any name that merely *contains* the app name, then scans running
/// applications, then fabricates bundle ids by lowercasing the display name and prefixing
/// `com.apple.`. Each step is a guess that can succeed with the wrong app — a substring match on
/// "Mail" finds "MailMate" — and the whole chain still fails on any app outside those directories.
///
/// `NSWorkspace.urlForApplication(withBundleIdentifier:)` asks LaunchServices, which knows where
/// every registered app on the machine actually is. It answers exactly or not at all, so a hit is
/// never the wrong app. Capture now records the identifier (`frames.bundleId`), and
/// `RewindQueries.bundleIdsByApp` carries it back over rows that predate the column.
///
/// The name fallback survives for apps that have not been seen since the column was added, but it is
/// deliberately narrower than theirs: **exact** basename match in the standard locations only. No
/// substring matching and no invented identifiers — a missing icon is a monogram, which is honest,
/// where a confidently wrong icon is a lie about what the user was doing.
@MainActor
final class AppIconCache {
    static let shared = AppIconCache()

    /// Icons are small and there are only ever as many as the user has apps.
    private let cache = NSCache<NSString, NSImage>()
    /// Names already looked up and not found, so a monogram costs one filesystem probe rather than
    /// one per redraw of the track.
    private var misses: Set<String> = []

    /// Bundle ids learned from the database, keyed by app name. Set once when a day loads.
    private var bundleIdsByApp: [String: String] = [:]

    /// The only directories the name fallback looks in. `/System/Library/CoreServices` is here
    /// because Finder and several system agents live there rather than in an Applications folder.
    private static let searchDirectories = [
        "/Applications",
        "/System/Applications",
        "/System/Applications/Utilities",
        "/Applications/Utilities",
        "/System/Library/CoreServices",
        NSHomeDirectory() + "/Applications",
    ]

    func setBundleIds(_ map: [String: String]) {
        guard map != bundleIdsByApp else { return }
        bundleIdsByApp = map
        // A name that missed before may now resolve through a newly learned identifier.
        misses.removeAll()
    }

    /// The icon for an app, or nil when nothing on this machine matches it.
    func icon(appName: String, bundleId: String? = nil) -> NSImage? {
        let key = appName as NSString
        if let cached = cache.object(forKey: key) { return cached }
        if misses.contains(appName) { return nil }

        guard let url = resolveURL(appName: appName, bundleId: bundleId) else {
            misses.insert(appName)
            return nil
        }
        let icon = NSWorkspace.shared.icon(forFile: url.path)
        cache.setObject(icon, forKey: key)
        return icon
    }

    /// Identifier from the row, then identifier learned for that app name, then an exact-name probe.
    private func resolveURL(appName: String, bundleId: String?) -> URL? {
        for identifier in [bundleId, bundleIdsByApp[appName]].compactMap({ $0 }) {
            if let url = NSWorkspace.shared.urlForApplication(withBundleIdentifier: identifier) {
                return url
            }
        }
        let fileManager = FileManager.default
        for directory in Self.searchDirectories {
            let candidate = "\(directory)/\(appName).app"
            if fileManager.fileExists(atPath: candidate) {
                return URL(fileURLWithPath: candidate)
            }
        }
        return nil
    }
}

/// One app icon, or a monogram when the app cannot be found on this machine.
///
/// The monogram is a real fallback rather than a generic placeholder: a track badge exists to be
/// recognised at 16 pt, and a row of identical grey document icons carries less than a row of
/// distinct letters. It is drawn in the app's own track colour so the badge still agrees with the
/// segment it sits on.
struct RewindAppIcon: View {
    let appName: String
    let bundleId: String?
    let size: CGFloat

    @State private var icon: NSImage?

    var body: some View {
        Group {
            if let icon {
                Image(nsImage: icon)
                    .resizable()
                    .aspectRatio(contentMode: .fit)
            } else {
                Circle()
                    .fill(RewindPalette.color(forApp: appName))
                    .overlay(
                        Text(monogram)
                            .font(.system(size: size * 0.5, weight: .semibold, design: .rounded))
                            // Fixed white on a mid-brightness colour chip, in both appearances:
                            // the chip is not a semantic surface, so a label colour that inverts
                            // would go invisible against it in one of the two.
                            .foregroundStyle(.white))
            }
        }
        .frame(width: size, height: size)
        .task(id: appName) {
            icon = AppIconCache.shared.icon(appName: appName, bundleId: bundleId)
        }
        .accessibilityLabel(Text(appName))
    }

    /// First character, uppercased. Grapheme-cluster safe, so an emoji-named app gets its emoji
    /// rather than half a scalar.
    private var monogram: String {
        guard let first = appName.first else { return "?" }
        return String(first).uppercased()
    }
}
