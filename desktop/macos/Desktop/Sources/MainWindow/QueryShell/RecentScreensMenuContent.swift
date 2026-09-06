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

  /// App first — that is what the user recognizes; then a compact clock time.
  /// Frames younger than a minute read as "just now" rather than "0:00 ago".
  func menuTitle(now: Date = Date()) -> String {
    let when: String
    if now.timeIntervalSince(timestamp) < 60 {
      when = "just now"
    } else {
      when = Self.timeFormatter.string(from: timestamp)
    }
    return "\(appName) — \(when)"
  }

  private static let timeFormatter: DateFormatter = {
    let formatter = DateFormatter()
    formatter.timeStyle = .short
    formatter.dateStyle = .none
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
    return ChatAttachment.from(url: url)
  }

  /// Created on demand; the OS reaps it like any temp content. A staged frame
  /// outliving its file behaves exactly like a user attachment whose source
  /// file has since moved.
  private static var framesDirectory: URL {
    let url =
      URL(fileURLWithPath: NSTemporaryDirectory())
      .appendingPathComponent("OmiScreenFrames", isDirectory: true)
    try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
    return url
  }

  private static let fileNameFormatter: DateFormatter = {
    let formatter = DateFormatter()
    formatter.dateFormat = "HHmm"
    return formatter
  }()
}
