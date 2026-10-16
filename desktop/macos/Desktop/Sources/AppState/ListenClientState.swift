import AppKit
import Combine
import SwiftUI

/// What the user can see of a live capture, reported to `/v4/listen` as
/// `{"type":"client_state","foreground":bool,"transcript_visible":bool}`.
///
/// The backend uses it to measure how much live time anyone actually watches in
/// real time (backend routers/listen/realtime_demand.py). It never changes routing.
/// `foreground` is `NSApp.isActive`; `transcriptVisible` is "some live-transcript
/// surface is on screen and the app is active". No transcript surface renders while
/// the app is inactive (the floating bar shows none), so requiring both is exact.
@MainActor
final class ListenClientState: ObservableObject {
  struct Snapshot: Equatable, Sendable {
    let foreground: Bool
    let transcriptVisible: Bool

    var jsonObject: [String: Any] {
      ["type": "client_state", "foreground": foreground, "transcript_visible": transcriptVisible]
    }
  }

  static let shared = ListenClientState()

  static func startSurfaceReporting() {
    guard ProcessInfo.processInfo.environment["DEMAND_PROCESSING_SURFACE_REPORTING_ENABLED"] == "true" else { return }
    _ = shared
  }

  @Published private(set) var snapshot: Snapshot

  private var heartbeat: Timer?
  private let surfaceSession = UUID().uuidString
  private var reportInFlight = false

  static func surfaceReportURL(baseURL: String) -> URL? {
    URL(string: baseURL)?.appendingPathComponent("v1/users/client-state")
  }

  private func reportSurface(heartbeat: Bool = false) {
    guard ProcessInfo.processInfo.environment["DEMAND_PROCESSING_SURFACE_REPORTING_ENABLED"] == "true",
      !reportInFlight
    else { return }
    guard let authorization = RuntimeOwnerIdentity.captureAuthorizationSnapshot() else { return }
    let clientState = snapshot
    let window = ShellSummon.shellWindow()
    let open =
      window?.isVisible == true && window?.isMiniaturized == false
      && window?.occlusionState.contains(.visible) == true && !NSApp.isHidden
    if heartbeat && !open { return }
    reportInFlight = true
    Task { @MainActor [weak self] in
      guard let self else { return }
      defer { self.reportInFlight = false }
      do {
        let baseURL = await APIClient.shared.baseURL
        guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization),
          let url = Self.surfaceReportURL(baseURL: baseURL)
        else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 5
        request.allHTTPHeaderFields = try await APIClient.shared.buildHeaders(
          requireAuth: true, includeBYOK: false, expectedAuthOwnerId: authorization.ownerID)
        guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { return }
        request.httpBody = try JSONSerialization.data(withJSONObject: [
          "session_id": self.surfaceSession, "surface_open": open,
          "foreground": clientState.foreground, "transcript_visible": clientState.transcriptVisible,
        ])
        _ = try await URLSession.shared.data(for: request)
      } catch { /* Best effort; the server lease expires without renewal. */  }
    }
  }

  private var foreground: Bool
  private var visibleSurfaces: Set<UUID> = []
  private var observers: [NSObjectProtocol] = []

  init(foreground: Bool? = nil, observeApplication: Bool = true) {
    let initial = foreground ?? NSApplication.shared.isActive
    self.foreground = initial
    self.snapshot = Snapshot(foreground: initial, transcriptVisible: false)
    guard observeApplication else { return }
    if ProcessInfo.processInfo.environment["DEMAND_PROCESSING_SURFACE_REPORTING_ENABLED"] == "true" {
      heartbeat = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { [weak self] _ in
        Task { @MainActor in self?.reportSurface(heartbeat: true) }
      }
      reportSurface()
    }
    let center = NotificationCenter.default
    observers = [
      center.addObserver(forName: NSApplication.didBecomeActiveNotification, object: nil, queue: .main) {
        [weak self] _ in
        MainActor.assumeIsolated { self?.setForeground(true) }
      },
      center.addObserver(forName: NSApplication.didResignActiveNotification, object: nil, queue: .main) {
        [weak self] _ in
        MainActor.assumeIsolated { self?.setForeground(false) }
      },
    ]
    if ProcessInfo.processInfo.environment["DEMAND_PROCESSING_SURFACE_REPORTING_ENABLED"] == "true" {
      for name in [
        NSWindow.didChangeOcclusionStateNotification, NSWindow.didMiniaturizeNotification,
        NSWindow.didDeminiaturizeNotification, NSWindow.willCloseNotification,
      ] {
        observers.append(
          center.addObserver(forName: name, object: nil, queue: .main) { [weak self] _ in
            MainActor.assumeIsolated { self?.reportSurface() }
          })
      }
    }
  }

  func setForeground(_ value: Bool) {
    foreground = value
    publish()
  }

  func setSurface(_ id: UUID, visible: Bool) {
    if visible {
      visibleSurfaces.insert(id)
    } else {
      visibleSurfaces.remove(id)
    }
    publish()
  }

  private func publish() {
    let next = Snapshot(foreground: foreground, transcriptVisible: foreground && !visibleSurfaces.isEmpty)
    if next != snapshot { snapshot = next }
    reportSurface()
  }
}

/// Registers the modified view as an on-screen live-transcript surface while it is shown.
private struct LiveTranscriptVisibilityReporter: ViewModifier {
  @State private var token = UUID()

  func body(content: Content) -> some View {
    content
      .onAppear { ListenClientState.shared.setSurface(token, visible: true) }
      .onDisappear { ListenClientState.shared.setSurface(token, visible: false) }
  }
}

extension View {
  /// Count this view as a visible live transcript for `/v4/listen` client_state reporting.
  func reportsLiveTranscriptVisibility() -> some View {
    modifier(LiveTranscriptVisibilityReporter())
  }
}
