import AppKit
import ApplicationServices
import Foundation

/// Launching apps and arranging their windows.
///
/// Everything here is deliberate rather than synthetic: an app is asked to come
/// forward, a window is asked to raise itself. That is more reliable than
/// clicking a Dock icon and, unlike a click, it says what it meant, so a failure
/// is reported instead of landing somewhere else on the screen.
enum CuaAppControl {
  /// Launch or reveal an app by name or bundle id.
  ///
  /// Resolution goes through LaunchServices via `/usr/bin/open`, which already
  /// knows every way a user might name an app — display name, bundle id, or the
  /// path to the bundle — and finds apps outside `/Applications`. The arguments
  /// are passed as a list, never through a shell, so a name with quotes in it is
  /// a name and not an injection.
  static func open(app name: String) -> Bool {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/usr/bin/open")
    process.arguments = ["-a", name]
    do {
      try process.run()
      process.waitUntilExit()
      return process.terminationStatus == 0
    } catch {
      log("CuaAppControl: open failed for \(name): \(error.localizedDescription)")
      return false
    }
  }

  @MainActor
  static func activate(app name: String) -> Bool {
    guard let pid = CuaAxReader.processID(forAppNamed: name),
      let app = NSRunningApplication(processIdentifier: pid)
    else { return false }
    return app.activate(options: [.activateAllWindows])
  }

  struct WindowHandle {
    let element: AXUIElement
    let title: String
  }

  /// An app's windows, in the order the app reports them (frontmost first).
  static func windows(pid: pid_t) async -> [WindowHandle] {
    guard AccessibilityProcessBoundary.isForeignProcess(pid) else { return [] }
    return await withCheckedContinuation { continuation in
      CuaAxReader.queue.async {
        let app = AXUIElementCreateApplication(pid)
        var raw: CFTypeRef?
        guard
          AXUIElementCopyAttributeValue(app, kAXWindowsAttribute as CFString, &raw) == .success,
          let elements = raw as? [AXUIElement]
        else {
          continuation.resume(returning: [])
          return
        }
        continuation.resume(
          returning: elements.map { element in
            var titleRef: CFTypeRef?
            AXUIElementCopyAttributeValue(element, kAXTitleAttribute as CFString, &titleRef)
            return WindowHandle(element: element, title: titleRef as? String ?? "")
          })
      }
    }
  }

  /// Bring one window to the front. A title picks a specific window; without one
  /// the app's frontmost window is raised, which is what "focus Safari" means.
  static func raiseWindow(pid: pid_t, titled title: String?) async -> Bool {
    let handles = await windows(pid: pid)
    let match =
      title.map { needle in
        handles.first { $0.title.localizedCaseInsensitiveContains(needle) }
      } ?? handles.first
    guard let match else { return false }
    let box = AXElementBox(match.element)
    return await withCheckedContinuation { continuation in
      CuaAxReader.queue.async {
        AXUIElementSetAttributeValue(box.element, kAXMainAttribute as CFString, kCFBooleanTrue)
        let raised = AXUIElementPerformAction(box.element, kAXRaiseAction as CFString) == .success
        continuation.resume(returning: raised)
      }
    }
  }

  /// Move and resize a window in global points. Either half may be omitted, so a
  /// window can be moved without being resized.
  static func setWindowFrame(
    pid: pid_t, titled title: String?, origin: CGPoint?, size: CGSize?
  ) async -> Bool {
    let handles = await windows(pid: pid)
    let match =
      title.map { needle in
        handles.first { $0.title.localizedCaseInsensitiveContains(needle) }
      } ?? handles.first
    guard let match else { return false }
    let box = AXElementBox(match.element)
    return await withCheckedContinuation { continuation in
      CuaAxReader.queue.async {
        var applied = false
        if var origin {
          if let value = AXValueCreate(.cgPoint, &origin) {
            applied =
              AXUIElementSetAttributeValue(box.element, kAXPositionAttribute as CFString, value)
              == .success
          }
        }
        if var size {
          if let value = AXValueCreate(.cgSize, &size) {
            applied =
              AXUIElementSetAttributeValue(box.element, kAXSizeAttribute as CFString, value)
              == .success || applied
          }
        }
        continuation.resume(returning: applied)
      }
    }
  }

  @MainActor
  static func readClipboard() -> String? {
    NSPasteboard.general.string(forType: .string)
  }

  @MainActor
  static func writeClipboard(_ text: String) {
    let pasteboard = NSPasteboard.general
    pasteboard.clearContents()
    pasteboard.setString(text, forType: .string)
  }
}
