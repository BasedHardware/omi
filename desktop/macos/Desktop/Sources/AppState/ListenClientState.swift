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
  typealias SurfaceTransport = (@MainActor () -> [String: Any]) async throws -> Bool

  private var reportTask: Task<Void, Never>?
  private var reportInFlight = false
  private var reportPending = false
  private var lastReportedOpen = false
  private let surfaceReportingEnabled: Bool
  private let surfaceOpen: (() -> Bool)?
  private let surfaceTransport: SurfaceTransport
  private weak var closingWindow: NSWindow?

  static func surfaceReportURL(baseURL: String) -> URL? {
    URL(string: baseURL)?.appendingPathComponent("v1/users/client-state")
  }

  private func isSurfaceOpen() -> Bool {
    if let surfaceOpen { return surfaceOpen() }
    let window = ShellSummon.shellWindow()
    return window != nil && window !== closingWindow && window?.isVisible == true
      && window?.isMiniaturized == false && window?.occlusionState.contains(.visible) == true && !NSApp.isHidden
  }

  func reportSurface(heartbeat: Bool = false) {
    guard surfaceReportingEnabled else { return }
    if heartbeat && !isSurfaceOpen() && !reportPending && !lastReportedOpen { return }
    // Keep a latest-state report owed while auth or transport is suspended.
    reportPending = true
    guard !reportInFlight else { return }
    reportInFlight = true
    reportTask = Task { @MainActor [weak self] in
      guard let self else { return }
      defer { self.reportInFlight = false }
      while self.reportPending {
        self.reportPending = false
        var sentOpen = false
        do {
          let delivered = try await self.surfaceTransport {
            // Read visibility after asynchronous URL/header preparation, just before send.
            sentOpen = self.isSurfaceOpen()
            return [
              "session_id": self.surfaceSession, "surface_open": sentOpen,
              "foreground": self.snapshot.foreground, "transcript_visible": self.snapshot.transcriptVisible,
            ]
          }
          guard delivered else {
            if self.reportPending { continue }
            self.reportPending = true
            break
          }
          self.lastReportedOpen = sentOpen
        } catch {
          if self.reportPending { continue }
          // Retry even a closed surface on the next heartbeat; never spin on network failure.
          self.reportPending = true
          break
        }
      }
    }
  }

  func waitForSurfaceReportsForTest() async {
    await reportTask?.value
  }

  private static func postSurface(_ latest: @MainActor () -> [String: Any]) async throws -> Bool {
    guard let authorization = RuntimeOwnerIdentity.captureAuthorizationSnapshot() else { return false }
    let baseURL = await APIClient.shared.baseURL
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization),
      let url = surfaceReportURL(baseURL: baseURL)
    else { return false }
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.timeoutInterval = 5
    request.allHTTPHeaderFields = try await APIClient.shared.buildHeaders(
      requireAuth: true, includeBYOK: false, expectedAuthOwnerId: authorization.ownerID)
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { return false }
    request.httpBody = try JSONSerialization.data(withJSONObject: latest())
    let (_, response) = try await URLSession.shared.data(for: request)
    return (response as? HTTPURLResponse).map { (200..<300).contains($0.statusCode) } ?? false
  }

  private var foreground: Bool
  private var visibleSurfaces: Set<UUID> = []
  private var observers: [NSObjectProtocol] = []

  init(
    foreground: Bool? = nil, observeApplication: Bool = true,
    surfaceReportingEnabled: Bool? = nil, surfaceOpen: (() -> Bool)? = nil,
    surfaceTransport: SurfaceTransport? = nil
  ) {
    self.surfaceReportingEnabled =
      surfaceReportingEnabled
      ?? (ProcessInfo.processInfo.environment["DEMAND_PROCESSING_SURFACE_REPORTING_ENABLED"] == "true")
    self.surfaceOpen = surfaceOpen
    self.surfaceTransport = surfaceTransport ?? Self.postSurface
    let initial = foreground ?? NSApplication.shared.isActive
    self.foreground = initial
    self.snapshot = Snapshot(foreground: initial, transcriptVisible: false)
    guard observeApplication else { return }
    if self.surfaceReportingEnabled {
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
    if self.surfaceReportingEnabled {
      for name in [
        NSWindow.didChangeOcclusionStateNotification, NSWindow.didMiniaturizeNotification,
        NSWindow.didDeminiaturizeNotification, NSWindow.willCloseNotification, NSWindow.didBecomeKeyNotification,
        NSApplication.didHideNotification, NSApplication.didUnhideNotification,
      ] {
        observers.append(
          center.addObserver(forName: name, object: nil, queue: .main) { [weak self] notification in
            let window = notification.object as? NSWindow
            MainActor.assumeIsolated {
              if name == NSWindow.willCloseNotification {
                self?.closingWindow = window
              } else if let window,
                window === self?.closingWindow, window.isVisible,
                window.occlusionState.contains(.visible)
              {
                self?.closingWindow = nil
              }
              self?.reportSurface()
            }
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
