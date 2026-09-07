import Foundation

/// Lifecycle support for app-owned staged screen frames (recent-frames menu
/// picks and the first-real-app card handoff). Extracted from the provider
/// body to respect the agent-runtime convergence ratchet; ownership lives
/// with `ChatAttachment.appOwnedFileURL`.
@MainActor
enum RecentFrameStagingLifecycle {
  /// Deletes the temp files behind app-owned attachments (staged screen
  /// frames) without touching user-picked files.
  static func discardAppOwnedFiles(_ attachments: [ChatAttachment]) {
    for url in attachments.compactMap(\.appOwnedFileURL) {
      try? FileManager.default.removeItem(at: url)
    }
  }

  /// Deletes the temp file behind one app-owned attachment, by id.
  static func discardAppOwnedFile(id: String, in attachments: [ChatAttachment]) {
    if let url = attachments.first(where: { $0.id == id })?.appOwnedFileURL {
      try? FileManager.default.removeItem(at: url)
    }
  }
}

/// Counts in-flight async frame stagings (store decode → temp JPEG →
/// `addAttachments`); a send holds the gate open only until they land.
@MainActor
final class RecentFrameStagingGate {
  private var inFlight = 0

  func begin() { inFlight += 1 }

  /// Must be balanced on every exit path of a `begin()` — use `defer`.
  func end() { inFlight = max(0, inFlight - 1) }

  /// Waits — bounded — for in-flight stagings to land. A decode that never
  /// returns must not hang the send: after the bound the send proceeds with
  /// whatever has landed, exactly as it would have without the wait.
  func settle(timeoutNanoseconds: UInt64 = 2_000_000_000) async {
    let deadline = DispatchTime.now().uptimeNanoseconds + timeoutNanoseconds
    while inFlight > 0 {
      if DispatchTime.now().uptimeNanoseconds > deadline { return }
      try? await Task.sleep(nanoseconds: 20_000_000)
    }
  }
}

extension ChatProvider {
  /// Marks the start of an asynchronous frame staging (see
  /// `QueryShellHome.stageRecentFrame`). Must be balanced by
  /// `endRecentFrameStaging` on every exit path.
  func beginRecentFrameStaging() {
    recentFrameStagingGate.begin()
  }

  func endRecentFrameStaging() {
    recentFrameStagingGate.end()
  }
}
