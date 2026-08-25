//
//  ScreenFrameQuickLook.swift — captured frames, shown in the viewer macOS already has.
//
//  Every surface that draws Rewind frames draws them as tiles: the Activity spine's strip, the
//  search grid, a meeting note's carousel. A tile is ~118pt wide, which is enough to recognise a
//  moment and nowhere near enough to read one — so "click it and see it properly" is the same need
//  everywhere, and this is the one place it is answered.
//
//  **It is answered with Quick Look rather than with a view of our own, and that is a correction.**
//  The bespoke lightbox this file replaces failed at the only job it had. Its panel was
//  `glassCard`, whose entire background is `Ink.rowFill` — `labelColor.opacity(0.045)` — over a
//  0.28 scrim, so the "modal" was about 68% transparent and the note's text read straight through
//  the screenshot. Its frame was a hardcoded `height: 560`, not a fraction of what was available,
//  so on a shorter shell the image was clipped by its own host. And a 5120pt-wide capture fit into
//  a 1030x560 box is rendered at a fifth of native, with no zoom, no pan and no 1:1 — which is to
//  say the one thing the user clicked for, reading the frame, was the one thing it could not do.
//
//  Quick Look fixes all three by not being ours: an opaque system panel, sized by the system, with
//  pinch and scroll zoom, space-to-close, full screen, share, Open With, and left/right stepping
//  across the whole set. What we owe it is a file, a title, and cleanup.
//
//  ## The three things this file actually has to get right
//
//  1. **Quick Look needs a file, and almost none of these frames are one.** A meeting frame's
//     pixels are a signed URL good for 60 minutes; a Rewind moment's are usually a frame inside an
//     H.264 chunk (`Screenshot.usesVideoStorage`), not a JPEG on disk. So every open materialises
//     bytes into `OmiQuickLook/` under the temp directory. `RewindStorage.loadScreenshotData` is
//     the right call for the local case — it already returns encoded bytes for both the video and
//     the legacy-file paths, so this does not add a second decode.
//  2. **Those temp files must not outlive the panel.** Rewind's own store is unencrypted on disk,
//     so a local frame's copy is not a new class of exposure. A *server* frame's is: "delete this
//     screenshot from the note" cannot reach a stray copy in `/tmp`. So the directory is purged
//     when the panel closes and again at launch, and it is one directory we own outright rather
//     than loose files among the system's.
//  3. **The responder chain.** `QLPreviewPanel` will not open for an app that does not claim it.
//     The claim lives on `AppDelegate` rather than on a view, deliberately: the delegate is in the
//     chain unconditionally, so there is no fight with SwiftUI over who is first responder and no
//     window that can be in a state where the panel silently refuses to appear.
//
//  Deleting a frame is no longer part of this surface. Quick Look's chrome is Apple's and cannot
//  take a trash button — so per-frame delete moved to a right-click on the tile, which is where
//  Finder puts it and is the more native place for it to have been all along.
//

import AppKit
import OmiTheme
@preconcurrency import QuickLookUI
import SwiftUI
import os

// MARK: - What a surface hands over

/// One frame, described well enough to put on screen and to fetch on demand.
///
/// Value-typed and free of pixels: a set of these is cheap to build on every render of a strip,
/// and nothing is fetched until someone actually opens one.
struct QuickLookFrame: Identifiable, Equatable {
  enum Source: Equatable {
    /// A Rewind row. Bytes come from local storage — a video chunk frame, or a legacy JPEG.
    case local(Screenshot)
    /// A persisted server frame. Bytes come from a signed URL with an hour of life in it.
    case remote(URL)
  }

  let id: String
  let source: Source
  /// What Quick Look shows in its title bar. The caption when there is one, the app and time when
  /// there is not — never empty, because an untitled Quick Look window reads as a failed load.
  let title: String

  init(id: String, source: Source, title: String) {
    self.id = id
    self.source = source
    self.title = title.isEmpty ? "Screenshot" : title
  }

  /// A Rewind moment. The window title is the specific thing; the app is the true fallback.
  init(screenshot: Screenshot, caption: String? = nil) {
    let time = screenshot.timestamp.formatted(date: .abbreviated, time: .shortened)
    let subject: String = {
      if let caption, !caption.isEmpty { return caption }
      if let windowTitle = screenshot.windowTitle, !windowTitle.isEmpty,
        windowTitle != screenshot.appName
      {
        return windowTitle
      }
      return screenshot.appName
    }()
    self.init(
      id: String(screenshot.id ?? 0),
      source: .local(screenshot),
      title: "\(subject) — \(time)")
  }

  /// A persisted meeting frame. `nil` when the server's `content_url` does not even parse, so the
  /// caller skips it rather than opening a panel onto nothing.
  init?(frame: ConversationScreenFrame) {
    guard let url = URL(string: frame.contentURL) else { return nil }
    let time = frame.capturedAt.formatted(date: .abbreviated, time: .shortened)
    let subject = frame.caption.isEmpty ? "Screenshot" : frame.caption
    self.init(id: frame.id, source: .remote(url), title: "\(subject) — \(time)")
  }
}

// MARK: - Bytes on disk

/// Where materialised frames live, and the guarantee that they stop living there.
///
/// One directory we own, rather than loose files in the system's temp: purging then is a single
/// `removeItem` we can reason about, instead of a filename pattern we would have to trust.
enum QuickLookScratch {
  static var directory: URL {
    FileManager.default.temporaryDirectory.appendingPathComponent("OmiQuickLook", isDirectory: true)
  }

  /// Remove everything. Called when the panel closes and once at launch — the second is what
  /// covers a crash or a force-quit while a panel was up.
  static func purge() {
    try? FileManager.default.removeItem(at: directory)
  }

  /// The extension decides the UTI, and the UTI decides whether Quick Look renders the file at all
  /// — so it is sniffed from the bytes rather than assumed from the source. JPEG is the default
  /// because it is what both the capture pipeline and the egress pipeline actually emit.
  static func fileExtension(for data: Data) -> String {
    if data.starts(with: [0x89, 0x50, 0x4E, 0x47]) { return "png" }
    if data.starts(with: [0xFF, 0xD8, 0xFF]) { return "jpg" }
    if data.starts(with: Array("GIF8".utf8)) { return "gif" }
    return "jpg"
  }

  /// Write `data` where Quick Look can read it. The name is derived from the frame id, not from
  /// its caption: the caption is user- and model-authored text that has no business becoming a
  /// path component, and `previewItemTitle` puts it on screen anyway.
  static func write(_ data: Data, id: String) throws -> URL {
    let folder = directory
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    let safeID = id.map { $0.isLetter || $0.isNumber ? $0 : "-" }
    let name = String(String(safeID).prefix(64))
    let url = folder.appendingPathComponent(
      "\(name.isEmpty ? "frame" : name).\(fileExtension(for: data))")
    try data.write(to: url, options: .atomic)
    return url
  }
}

// MARK: - One item, as Quick Look wants it

/// A reference type on purpose. `QLPreviewPanel` holds items and asks them for a URL whenever it
/// needs one, so an item that fills its URL in later can be handed over before its bytes have
/// landed — which is what lets the panel open on the frame the user clicked without first
/// downloading the other five.
///
/// **Not `@MainActor`, and that is load-bearing rather than a preference.** Quick Look renders out
/// of process and reads `previewItemURL` from whichever thread its own machinery is on. An actor
/// hop is not available from a synchronous protocol getter, and `MainActor.assumeIsolated` there
/// would not be an assumption, it would be a trap waiting for the first off-main read. So the one
/// piece of mutable state is held under a lock and every accessor is `nonisolated`.
final class QuickLookItem: NSObject, QLPreviewItem, @unchecked Sendable {
  private struct State {
    var fileURL: URL?
    var loading = false
  }

  let frame: QuickLookFrame
  private let state = OSAllocatedUnfairLock(initialState: State())

  init(frame: QuickLookFrame) {
    self.frame = frame
    super.init()
  }

  nonisolated var previewItemURL: URL? {
    state.withLock { $0.fileURL }
  }

  nonisolated var previewItemTitle: String? {
    frame.title
  }

  var isReady: Bool { previewItemURL != nil }

  /// Fetch and write, once. A second call while the first is in flight, or after it has landed, is
  /// a no-op — the panel asks for items far more often than they change.
  ///
  /// A *failure* is deliberately not latched. `present` builds fresh items on every open, so a
  /// latch could only ever suppress a retry inside one presentation, and the errors here are the
  /// transient kind: an expired signed URL, a video chunk still being written, or — measured, this
  /// is how the bug was found — Rewind storage not yet initialised when the click arrived.
  func materialize() async {
    let shouldStart = state.withLock { current -> Bool in
      guard current.fileURL == nil, !current.loading else { return false }
      current.loading = true
      return true
    }
    guard shouldStart else { return }
    do {
      let data: Data
      switch frame.source {
      case .local(let screenshot):
        // Every other caller that reads Rewind pixels does this first, and a viewer reached from
        // the Activity spine is routinely the first thing in a session to want them.
        try await RewindStorage.shared.initialize()
        data = try await RewindStorage.shared.loadScreenshotData(for: screenshot)
      case .remote(let url):
        let (downloaded, response) = try await URLSession.shared.data(from: url)
        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
          throw URLError(.badServerResponse)
        }
        data = downloaded
      }
      let written = try QuickLookScratch.write(data, id: frame.id)
      state.withLock {
        $0.fileURL = written
        $0.loading = false
      }
    } catch {
      // A frame whose chunk retention already reclaimed it, or whose signed URL expired, is a
      // normal state rather than an error worth interrupting anyone over. Quick Look shows its
      // own "no preview" for an item with no URL, which is the honest thing to put there.
      state.withLock { $0.loading = false }
      log("QUICKLOOK: could not materialize frame \(frame.id) — \(error.localizedDescription)")
    }
  }
}

// MARK: - The panel

/// Owns the current preview set and drives `QLPreviewPanel`.
///
/// A singleton because the panel is one: `QLPreviewPanel.shared()` is app-wide, so two surfaces
/// cannot each have their own, and pretending otherwise would mean two data sources racing to
/// answer the same panel.
@MainActor
final class ScreenFrameQuickLook: NSObject {
  static let shared = ScreenFrameQuickLook()

  private var items: [QuickLookItem] = []
  private var pendingIndex = 0

  private override init() {
    super.init()
    // Covers the case the close-handler cannot: a crash or force-quit with a panel open leaves
    // frames on disk, and this is the next moment anything of ours runs.
    QuickLookScratch.purge()
  }

  /// Whether anything is currently on screen. Read by the delegate hooks, which must not claim a
  /// panel this object did not ask for.
  var isPresenting: Bool { !items.isEmpty }

  /// Open `frames` at `id`. The clicked frame is fetched before the panel appears — opening onto a
  /// spinner would be the bespoke lightbox's failure repeated in a nicer window — and the rest are
  /// fetched behind it so that arrowing along is instant.
  func present(_ frames: [QuickLookFrame], startingAt id: String) {
    guard !frames.isEmpty else { return }
    let start = frames.firstIndex { $0.id == id } ?? 0
    items = frames.map { QuickLookItem(frame: $0) }
    pendingIndex = start

    Task { [weak self] in
      guard let self else { return }
      await self.items[start].materialize()
      // The set can be replaced by a second click while the first fetch is in flight; opening the
      // panel then would show the wrong frame.
      guard self.items.indices.contains(start), self.items[start].frame.id == id else { return }
      self.show(at: start)
      await self.materializeRest(around: start)
    }
  }

  private func show(at index: Int) {
    guard let panel = QLPreviewPanel.shared() else { return }
    // The panel belongs to the app, and the shell is routinely summoned over someone else's
    // full-screen window. Without this the panel opens on the Space the app was last active on
    // rather than the one the user is looking at.
    panel.collectionBehavior.insert(.fullScreenAuxiliary)
    NSApp.activate(ignoringOtherApps: true)
    panel.makeKeyAndOrderFront(nil)
    panel.reloadData()
    panel.currentPreviewItemIndex = index
  }

  /// Fetch everything else, nearest-first, so the frames on either side of the one being read are
  /// the first to become steppable.
  private func materializeRest(around index: Int) async {
    let order = items.indices.sorted { abs($0 - index) < abs($1 - index) }
    for i in order where i != index {
      let item = items[i]
      await item.materialize()
      // Only nudge the panel when the item that just landed is the one being looked at — the user
      // can arrow onto a frame while its bytes are still coming.
      if let panel = QLPreviewPanel.shared(), panel.isVisible,
        panel.currentPreviewItemIndex == i
      {
        panel.refreshCurrentPreviewItem()
      }
    }
  }

  /// What an automation probe can read back about the live panel.
  ///
  /// This exists because the risky part of this design is invisible to every capture path the app
  /// has: `capture_main_window_png` uses `cacheDisplay`, which draws only Omi's own content view,
  /// and Quick Look's panel is a separate window belonging to the system. Whether the responder
  /// chain accepted the panel is therefore not a thing anyone can screenshot — but it is a thing
  /// the app can be asked.
  func probeState() -> [String: String] {
    let exists = QLPreviewPanel.sharedPreviewPanelExists()
    let panel = exists ? QLPreviewPanel.shared() : nil
    return [
      "item_count": "\(items.count)",
      "ready_count": "\(items.filter(\.isReady).count)",
      "first_item_title": items.first?.frame.title ?? "",
      "first_item_url": items.first?.previewItemURL?.lastPathComponent ?? "",
      "panel_exists": exists ? "true" : "false",
      "panel_visible": (panel?.isVisible ?? false) ? "true" : "false",
      // The one that actually answers the responder-chain question: the panel only has a data
      // source if `beginPreviewPanelControl` ran, and that only runs if something in the chain
      // returned true from `acceptsPreviewPanelControl`.
      "panel_controlled": (panel?.dataSource != nil) ? "true" : "false",
      "panel_index": "\(panel?.currentPreviewItemIndex ?? -1)",
    ]
  }

  /// Close the panel from code. Automation only — a person presses Escape or space.
  func dismissForProbe() {
    if QLPreviewPanel.sharedPreviewPanelExists() {
      QLPreviewPanel.shared()?.orderOut(nil)
    }
    didClose()
  }

  /// The panel went away. Drop the set and take the bytes off disk with it.
  fileprivate func didClose() {
    items = []
    pendingIndex = 0
    QuickLookScratch.purge()
  }
}

// MARK: - Data source and delegate

extension ScreenFrameQuickLook: QLPreviewPanelDataSource {
  nonisolated func numberOfPreviewItems(in panel: QLPreviewPanel!) -> Int {
    MainActor.assumeIsolated { items.count }
  }

  nonisolated func previewPanel(_ panel: QLPreviewPanel!, previewItemAt index: Int) -> QLPreviewItem! {
    MainActor.assumeIsolated {
      guard items.indices.contains(index) else { return nil }
      return items[index]
    }
  }
}

extension ScreenFrameQuickLook: QLPreviewPanelDelegate {
  /// Escape closes the panel; every other key is Quick Look's own. Returning `false` lets the
  /// panel keep its arrow-key stepping, which is the whole reason the set is handed over rather
  /// than a single item.
  nonisolated func previewPanel(_ panel: QLPreviewPanel!, handle event: NSEvent!) -> Bool {
    false
  }
}

// MARK: - The claim on the panel

/// The three methods `QLPreviewPanel` looks for. They live on the app delegate rather than on a
/// view because the delegate is in the responder chain no matter what SwiftUI has done with first
/// responder — see this file's header.
extension AppDelegate {
  @objc override func acceptsPreviewPanelControl(_ panel: QLPreviewPanel!) -> Bool {
    MainActor.assumeIsolated { ScreenFrameQuickLook.shared.isPresenting }
  }

  @objc override func beginPreviewPanelControl(_ panel: QLPreviewPanel!) {
    MainActor.assumeIsolated {
      panel.dataSource = ScreenFrameQuickLook.shared
      panel.delegate = ScreenFrameQuickLook.shared
    }
  }

  @objc override func endPreviewPanelControl(_ panel: QLPreviewPanel!) {
    MainActor.assumeIsolated {
      panel.dataSource = nil
      panel.delegate = nil
      ScreenFrameQuickLook.shared.didClose()
    }
  }
}
