import AppKit
import Combine
import SwiftUI

/// What the user can see of a live capture, reported to `/v4/listen` as
/// `{"type":"client_state","foreground":bool,"transcript_visible":bool}`.
///
/// The backend uses it for live visibility telemetry and STT routing.
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

  @Published private(set) var snapshot: Snapshot

  private var foreground: Bool
  private var visibleSurfaces: Set<UUID> = []
  private var observers: [AnyCancellable] = []

  init(
    foreground: Bool? = nil, observeApplication: Bool = true,
    notificationCenter: NotificationCenter = .default
  ) {
    let initial = foreground ?? NSApplication.shared.isActive
    self.foreground = initial
    self.snapshot = Snapshot(foreground: initial, transcriptVisible: false)
    guard observeApplication else { return }
    observers = [
      (NSApplication.didBecomeActiveNotification, true),
      (NSApplication.didResignActiveNotification, false),
    ].map { name, isActive in
      let observer = notificationCenter.addObserver(forName: name, object: nil, queue: .main) { [weak self] _ in
        MainActor.assumeIsolated { self?.setForeground(isActive) }
      }
      return AnyCancellable { notificationCenter.removeObserver(observer) }
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
