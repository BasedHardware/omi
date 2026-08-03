import AppKit
import Foundation
import ObjCExceptionCatcher
import SwiftUI

/// Renders a SwiftUI view to a real document (vector PDF or PNG) fully on-device.
///
/// This is the reusable core that `ViewExporter` already proved out for its CLI screenshot
/// mode: an `NSHostingView` inside a borderless offscreen window, captured either through
/// `dataWithPDF(inside:)` (vector) or `bitmapImageRepForCachingDisplay` (raster). The
/// difference is that this version **returns `Data`** instead of writing to a directory and
/// exiting, so product code can render a person profile and hand the file to the user.
///
/// Privacy: a rendered person profile is dense inferred personal data about a third party.
/// Nothing here logs the view's contents, the person's name, or the file's bytes, and nothing
/// is transmitted — the only side effect is a file in the user's own Downloads folder.
enum PersonProfileRenderer {

  // MARK: - Rendering

  /// Renders `view` to vector PDF data. Must be called on the main actor (AppKit hosting).
  /// Returns nil when AppKit could not produce a backing store for the requested size.
  ///
  /// The renderer applies no background or color scheme of its own: compose the document view
  /// with the background and `.environment(\.colorScheme, …)` you want baked into the file.
  @MainActor
  static func renderPDF<V: View>(_ view: V, size: CGSize) -> Data? {
    render(view, size: size) { host in host.dataWithPDF(inside: host.bounds) }
  }

  /// Renders `view` to PNG data. Must be called on the main actor (AppKit hosting).
  @MainActor
  static func renderPNG<V: View>(_ view: V, size: CGSize) -> Data? {
    render(view, size: size) { host in
      guard let rep = host.bitmapImageRepForCachingDisplay(in: host.bounds) else { return nil }
      host.cacheDisplay(in: host.bounds, to: rep)
      return rep.representation(using: .png, properties: [:])
    }
  }

  /// Hosts `view` offscreen at `size`, lays it out, and captures it with `capture`.
  /// AppKit raises ObjC exceptions for some view trees, so the capture is guarded the same way
  /// the CLI exporter guards it — a raised exception is a nil result, never a crash.
  @MainActor
  private static func render<V: View>(
    _ view: V, size: CGSize, _ capture: (NSHostingView<V>) -> Data?
  ) -> Data? {
    let width = size.width.isFinite ? max(1, size.width.rounded()) : 1
    let height = size.height.isFinite ? max(1, size.height.rounded()) : 1
    let bounded = CGSize(width: width, height: height)

    let hostingView = NSHostingView(rootView: view)
    hostingView.setFrameSize(bounded)

    let window = NSWindow(
      contentRect: NSRect(origin: .zero, size: bounded),
      styleMask: [.borderless],
      backing: .buffered,
      defer: false
    )
    window.contentView = hostingView
    hostingView.needsLayout = true
    hostingView.layoutSubtreeIfNeeded()

    var data: Data?
    let exception = ObjCExceptionCatcher.catching { data = capture(hostingView) }
    window.orderOut(nil)

    if let exception {
      log("PersonProfileRenderer: render failed - \(exception.name.rawValue)")
      return nil
    }
    return data
  }

  // MARK: - Writing

  /// Writes rendered PDF bytes to `~/Downloads/Omi Exports/<safe name>.pdf` and returns the URL.
  ///
  /// The directory is created when missing, and an existing file is never overwritten — a
  /// numbered sibling is used instead, so a second export cannot silently destroy the first
  /// one (or an unrelated file that happens to share the name).
  static func write(pdf: Data, personName: String) throws -> URL {
    try write(pdf: pdf, personName: personName, directory: exportDirectory())
  }

  /// Seam for tests: write into an explicit directory rather than the user's Downloads folder.
  static func write(pdf: Data, personName: String, directory: URL) throws -> URL {
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    let url = availableURL(in: directory, base: safeFileName(for: personName), extension: "pdf")
    try pdf.write(to: url, options: .atomic)
    return url
  }

  /// `~/Downloads/Omi Exports/` — the same folder the memory export already uses, so every
  /// document Omi hands the user lands in one predictable place. Not created here; `write`
  /// creates it on demand.
  static func exportDirectory() -> URL {
    let downloads =
      FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask).first
      ?? FileManager.default.homeDirectoryForCurrentUser
    return downloads.appendingPathComponent("Omi Exports", isDirectory: true)
  }

  /// A filesystem-safe base name for a person: no path separators, no colons, no control
  /// characters, no leading dot, and short enough that the final name (plus a numeric suffix
  /// and extension) fits the 255-byte per-component limit. Emoji and non-Latin scripts are
  /// preserved — they are legal on APFS and the name is what the recipient will see.
  static func safeFileName(for personName: String) -> String {
    let illegal = CharacterSet(charactersIn: "/\\:*?\"<>|").union(.controlCharacters)
    var scalars = String.UnicodeScalarView()
    for scalar in personName.unicodeScalars {
      scalars.append(illegal.contains(scalar) ? " " : scalar)
    }
    let collapsed = String(scalars).split(whereSeparator: { $0.isWhitespace }).joined(separator: " ")
    let unhidden = String(collapsed.drop(while: { $0 == "." }))
    let trimmed = truncate(unhidden, toUTF8Bytes: 120).trimmingCharacters(in: .whitespaces)
    return trimmed.isEmpty ? "Person" : trimmed
  }

  /// Truncates on a character boundary so a multi-byte scalar (emoji, CJK) is never split.
  private static func truncate(_ value: String, toUTF8Bytes limit: Int) -> String {
    guard value.utf8.count > limit else { return value }
    var out = ""
    var used = 0
    for character in value {
      let width = String(character).utf8.count
      if used + width > limit { break }
      out.append(character)
      used += width
    }
    return out
  }

  /// First unused `<base>.<ext>` / `<base> 2.<ext>` / … in `directory`.
  private static func availableURL(in directory: URL, base: String, extension ext: String) -> URL {
    let fm = FileManager.default
    let first = directory.appendingPathComponent("\(base).\(ext)")
    if !fm.fileExists(atPath: first.path) { return first }
    for index in 2...99 {
      let candidate = directory.appendingPathComponent("\(base) \(index).\(ext)")
      if !fm.fileExists(atPath: candidate.path) { return candidate }
    }
    return directory.appendingPathComponent("\(base) \(UUID().uuidString).\(ext)")
  }
}
