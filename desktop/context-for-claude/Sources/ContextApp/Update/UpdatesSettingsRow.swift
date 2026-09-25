import SwiftUI

/// The Updates row for Settings › General › About.
///
/// It replaces a row that showed the version and nothing else, and the note beside that row said why:
/// "This build has no auto-updater, so there is nothing here to check for one." That was the right
/// thing to ship at the time — `J7` rules out a control the user can operate that changes nothing,
/// and a greyed-out `Update Now` still advertises a feature that does not exist. The updater exists
/// now, so the button is real; and on a build where ``UpdatePolicy`` refused, the button is gone
/// again rather than disabled, and the subtitle says which kind of build this is. Same rule, applied
/// in both directions.
///
/// Nothing here names a version, a product or a changelog. Sparkle's own sheet does all of that from
/// the host bundle and the feed, which is exactly what keeps an update prompt for this app from
/// looking like an update prompt for Omi.
struct UpdatesSettingsRow: View {
    @ObservedObject var updater: ContextUpdater

    var body: some View {
        SettingsRow(
            icon: "arrow.triangle.2.circlepath",
            title: "Updates",
            subtitle: subtitle
        ) {
            if updater.refusal == nil {
                Button("Check Now") { updater.checkForUpdates() }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                    .disabled(!updater.canCheckForUpdates)
            }
        }
    }

    /// The version always, and after it whatever the last check or the refusal has to say. Two facts
    /// on one line because the row is one line: what you are running, and whether that is going to
    /// change on its own.
    private var subtitle: String {
        if let summary = updater.lastCheckSummary, !summary.isEmpty {
            return "\(updater.currentVersionDescription) — \(summary)"
        }
        return updater.currentVersionDescription
    }
}
