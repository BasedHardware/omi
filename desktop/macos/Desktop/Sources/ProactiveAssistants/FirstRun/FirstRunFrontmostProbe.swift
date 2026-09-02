import AppKit
import Foundation

/// Watches the frontmost app and window title while the first run is active and posts each change
/// as a first-run context switch. The proactive monitoring loop posts the same switches, but only
/// when screen analysis is running; the guide must work without it.
///
/// Polls the title every two seconds and reacts to app activation immediately. Posts only on
/// change, so the reducer's dwell timers are keyed on real transitions.
@MainActor
final class FirstRunFrontmostProbe {
  static let pollInterval: UInt64 = 2_000_000_000

  private var activationObserver: NSObjectProtocol?
  private var pollTask: Task<Void, Never>?
  private var last: (bundleID: String, title: String)?

  func start() {
    guard pollTask == nil else { return }
    activationObserver = NSWorkspace.shared.notificationCenter.addObserver(
      forName: NSWorkspace.didActivateApplicationNotification, object: nil, queue: .main
    ) { [weak self] _ in
      Task { @MainActor [weak self] in await self?.observeOnce() }
    }
    pollTask = Task { [weak self] in
      while !Task.isCancelled {
        await self?.observeOnce()
        try? await Task.sleep(nanoseconds: Self.pollInterval)
      }
    }
    log("FirstRunFrontmostProbe: started")
  }

  func stop() {
    pollTask?.cancel()
    pollTask = nil
    if let activationObserver {
      NSWorkspace.shared.notificationCenter.removeObserver(activationObserver)
    }
    activationObserver = nil
    last = nil
    log("FirstRunFrontmostProbe: stopped")
  }

  private func observeOnce() async {
    guard let app = NSWorkspace.shared.frontmostApplication, let bundleID = app.bundleIdentifier else { return }
    let info = await WindowMonitor.getActiveWindowInfoAsync()
    guard !Task.isCancelled else { return }
    let appName = info.appName ?? app.localizedName ?? bundleID
    guard let title = ContextDetection.normalizeWindowTitle(info.windowTitle, appName: appName), !title.isEmpty
    else { return }
    if let last, last.bundleID == bundleID, last.title == title { return }
    last = (bundleID, title)
    FirstRunContextObserver.post(appName: appName, bundleID: bundleID, windowTitle: info.windowTitle, bucketID: nil)
  }
}
