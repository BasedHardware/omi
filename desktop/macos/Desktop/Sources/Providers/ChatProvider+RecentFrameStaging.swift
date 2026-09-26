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

  /// Writes fresh bytes next to the other staged screens' files, for an
  /// attachment whose original file is about to be deleted (the failed turn's
  /// exit cleanup). Returns nil when the write fails; the caller then falls
  /// back to the attachment's in-memory bytes alone.
  nonisolated static func writeAppOwnedFile(data: Data, fileName: String) -> URL? {
    let directory =
      URL(fileURLWithPath: NSTemporaryDirectory())
      .appendingPathComponent("OmiScreenFrames", isDirectory: true)
    try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    let url = directory.appendingPathComponent("Retried \(fileName)")
    do {
      try data.write(to: url, options: .atomic)
    } catch {
      return nil
    }
    return url
  }

  /// Deletes staged screen files older than a week. Staging writes private
  /// full-screen captures here on every pick and paste, and a file whose app
  /// quit before its cleanup runs is one the OS may not reap for days — the
  /// sweep bounds that exposure to the lifetime of the staging flow itself.
  nonisolated static func sweepStaleStagedFiles(
    in directory: URL, olderThanDays days: Int = 7, now: Date = Date()
  ) {
    let cutoff = now.addingTimeInterval(-TimeInterval(days) * 86_400)
    guard
      let enumerator = FileManager.default.enumerator(
        at: directory, includingPropertiesForKeys: [.contentModificationDateKey])
    else { return }
    for case let url as URL in enumerator {
      guard
        let modified = try? url.resourceValues(forKeys: [.contentModificationDateKey])
          .contentModificationDate,
        modified < cutoff
      else { continue }
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

  /// Puts a failed turn's attachments back in the composer, so "Try again"
  /// re-sends the same pixels instead of a caption for files that are gone.
  /// The failed turn's exit cleanup deletes app-owned staged files, so each of
  /// those is re-staged into a fresh app-owned file from its in-memory bytes;
  /// user-picked files still exist and are re-added as they are.
  func restoreFailedTurnAttachments(_ attachments: [ChatAttachment], turnOwner: ChatTurnOwner) {
    guard turnOwner == .mainChat, !attachments.isEmpty else { return }
    let restored = attachments.map { attachment in
      guard attachment.appOwnedFileURL != nil, let data = attachment.data, !data.isEmpty
      else { return attachment }
      var fresh = attachment
      if let url = RecentFrameStagingLifecycle.writeAppOwnedFile(
        data: data, fileName: attachment.fileName)
      {
        fresh.appOwnedFileURL = url
      }
      return fresh
    }
    addAttachments(restored)
  }
}
