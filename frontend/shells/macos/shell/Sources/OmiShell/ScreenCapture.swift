import AppKit
import CoreGraphics
import Foundation
import IOKit.ps
import ScreenCaptureKit

struct ScreenCapturedFrame {
  var image: CGImage
  var capturedAt: Date
  var appBundleId: String
  var appName: String
  var windowTitle: String
}

protocol ScreenFrameSource: Sendable {
  func captureFocused(excluded: Set<String>) async throws -> ScreenCapturedFrame?
}

struct ScreenEnvironmentSnapshot: Equatable {
  var onBattery: Bool
  var idleSeconds: TimeInterval
  var mediaPlaying: Bool
  var locked: Bool
  var screensaver: Bool
  var loginwindow: Bool
  var frontmostIsScreenshotApp: Bool
  var screenSharingActive: Bool
  var frontmostBundleId: String
}

protocol ScreenEnvironmentSource: Sendable {
  func snapshot() -> ScreenEnvironmentSnapshot
}

/// Real ScreenCaptureKit one-shot of the focused window. No SCStream, no private AX.
struct ScreenCaptureKitSource: ScreenFrameSource {
  func captureFocused(excluded: Set<String>) async throws -> ScreenCapturedFrame? {
    let content = try await SCShareableContent.excludingDesktopWindows(
      false, onScreenWindowsOnly: true)
    let front = NSWorkspace.shared.frontmostApplication
    let bundleId = front?.bundleIdentifier ?? ""
    if excluded.contains(bundleId) { return nil }
    let pid = front?.processIdentifier ?? 0
    let candidates = content.windows.filter { window in
      guard let app = window.owningApplication else { return false }
      if app.bundleIdentifier == bundleId { return true }
      return pid != 0 && app.processID == pid
    }
    let chosen =
      candidates.first(where: { $0.isOnScreen && $0.frame.width > 0 && $0.frame.height > 0 })
      ?? candidates.first
    guard let window = chosen else { return nil }
    let filter = SCContentFilter(desktopIndependentWindow: window)
    let config = SCStreamConfiguration()
    config.showsCursor = false
    let bounds = window.frame
    let longEdge = max(bounds.width, bounds.height)
    let scale = longEdge > CGFloat(ScreenImaging.captureLongEdge)
      ? CGFloat(ScreenImaging.captureLongEdge) / max(longEdge, 1) : 1
    config.width = max(2, Int((bounds.width * scale).rounded()))
    config.height = max(2, Int((bounds.height * scale).rounded()))
    let image = try await SCScreenshotManager.captureImage(
      contentFilter: filter, configuration: config)
    let clamped = ScreenImaging.clampLongEdge(image, maxLongEdge: ScreenImaging.captureLongEdge)
    return ScreenCapturedFrame(
      image: clamped,
      capturedAt: Date(),
      appBundleId: bundleId,
      appName: front?.localizedName ?? window.owningApplication?.applicationName ?? bundleId,
      windowTitle: window.title ?? "")
  }

  static func primeConsent() async {
    do {
      let content = try await SCShareableContent.excludingDesktopWindows(
        false, onScreenWindowsOnly: true)
      guard let window = content.windows.first else { return }
      let filter = SCContentFilter(desktopIndependentWindow: window)
      let config = SCStreamConfiguration()
      config.showsCursor = false
      config.width = 2
      config.height = 2
      _ = try await SCScreenshotManager.captureImage(
        contentFilter: filter, configuration: config)
    } catch {}
  }
}

struct ScreenSystemEnvironment: ScreenEnvironmentSource {
  func snapshot() -> ScreenEnvironmentSnapshot {
    let front = NSWorkspace.shared.frontmostApplication
    let bundleId = front?.bundleIdentifier ?? ""
    let session = CGSessionCopyCurrentDictionary() as? [String: Any]
    let locked = (session?["CGSSessionScreenIsLocked"] as? Bool) ?? false
    let idle = CGEventSource.secondsSinceLastEventType(
      .combinedSessionState, eventType: CGEventType(rawValue: ~0)!)
    return ScreenEnvironmentSnapshot(
      onBattery: Self.onBattery(),
      idleSeconds: idle,
      mediaPlaying: ScreenExclusionPolicy.mediaPlaybackBundleIds.contains(bundleId),
      locked: locked,
      screensaver: bundleId == "com.apple.ScreenSaver.Engine" || bundleId == "com.apple.loginwindow"
        && locked,
      loginwindow: bundleId == "com.apple.loginwindow",
      frontmostIsScreenshotApp: ScreenExclusionPolicy.screenshotBundleIds.contains(bundleId),
      screenSharingActive: Self.screenSharingActive(),
      frontmostBundleId: bundleId)
  }

  static func preflightGranted() -> Bool {
    CGPreflightScreenCaptureAccess()
  }

  static func requestAccessWhileFrontmost() -> Bool {
    NSApp.activate()
    NSRunningApplication.current.activate()
    FileHandle.standardError.write(
      Data("screen-tcc: CGRequestScreenCaptureAccess firing preflight=\(preflightGranted())\n".utf8))
    let granted = CGRequestScreenCaptureAccess()
    FileHandle.standardError.write(
      Data("screen-tcc: CGRequestScreenCaptureAccess returned \(granted)\n".utf8))
    return granted
  }

  static func openScreenCaptureSettings() -> Bool {
    let url = URL(
      string:
        "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture")!
    return NSWorkspace.shared.open(url)
  }

  private static func onBattery() -> Bool {
    guard let snapshot = IOPSCopyPowerSourcesInfo()?.takeRetainedValue(),
      let list = IOPSCopyPowerSourcesList(snapshot)?.takeRetainedValue() as? [CFTypeRef]
    else { return false }
    for source in list {
      guard
        let desc = IOPSGetPowerSourceDescription(snapshot, source)?.takeUnretainedValue()
          as? [String: Any]
      else { continue }
      if desc[kIOPSPowerSourceStateKey] as? String == kIOPSBatteryPowerValue {
        return true
      }
    }
    return false
  }

  private static func screenSharingActive() -> Bool {
    let apps = NSWorkspace.shared.runningApplications
    let sharingBundles: Set<String> = [
      "com.apple.ScreenSharing",
      "com.apple.controlcenter",
    ]
    for app in apps {
      guard let id = app.bundleIdentifier else { continue }
      if id == "com.apple.screencaptureui" { return true }
      if sharingBundles.contains(id), app.activationPolicy == .regular, !app.isHidden {
        if id == "com.apple.ScreenSharing" { return true }
      }
    }
    let windows = CGWindowListCopyWindowInfo([.optionOnScreenOnly], kCGNullWindowID)
      as? [[String: Any]] ?? []
    for window in windows {
      let name = (window[kCGWindowName as String] as? String ?? "").lowercased()
      if name.contains("screen sharing") || name.contains("sharing your screen") {
        return true
      }
    }
    return false
  }
}

actor ScreenCaptureEngine {
  private let store: ScreenLocalStore
  private let source: ScreenFrameSource
  private let environment: ScreenEnvironmentSource
  private var ingest: ScreenIngestClient?
  private let deviceName: String
  private var state: ScreenCaptureState = .idle
  private var reason: String?
  private var sessionId: String?
  private var fence = ScreenFence.initial
  private var loopTask: Task<Void, Never>?
  private var ingestTask: Task<Void, Never>?
  private var lastCaptureAt: Date?
  private var lastAnchorAt: Date?
  private var lastAppBundleId: String?
  private var lastWindowTitle: String?
  private var lastStoredDHash: UInt64?
  private var lastOCRDHash: UInt64?
  private var capturedCount = 0
  private var videoCallTick = 0
  private var sharingBackoffUntil: Date?
  private var lastPreflightCheck = Date.distantPast
  private var statusSink: (@Sendable (ScreenStatusEvent) -> Void)?
  private var running = false

  init(
    store: ScreenLocalStore,
    source: ScreenFrameSource,
    environment: ScreenEnvironmentSource,
    ingest: ScreenIngestClient?,
    deviceName: String
  ) {
    self.store = store
    self.source = source
    self.environment = environment
    self.ingest = ingest
    self.deviceName = deviceName
  }

  func setStatusSink(_ sink: (@Sendable (ScreenStatusEvent) -> Void)?) {
    statusSink = sink
  }

  func setIngestClient(_ client: ScreenIngestClient?) {
    ingest = client
  }

  func currentStatus() -> ScreenStatusResult {
    statusResult()
  }

  func start() async -> ScreenStartResult {
    if running {
      return ScreenStartResult(sessionId: sessionId ?? "", state: state)
    }
    state = .starting
    reason = nil
    emit()
    let granted = ScreenSystemEnvironment.preflightGranted()
    if !granted {
      state = .error
      reason = "permission"
      emit()
      return ScreenStartResult(sessionId: "", state: .error)
    }
    sessionId = UUID().uuidString.lowercased()
    running = true
    state = .recording
    emit()
    loopTask = Task { await self.runLoop() }
    ingestTask = Task { await self.runIngestLoop() }
    _ = store.sweepIfDue(now: Date())
    return ScreenStartResult(sessionId: sessionId ?? "", state: .recording)
  }

  func stop() async -> ScreenStopResult {
    running = false
    loopTask?.cancel()
    ingestTask?.cancel()
    loopTask = nil
    ingestTask = nil
    store.finishWriter()
    state = .idle
    reason = nil
    sessionId = nil
    emit()
    return ScreenStopResult(state: .idle)
  }

  func processInjected(_ frame: ScreenCapturedFrame) async -> ScreenIndexRow? {
    await process(frame: frame, env: environment.snapshot())
  }

  func exclusionsList() -> ScreenExclusionsListResult {
    ScreenExclusionsListResult(bundleIds: store.exclusions)
  }

  func exclusionsSet(_ bundleIds: [String], omiBundleId: String) async -> ScreenExclusionsSetResult
  {
    _ = fence.bump()
    while !fence.isDrained {
      await Task.yield()
    }
    let result = store.setExclusions(bundleIds, omiBundleId: omiBundleId)
    emit()
    return ScreenExclusionsSetResult(bundleIds: result.bundleIds, retiredFrameRefs: result.retired)
  }

  func retentionSet(_ days: Int) async -> ScreenRetentionSetResult {
    let normalized = ScreenRetentionPolicy.normalize(days)
    let retired = store.setRetentionDays(normalized, now: Date())
    if let ingest {
      _ = try? ingest.putRetention(days: normalized)
      _ = ScreenIngestSync.collectRetired(store: store, client: ingest)
    }
    emit()
    return ScreenRetentionSetResult(days: normalized, retiredFrameRefs: retired)
  }

  func rebuildIndex() -> ScreenRebuildIndexResult {
    let result = store.rebuildIndex()
    return ScreenRebuildIndexResult(frames: result.frames, chunks: result.chunks)
  }

  func frameImage(frameRef: String, maxLongEdge: Int?) throws -> ScreenFrameImageResult {
    let (image, width, height) = try store.decodeFrame(frameRef: frameRef, maxLongEdge: maxLongEdge)
    guard let encoded = ScreenImaging.pngBase64(image, maxLongEdge: nil) else {
      throw ScreenStoreError.decodeFailed
    }
    return ScreenFrameImageResult(pngBase64: encoded.0, width: width, height: height)
  }

  func requestPermission() async -> ScreenPermissionResult {
    store.markRequestedPermission()
    let granted = ScreenSystemEnvironment.requestAccessWhileFrontmost()
    if granted {
      await ScreenCaptureKitSource.primeConsent()
    }
    emit()
    return ScreenPermissionResult(permission: permission())
  }

  func openSettings() -> ScreenOpenSettingsResult {
    ScreenOpenSettingsResult(opened: ScreenSystemEnvironment.openScreenCaptureSettings())
  }

  private func runLoop() async {
    while running && !Task.isCancelled {
      let now = Date()
      if now.timeIntervalSince(lastPreflightCheck) >= 1 {
        lastPreflightCheck = now
        if !ScreenSystemEnvironment.preflightGranted() {
          state = .error
          reason = "permission-revoked"
          running = false
          emit()
          break
        }
      }
      let env = environment.snapshot()
      if env.screenSharingActive {
        sharingBackoffUntil = ScreenCadencePolicy.nextSharingBackoff(now: now)
      }
      if ScreenExclusionPolicy.videoCallBundleIds.contains(env.frontmostBundleId) {
        videoCallTick += 1
      } else {
        videoCallTick = 0
      }
      var hamming: Int?
      var preview: ScreenCapturedFrame?
      do {
        preview = try await source.captureFocused(excluded: Set(store.exclusions))
      } catch {
        state = .error
        reason = "capture-failed"
        emit()
        preview = nil
      }
      if let preview {
        let hash = ScreenImaging.dhash64(preview.image)
        if let last = lastStoredDHash {
          hamming = ScreenDHash.hamming(hash, last)
        }
        let input = ScreenCadenceInput(
          now: now,
          lastCaptureAt: lastCaptureAt,
          lastAnchorAt: lastAnchorAt,
          lastAppBundleId: lastAppBundleId,
          lastWindowTitle: lastWindowTitle,
          appBundleId: preview.appBundleId,
          windowTitle: preview.windowTitle,
          onBattery: env.onBattery,
          idleSeconds: env.idleSeconds,
          mediaPlaying: env.mediaPlaying,
          locked: env.locked,
          screensaver: env.screensaver,
          loginwindow: env.loginwindow,
          frontmostIsScreenshotApp: env.frontmostIsScreenshotApp,
          screenSharingActive: env.screenSharingActive,
          sharingBackoffUntil: sharingBackoffUntil,
          excluded: store.isExcluded(preview.appBundleId),
          dhashHammingFromLastStored: hamming,
          heartbeatSeconds: ScreenCadencePolicy.defaultHeartbeat,
          videoCallTick: videoCallTick)
        switch ScreenCadencePolicy.decide(input) {
        case .skip(let skipReason):
          if skipReason == "dhash-static" { lastCaptureAt = now }
          if skipReason == "lock" || skipReason == "screensaver" || skipReason == "loginwindow"
            || skipReason == "screen-sharing"
          {
            if state == .recording {
              state = .paused
              reason = skipReason
              emit()
            }
          }
        case .capture(let captureReason):
          if state == .paused {
            state = .recording
            reason = nil
            emit()
          }
          lastAppBundleId = preview.appBundleId
          lastWindowTitle = preview.windowTitle
          lastCaptureAt = now
          if captureReason == "anchor" { lastAnchorAt = now }
          _ = await process(frame: preview, env: env, precomputedHash: hash)
        }
      }
      try? await Task.sleep(nanoseconds: 1_000_000_000)
    }
    store.finishWriter()
  }

  private func runIngestLoop() async {
    while running && !Task.isCancelled {
      if let ingest, let sessionId {
        _ = ScreenIngestSync.flush(
          store: store, client: ingest, sessionId: sessionId, deviceName: deviceName, now: Date())
        _ = ScreenIngestSync.collectRetired(store: store, client: ingest)
      }
      _ = store.sweepIfDue(now: Date())
      try? await Task.sleep(nanoseconds: 2_000_000_000)
    }
  }

  private func process(
    frame: ScreenCapturedFrame,
    env: ScreenEnvironmentSnapshot,
    precomputedHash: UInt64? = nil
  ) async -> ScreenIndexRow? {
    if store.isExcluded(frame.appBundleId) { return nil }
    let capturedGeneration = fence.beginWork()
    defer { fence.endWork() }
    let hash = precomputedHash ?? ScreenImaging.dhash64(frame.image)
    let hex = ScreenDHash.hex(hash)
    var ocrHamming: Int?
    if let last = lastOCRDHash {
      ocrHamming = ScreenDHash.hamming(hash, last)
    }
    let runOCR = ScreenCadencePolicy.shouldOCR(
      capturedCount: capturedCount, hammingFromLastOCR: ocrHamming)
    var ocr: ScreenOCRAttachment?
    if runOCR {
      ocr = ScreenOCR.recognize(frame.image)
      lastOCRDHash = hash
    }
    capturedCount += 1
    lastStoredDHash = hash
    let allowWrite = fence.canWrite(capturedGeneration: capturedGeneration)
    do {
      let row = try store.appendFrame(
        image: frame.image,
        capturedAt: frame.capturedAt,
        appBundleId: frame.appBundleId,
        appName: frame.appName,
        windowTitle: frame.windowTitle,
        dhash: hex,
        ocr: ocr,
        allowWrite: allowWrite)
      lastAnchorAt = lastAnchorAt ?? frame.capturedAt
      emit()
      return row
    } catch {
      return nil
    }
  }

  private func permission() -> ScreenPermission {
    let mapped = ScreenPermissionPolicy.map(
      preflightGranted: ScreenSystemEnvironment.preflightGranted(),
      hasRequested: store.hasRequestedPermission)
    switch mapped {
    case "granted": return .granted
    case "denied": return .denied
    default: return .undetermined
    }
  }

  private func statusResult() -> ScreenStatusResult {
    ScreenStatusResult(
      state: state,
      reason: reason,
      permission: permission(),
      framesStored: store.framesStored,
      bytesOnDisk: store.bytesOnDisk,
      lastCaptureAt: lastCaptureAt.map(ScreenTime.wireTimestamp))
  }

  private func emit() {
    let status = statusResult()
    let event = ScreenStatusEvent(
      state: status.state,
      reason: status.reason,
      permission: status.permission,
      framesStored: status.framesStored,
      bytesOnDisk: status.bytesOnDisk,
      lastCaptureAt: status.lastCaptureAt)
    statusSink?(event)
  }
}
