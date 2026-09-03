import AppKit
import ApplicationServices
import Foundation

/// What the user is looking at right now: the front window's accessibility text and a
/// picture of it.
///
/// The two cover for each other. Accessibility is exact and free but absent wherever an
/// app does not publish a tree — Chromium leaves web content dark unless a client sets
/// `AXManualAccessibility`, and Electron and canvas-drawn apps publish almost nothing. A
/// screenshot never has that gap and never has the structure. Asking for both means a
/// spoken question about something on screen is answerable in either case, and answerable
/// well when both land.
///
/// Scoped to the front window rather than the display: it is what "this" means when the
/// user says it, it keeps other apps' content out of the frame, and it structurally
/// excludes Omi's own floating panel, which sits in a window of its own.
@MainActor
enum ScreenGlance {
  struct Glance: Sendable {
    let appName: String
    let windowTitle: String
    let pageURL: String
    /// Accessibility text, empty when the app publishes none.
    let text: String
    /// A downscaled JPEG of the front window, nil without Screen Recording permission.
    let image: Data?

    var isEmpty: Bool { text.isEmpty && image == nil }
  }

  /// Bounds borrowed from the form scanner, which walks the same trees.
  private static let maxDepth = 14
  private static let maxNodes = 900
  /// One AX value can hold a whole document; past this a line is a dump, not a label.
  nonisolated static let maxLineLength = 300
  /// Enough of a page to answer from, bounded so a long document cannot crowd out the
  /// sweep results the prompt also carries.
  nonisolated static let maxTextLength = 6_000

  static func capture() async -> Glance? {
    guard let app = NSWorkspace.shared.frontmostApplication,
      app.processIdentifier != ProcessInfo.processInfo.processIdentifier
    else { return nil }

    let window = focusedWindow(of: app)
    let glance = Glance(
      appName: app.localizedName ?? "",
      windowTitle: window.map { AXFormTree.stringAttribute($0, "AXTitle") } ?? "",
      pageURL: window.map(AXFormTree.pageURL(inWindow:)) ?? "",
      text: window.map(accessibilityText(of:)) ?? "",
      image: await frontWindowImage()
    )
    return glance.isEmpty && glance.windowTitle.isEmpty ? nil : glance
  }

  private static func focusedWindow(of app: NSRunningApplication) -> AXUIElement? {
    guard AXIsProcessTrusted() else { return nil }
    let appElement = AXUIElementCreateApplication(app.processIdentifier)
    return AXFormTree.elementAttribute(appElement, "AXFocusedWindow")
  }

  private static func accessibilityText(of window: AXUIElement) -> String {
    let nodes = AXFormTree.collectNodes(from: window, maxDepth: maxDepth, maxNodes: maxNodes)
    return render(nodes.flatMap { [$0.title, $0.value, $0.placeholder, $0.description] })
  }

  private static func frontWindowImage() async -> Data? {
    guard let windowID = ScreenCaptureService.getActiveWindowInfo().windowID else { return nil }
    let service = ScreenCaptureService()
    guard case .success(let image) = await service.captureWindowCGImage(windowID: windowID),
      let encoded = service.encodeJPEG(from: image)
    else { return nil }
    return SuggestionFramePreview.downscaledJPEG(from: encoded)
  }

  /// Flatten the tree's strings into something a model can read.
  ///
  /// A UI tree repeats itself — a button's title is also its parent group's description,
  /// and a list renders every row twice through `AXChildren` and `AXVisibleChildren` — so
  /// the same words arrive many times. Deduplicating is most of what makes this readable
  /// and is why the budget goes on distinct content rather than on repetition.
  nonisolated static func render(_ raw: [String], limit: Int = maxTextLength) -> String {
    var seen = Set<String>()
    var lines: [String] = []
    var used = 0
    for entry in raw {
      let line = entry.trimmingCharacters(in: .whitespacesAndNewlines)
        .replacingOccurrences(of: "\n", with: " ")
      guard line.count > 1 else { continue }
      let clipped = line.count > maxLineLength ? String(line.prefix(maxLineLength)) + "…" : line
      let key = clipped.lowercased()
      guard seen.insert(key).inserted else { continue }
      guard used + clipped.count + 1 <= limit else { break }
      used += clipped.count + 1
      lines.append(clipped)
    }
    return lines.joined(separator: "\n")
  }

  /// The prompt section, or empty when nothing could be read. The image, when there is
  /// one, rides the request separately; this names it so the model knows to look.
  nonisolated static func promptSection(_ glance: Glance?) -> String {
    guard let glance else { return "" }
    var lines = ["== WHAT IS ON THEIR SCREEN RIGHT NOW =="]
    if !glance.appName.isEmpty { lines.append("App: \(glance.appName)") }
    if !glance.windowTitle.isEmpty { lines.append("Window: \(glance.windowTitle)") }
    if !glance.pageURL.isEmpty { lines.append("Page: \(glance.pageURL)") }
    if glance.image != nil {
      lines.append(
        "A picture of this window is attached. It is the truth about what they can see;"
          + " read values off it when the text below is missing or thin.")
    }
    if !glance.text.isEmpty {
      lines.append("")
      lines.append("Text read from the window:")
      lines.append(glance.text)
    }
    return lines.joined(separator: "\n")
  }
}
