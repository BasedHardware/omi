import Foundation

/// One row of the composer's "recent screens" picker: a Rewind frame's
/// metadata, ready for a menu title. No bytes — a SwiftUI `Menu` builds its
/// content eagerly, so the picker lists rows and decodes only on stage.
struct RecentScreenFrameRow: Identifiable, Equatable {
  let id: Int64
  let appName: String
  let windowTitle: String?
  let timestamp: Date

  init?(screenshot: Screenshot) {
    guard let id = screenshot.id else { return nil }
    self.id = id
    self.appName = screenshot.appName
    self.windowTitle = screenshot.windowTitle
    self.timestamp = screenshot.timestamp
  }

  /// App first — that is what the user recognizes; then an age the reader can
  /// act on. A bare clock time reads "14:32" whether the frame is twenty
  /// minutes or a day old, and the send-time policy refuses frames past the
  /// freshness bound — a person picking from this menu needs to see that
  /// distance, not compute it.
  func menuTitle(now: Date = Date()) -> String {
    return "\(appName) — \(Self.ageDescription(from: timestamp, to: now))"
  }

  static func ageDescription(from date: Date, to now: Date) -> String {
    let age = now.timeIntervalSince(date)
    if age < 60 { return "just now" }
    if age < 3_600 { return "\(Int(age / 60))m ago" }
    if age < 86_400 { return "\(Int(age / 3_600))h ago" }
    return dayFormatter.string(from: date)
  }

  private static let dayFormatter: DateFormatter = {
    let formatter = DateFormatter()
    formatter.timeStyle = .short
    formatter.dateStyle = .medium
    return formatter
  }()
}

/// The one staging path from "a Rewind frame's bytes" to "a chat attachment",
/// shared by the composer's picker and the first-real-app card's handoff.
///
/// Frames enter through a temp file and `ChatAttachment.from(url:)` rather
/// than `ChatAttachment.fromImageData` so the attachment carries a
/// `localFileURL`: if its upload later fails, the send degrades to local-only
/// pixels instead of aborting, which is what a data-only attachment's failure
/// state would do to the whole turn.
enum RecentScreenFrameStaging {
  static func attachment(appName: String, jpegData: Data, capturedAt: Date = Date()) -> ChatAttachment? {
    let safeApp =
      appName
      .replacingOccurrences(of: "/", with: "-")
      .replacingOccurrences(of: ":", with: "-")
    let stamp = fileNameFormatter.string(from: capturedAt)
    let url =
      framesDirectory
      .appendingPathComponent("Screen frame (\(safeApp)) \(stamp) \(UUID().uuidString).jpg")
    do {
      try jpegData.write(to: url, options: .atomic)
    } catch {
      return nil
    }
    guard var attachment = ChatAttachment.from(url: url) else { return nil }
    // The JPEG is app-owned: every drop path that never sends it (removal,
    // clear-chat, dismissal) and the turn that did send it both delete it,
    // so staged screen frames cannot accumulate private screenshots in the
    // temp directory.
    attachment.appOwnedFileURL = url
    return attachment
  }

  /// Created on demand; the OS reaps it like any temp content. A staged frame
  /// outliving its file behaves exactly like a user attachment whose source
  /// file has since moved.
  private static var framesDirectory: URL {
    let url =
      URL(fileURLWithPath: NSTemporaryDirectory())
      .appendingPathComponent("OmiScreenFrames", isDirectory: true)
    try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
    RecentFrameStagingLifecycle.sweepStaleStagedFiles(in: url)
    return url
  }

  /// The staging directory, for tests asserting that a sanitized file name
  /// lands directly inside it (no nested directory from an unsanitized
  /// appName).
  static var framesDirectoryForTesting: URL { framesDirectory }

  private static let fileNameFormatter: DateFormatter = {
    let formatter = DateFormatter()
    formatter.dateFormat = "HHmm"
    return formatter
  }()
}
