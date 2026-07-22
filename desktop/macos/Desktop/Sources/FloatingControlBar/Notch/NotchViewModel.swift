import AppKit
import Combine
import SwiftUI

/// Per-display source of truth for one notch panel: the authoritative
/// closed/open toggle, tab selection, dynamic chat height, and all sizing.
/// The window frame is fixed (sized to the largest any presentation can need);
/// only the inner content resizes, so every expansion visually originates from
/// the notch.
@MainActor
final class NotchViewModel: ObservableObject {
  enum State: Equatable {
    case closed
    case open
  }

  @Published private(set) var state: State = .closed
  @Published var selectedTab: NotchTab = .chat
  @Published private(set) var closedNotchSize: CGSize
  /// Physical camera housing width (no padding) — chrome icons hug its edges.
  @Published private(set) var cameraWidth: CGFloat
  @Published private(set) var screenFrame: CGRect
  /// Chat body height as reported by the chat view's measure loop. Drives the
  /// dynamic panel height: the notch grows just enough to fit the current
  /// answer, capped at half the screen. Deliberately NOT part of
  /// `NotchPresentation` — it rides its own animation timeline.
  @Published var chatBodyHeight: CGFloat?
  /// Measured height of the live voice content (transcript while listening,
  /// streaming reply while responding). Drives the notch's grow as words wrap
  /// to new lines. Transient — a voice turn always starts fresh, so unlike
  /// `chatBodyHeight` it is not persisted. Rides the same isolated height
  /// timeline as chat.
  @Published var voiceBodyHeight: CGFloat?
  /// Agent drill-in within the agents tab (nil = the list).
  @Published var openAgentPillID: UUID?
  /// True while something must stay on screen regardless of the pointer.
  var holdOpen = false

  let displayID: CGDirectDisplayID
  private(set) var hasPhysicalNotch: Bool

  private weak var window: NSWindow?
  private var openedAt: Date?
  private var hoverOpenTask: Task<Void, Never>?
  /// Fired after every open/close so the screen manager can install pointer
  /// monitors only while a panel is open (zero mouse tracking while idle).
  var onStateChange: (() -> Void)?

  /// Injected time sources so the hover dwell and the post-open grace are
  /// testable without wall-clock sleeps.
  private let now: () -> Date
  private let sleep: (TimeInterval) async -> Void
  private let defaults: UserDefaults

  private static let chatBodyHeightKey = "notch.chatBodyHeight"

  init(
    displayID: CGDirectDisplayID,
    screenFrame: CGRect,
    hasPhysicalNotch: Bool,
    closedNotchSize: CGSize,
    cameraWidth: CGFloat = NotchMetrics.fallbackHiddenCenterWidth,
    now: @escaping () -> Date = { Date() },
    sleep: @escaping (TimeInterval) async -> Void = { try? await Task.sleep(for: .seconds($0)) },
    defaults: UserDefaults = .standard
  ) {
    self.now = now
    self.sleep = sleep
    self.defaults = defaults
    self.displayID = displayID
    self.screenFrame = screenFrame
    self.hasPhysicalNotch = hasPhysicalNotch
    self.closedNotchSize = closedNotchSize
    self.cameraWidth = cameraWidth
    // Seed the last-known chat height so the first open after launch morphs
    // straight to the right size instead of jumping min -> measured. The chat
    // view's measure loop corrects it on mount if the answer differs.
    if let saved = defaults.object(forKey: Self.chatBodyHeightKey) as? Double {
      chatBodyHeight = CGFloat(saved)
    }
  }

  convenience init(
    screen: NSScreen,
    now: @escaping () -> Date = { Date() },
    sleep: @escaping (TimeInterval) async -> Void = { try? await Task.sleep(for: .seconds($0)) }
  ) {
    self.init(
      displayID: screen.omiDisplayID,
      screenFrame: screen.frame,
      hasPhysicalNotch: NotchMetrics.screenHasCameraHousing(screen),
      closedNotchSize: NotchMetrics.closedSize(for: screen),
      cameraWidth: NotchMetrics.cameraWidth(
        auxiliaryTopLeftArea: screen.auxiliaryTopLeftArea,
        auxiliaryTopRightArea: screen.auxiliaryTopRightArea
      ),
      now: now,
      sleep: sleep
    )
  }

  // MARK: - Sizing

  /// Chrome above the chat body: header row (closed-chrome height) + paddings.
  private var chatChromeHeight: CGFloat { closedNotchSize.height + 8 + 16 }

  var chatMinHeight: CGFloat { clampValue(screenFrame.height * 0.09, 96, 124) }
  var chatMaxHeight: CGFloat { screenFrame.height * 0.5 }

  func openContentSize(for tab: NotchTab) -> CGSize {
    let width = clampValue(screenFrame.width * 0.32, 440, 540)
    switch tab {
    case .chat:
      let height =
        chatBodyHeight.map { clampValue($0 + chatChromeHeight, chatMinHeight, chatMaxHeight) }
        ?? chatMinHeight
      return CGSize(width: width, height: height)
    case .agents:
      return CGSize(width: width, height: clampValue(screenFrame.height * 0.34, 240, 400))
    }
  }

  var currentOpenContentSize: CGSize { openContentSize(for: selectedTab) }

  /// Fixed width for the expanded voice states (listening / responding); only
  /// the HEIGHT grows with the measured content, so the island grows downward
  /// out of the notch as the user speaks or the answer streams — the Dynamic
  /// Island grow, not a wide pop. Thinking narrows to a compact pill and the
  /// width morphs between them.
  var voiceWidth: CGFloat { clampValue(screenFrame.width * 0.27, 340, 430) }
  var voiceMinHeight: CGFloat { clampValue(closedNotchSize.height + 82, 120, 168) }

  var voiceExpandedSize: CGSize {
    let height = voiceBodyHeight.map { clampValue($0, voiceMinHeight, chatMaxHeight) } ?? voiceMinHeight
    return CGSize(width: voiceWidth, height: height)
  }

  /// The compact pill between listening and responding: camera strip + the orb
  /// (now the rotating ring), centered — no text. Distinctly narrower than the
  /// expanded voice width so the width visibly contracts into "thinking".
  var thinkingSize: CGSize {
    CGSize(width: clampValue(closedNotchSize.width * 0.6, 170, 215), height: closedNotchSize.height + 42)
  }

  var hintSize: CGSize {
    CGSize(
      width: clampValue(closedNotchSize.width + NotchMetrics.listeningExtraWidth, 280, 380),
      height: closedNotchSize.height + NotchMetrics.hintRowHeight)
  }

  var notificationSize: CGSize {
    CGSize(
      width: max(closedNotchSize.width, NotchMetrics.notificationSize.width),
      height: closedNotchSize.height + NotchMetrics.notificationSpacing + NotchMetrics.notificationSize.height)
  }

  /// The panel size for a presentation — the single sizing authority. Content
  /// (in NotchView) switches on the same value, so size and content stay locked.
  func size(for presentation: NotchPresentation) -> CGSize {
    switch presentation {
    case .open(let tab): return openContentSize(for: tab)
    case .listening, .responding: return voiceExpandedSize
    case .thinking: return thinkingSize
    case .hint: return hintSize
    case .notification: return notificationSize
    case .idle: return closedNotchSize
    }
  }

  /// The window is fixed at the largest any presentation can ever need; only
  /// the inner content scales, so expansion always originates from the notch.
  private var maxContentSize: CGSize {
    var size = CGSize(width: 0, height: chatMaxHeight)
    for tab in NotchTab.allCases {
      let tabSize = openContentSize(for: tab)
      size.width = max(size.width, tabSize.width)
      size.height = max(size.height, tabSize.height)
    }
    size.width = max(size.width, notificationSize.width)
    size.height = max(size.height, notificationSize.height)
    size.width = max(size.width, voiceWidth)
    return size
  }

  var windowSize: CGSize {
    CGSize(
      width: maxContentSize.width + NotchMetrics.shadowPadding * 2,
      height: maxContentSize.height + NotchMetrics.trayReserve + NotchMetrics.shadowPadding
    )
  }

  /// The visible black region in screen coordinates for the current state —
  /// used for authoritative hover hit-testing (the window itself is larger).
  func visibleRect(open: Bool) -> CGRect {
    let size = open ? currentOpenContentSize : closedNotchSize
    return CGRect(
      x: screenFrame.midX - size.width / 2,
      y: screenFrame.maxY - size.height,
      width: size.width,
      height: size.height
    )
  }

  /// The floating composer tray's region: directly below the body. Union'd
  /// with `visibleRect` for the auto-close hit region so moving onto the
  /// composer never reads as "left the panel".
  func trayRect(open: Bool) -> CGRect {
    let body = visibleRect(open: open)
    return CGRect(
      x: body.minX,
      y: body.minY - NotchMetrics.trayGap - NotchMetrics.trayHeight,
      width: body.width,
      height: NotchMetrics.trayHeight
    )
  }

  // MARK: - Window coordination

  func attach(window: NSWindow) {
    self.window = window
    positionWindow()
  }

  func refresh(for screen: NSScreen) {
    screenFrame = screen.frame
    hasPhysicalNotch = NotchMetrics.screenHasCameraHousing(screen)
    closedNotchSize = NotchMetrics.closedSize(for: screen)
    cameraWidth = NotchMetrics.cameraWidth(
      auxiliaryTopLeftArea: screen.auxiliaryTopLeftArea,
      auxiliaryTopRightArea: screen.auxiliaryTopRightArea
    )
    positionWindow()
  }

  /// Fixed geometry: centered horizontally, pinned to the top. Never animated.
  private func positionWindow() {
    guard let window else { return }
    let size = windowSize
    let origin = NSPoint(
      x: screenFrame.midX - size.width / 2,
      y: screenFrame.maxY - size.height
    )
    window.setFrame(NSRect(origin: origin, size: size), display: true)
  }

  // MARK: - Open / close

  /// Chat-first: every open lands on chat unless the caller asks for another
  /// tab (logo click opens agents).
  func open(tab: NotchTab = .chat) {
    cancelHoverTasks()
    selectedTab = tab
    guard state != .open else { return }
    state = .open
    openedAt = now()
    onStateChange?()
  }

  func close() {
    cancelHoverTasks()
    guard state != .closed else { return }
    state = .closed
    openedAt = nil
    openAgentPillID = nil
    // Persist the settled chat height to seed the next launch's first open.
    if let chatBodyHeight {
      defaults.set(Double(chatBodyHeight), forKey: Self.chatBodyHeightKey)
    }
    onStateChange?()
  }

  /// Grace period so the panel can't slam shut right after opening.
  var canAutoClose: Bool {
    guard state == .open, !holdOpen else { return false }
    guard let openedAt else { return true }
    return now().timeIntervalSince(openedAt) > 0.6
  }

  /// Voice-first notch: hover never opens anything. The closed notch is a
  /// passive identity + settings surface; the panel only expands for a voice
  /// turn (via the presentation ladder) or an explicit agents/notification
  /// open. Kept as a no-op (rather than removing the hover wiring) so the
  /// hover-driven shadow in `NotchView` still works.
  func hoverEntered(delay: TimeInterval = 0.28) {
    // ponytail: intentionally does nothing — hover-to-open is retired.
    hoverOpenTask?.cancel()
  }

  func hoverExited() {
    hoverOpenTask?.cancel()
  }

  func cancelHoverTasks() {
    hoverOpenTask?.cancel()
  }

  deinit {
    hoverOpenTask?.cancel()
  }
}

private func clampValue(_ value: CGFloat, _ low: CGFloat, _ high: CGFloat) -> CGFloat {
  min(max(value, low), high)
}
