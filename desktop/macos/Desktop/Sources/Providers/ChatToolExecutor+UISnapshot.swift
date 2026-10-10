import AppKit
import ApplicationServices
import Carbon
import Foundation

/// The process a snapshot reads, as the target step resolved it.
struct UISnapshotTarget: Equatable, Sendable {
  let pid: pid_t
  /// Lowercased: the bundle id the kernel approved.
  let bundleID: String
  let checksSettingsPane: Bool
}

/// What `ui_snapshot` asks of the system, so the executor runs against fakes
/// in tests and never against a real app.
struct UISnapshotEnvironment: Sendable {
  var isAccessibilityTrusted: @Sendable () -> Bool
  var runningApps: @MainActor @Sendable () -> [UIAutomationRunningApp]
  var isExcludedFromCapture: @MainActor @Sendable (String) -> Bool
  var isSecureInputActive: @Sendable () -> Bool
  var ownPID: pid_t
  var assistiveTreeMode: @Sendable (URL?) -> AssistiveTreeMode
  /// The bundle id a pid belongs to right now, checked off the main actor
  /// just before and just after the read.
  var bundleIDOfProcess: @Sendable (pid_t) -> String?
  /// Runs off the main actor. A pane-checked target gets the System Settings
  /// pane guard, built there because it reads the installed extensions once.
  var snapshot:
    @Sendable (
      _ target: UISnapshotTarget, _ request: WindowSnapshotRequest, _ isCancelled: @escaping @Sendable () -> Bool
    )
      -> Result<WindowSnapshot, WindowSnapshotFailure>

  static var live: UISnapshotEnvironment {
    UISnapshotEnvironment(
      isAccessibilityTrusted: { AXIsProcessTrusted() },
      runningApps: {
        NSWorkspace.shared.runningApplications.compactMap { app in
          guard let bundleID = app.bundleIdentifier else { return nil }
          return UIAutomationRunningApp(
            pid: app.processIdentifier, bundleID: bundleID, localizedName: app.localizedName,
            bundleURL: app.bundleURL, isActive: app.isActive)
        }
      },
      isExcludedFromCapture: { RewindSettings.shared.isAppExcluded($0) },
      isSecureInputActive: { IsSecureEventInputEnabled() },
      ownPID: ProcessInfo.processInfo.processIdentifier,
      assistiveTreeMode: { UIAutomationTargetPolicy.assistiveTreeMode(bundleURL: $0) },
      bundleIDOfProcess: { NSRunningApplication(processIdentifier: $0)?.bundleIdentifier },
      snapshot: { target, request, isCancelled in
        var request = request
        if target.checksSettingsPane { request.paneGuard = SettingsPaneGuard.live }
        var walker = WindowSnapshotWalker(
          source: LiveAccessibilityElementSource(pid: target.pid),
          now: { ProcessInfo.processInfo.systemUptime },
          pause: { Thread.sleep(forTimeInterval: $0) })
        walker.isCancelled = isCancelled
        return walker.snapshot(request)
      })
  }
}

/// Carries the calling task's cancellation into the detached read.
final class UISnapshotCancellation: @unchecked Sendable {
  private let lock = NSLock()
  private var cancelled = false

  func cancel() { lock.withLock { cancelled = true } }
  var isCancelled: Bool { lock.withLock { cancelled } }
}

/// `ui_snapshot`: one window of another app as named elements.
///
/// The kernel has already parked this call behind the per-app approval card
/// and dispatched it only after an allow, and the owner bind around the call
/// is the second gate. This executor is the third: it treats the approved
/// bundle id as untrusted text, resolves the one running copy without
/// launching anything, applies the refusal floor against the real process,
/// checks that the pid still belongs to the approved app right before and
/// after reading, and walks off the main actor so a hung app never blocks the
/// UI. The result carries facts only; how to read it lives in the manifest.
extension ChatToolExecutor {
  static var uiSnapshotEnvironment = UISnapshotEnvironment.live

  static func executeUISnapshot(_ args: [String: Any]) async -> String {
    let environment = uiSnapshotEnvironment
    guard let bundleID = UIAutomationTargetPolicy.normalizedBundleID(args["bundle_id"]) else {
      return deviceToolFailure(
        reason: "invalid_arguments", message: "bundle_id must name an app, for example com.apple.TextEdit.")
    }
    guard environment.isAccessibilityTrusted() else {
      return deviceToolFailure(
        reason: "accessibility_not_granted",
        message: "Omi needs Accessibility permission to read app windows.",
        requiredPermission: "accessibility")
    }

    let requestedPID = args["pid"] == nil ? nil : boundedInt(args, "pid", default: -1)
    if let requestedPID, requestedPID <= 0 || requestedPID > Int(Int32.max) {
      return deviceToolFailure(reason: "invalid_arguments", message: "pid must be a running process id.")
    }
    let app: UIAutomationRunningApp
    switch UIAutomationTargetPolicy.resolve(
      bundleID: bundleID, pid: requestedPID.map { pid_t($0) }, running: environment.runningApps())
    {
    case .failure(let failure): return targetFailureJSON(failure)
    case .success(let resolved): app = resolved
    }
    if let refusal = UIAutomationTargetPolicy.refusal(
      for: app, ownPID: environment.ownPID, isExcludedFromCapture: environment.isExcludedFromCapture,
      isSecureInputActive: environment.isSecureInputActive())
    {
      log("ui_snapshot: refused bundle=\(bundleID) reason=\(refusal.reason)")
      return targetFailureJSON(refusal)
    }

    let request = uiSnapshotRequest(args, assistiveTree: environment.assistiveTreeMode(app.bundleURL))
    let target = UISnapshotTarget(
      pid: app.pid, bundleID: bundleID, checksSettingsPane: UIAutomationTargetPolicy.isPaneChecked(app.bundleID))
    let cancellation = UISnapshotCancellation()
    let outcome: Result<WindowSnapshot, WindowSnapshotFailure>
    do {
      outcome = try await withTaskCancellationHandler {
        try await offMainActor { _ in
          let targetChanged = WindowSnapshotFailure(
            reason: "target_changed", message: "That process no longer belongs to the approved app; nothing was read.")
          guard environment.bundleIDOfProcess(target.pid)?.lowercased() == target.bundleID else {
            return .failure(targetChanged)
          }
          let result = environment.snapshot(target, request) { cancellation.isCancelled }
          guard environment.bundleIDOfProcess(target.pid)?.lowercased() == target.bundleID else {
            return .failure(targetChanged)
          }
          return result
        }
      } onCancel: {
        cancellation.cancel()
      }
    } catch {
      return deviceToolFailure(reason: "snapshot_failed", message: "Omi could not read the window.")
    }

    switch outcome {
    case .success(let snapshot):
      log(
        "ui_snapshot: bundle=\(bundleID) nodes=\(snapshot.nodes.count) visited=\(snapshot.visited) "
          + "ms=\(snapshot.elapsedMilliseconds) stop=\(snapshot.stopReason?.rawValue ?? "none") "
          + "sparse=\(snapshot.sparseReason ?? "no") assistive_tree=\(request.assistiveTree.logName) "
          + "enabled=\(snapshot.assistiveTreeEnabled) retried=\(snapshot.assistiveTreeRetried)")
      let appName = WindowSnapshotText.bounded(
        WindowSnapshotText.appText(app.localizedName ?? ""), limits: request.limits)
      return deviceToolJSON(snapshot.payload(appName: appName, bundleID: app.bundleID, pid: app.pid))
    case .failure(let failure):
      log(
        "ui_snapshot: bundle=\(bundleID) failed reason=\(failure.reason) "
          + "assistive_tree=\(request.assistiveTree.logName)")
      if failure.reason == "accessibility_not_granted" {
        return deviceToolFailure(
          reason: failure.reason, message: failure.message, requiredPermission: "accessibility")
      }
      var payload: [String: Any] = ["ok": false, "reason": failure.reason, "error": failure.message]
      if !failure.windows.isEmpty {
        // Window titles are app text: quoted, after the window number.
        payload["windows"] = failure.windows.map { window -> String in
          let number = window.windowID.map { "window_id=\($0) " } ?? ""
          return number + WindowSnapshot.field("window_title", window.text)
        }
      }
      return deviceToolJSON(payload)
    }
  }

  /// The model's numbers are clamped, never trusted: `1e100` and `NaN` read as absent.
  static func uiSnapshotRequest(_ args: [String: Any], assistiveTree: AssistiveTreeMode) -> WindowSnapshotRequest {
    var request = WindowSnapshotRequest()
    let windowID = boundedInt(args, "window_id", default: 0)
    if windowID > 0, windowID <= Int(UInt32.max) { request.windowID = CGWindowID(windowID) }
    if let title = args["window_title"] as? String {
      let trimmed = title.trimmingCharacters(in: .whitespacesAndNewlines)
      if !trimmed.isEmpty { request.windowTitle = String(trimmed.prefix(256)) }
    }
    let ceiling = WindowSnapshotLimits.maxNodesCeiling
    request.limits.maxNodes = min(max(boundedInt(args, "max_nodes", default: ceiling), 1), ceiling)
    request.assistiveTree = assistiveTree
    return request
  }

  private static func targetFailureJSON(_ failure: UIAutomationTargetFailure) -> String {
    var payload: [String: Any] = ["ok": false, "reason": failure.reason, "error": failure.message]
    if !failure.candidatePIDs.isEmpty { payload["pids"] = failure.candidatePIDs.map { Int($0) } }
    return deviceToolJSON(payload)
  }
}
