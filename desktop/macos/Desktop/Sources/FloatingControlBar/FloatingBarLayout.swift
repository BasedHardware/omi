import AppKit
import VoiceTurnDomain

/// Typed voice phase for floating-bar sizing and chrome.
///
/// `isVoiceListening` and `isVoicePresentationActive` overloaded several
/// live states (capture, a failure hint, thinking, spoken response) into
/// booleans. A layout reader that needs the capture waveform is not the same
/// as one that needs the hold-longer banner, and treating them as one boolean
/// is how the island settled at the wrong width.
enum FloatingBarVoicePhase: Equatable, Sendable {
  case idle
  case listening
  case thinking
  case hint
  case responding

  static func from(_ projection: VoiceTurnUIProjection) -> Self {
    if projection.isListening { return .listening }
    if !projection.hint.isEmpty { return .hint }
    if projection.isThinking { return .thinking }
    if projection.isResponseActive || projection.isResponseWaiting { return .responding }
    return .idle
  }

  /// Any phase that reserves the closed surface so hover/idle collapse cannot
  /// steal the island.
  var reservesSurface: Bool {
    self != .idle
  }

  /// Capture is live. A failure hint is a different phase and must not reuse
  /// this for waveform chrome.
  var isCapturing: Bool {
    self == .listening
  }

  /// The historical `isVoiceListening` boolean: capture *or* a hint that
  /// kept that flag true. Prefer the typed cases at new call sites.
  var isListeningOrHint: Bool {
    self == .listening || self == .hint
  }
}

/// One pure layout snapshot both the SwiftUI view and the window read.
///
/// Lobe width, chrome width, the drawn surface, and the closed surface are
/// derived from the same inputs so a hover menu, a card, or a voice phase
/// cannot paint one size and settle the window at another.
struct FloatingBarLayout: Equatable {
  var voicePhase: FloatingBarVoicePhase
  var lobeWidth: CGFloat
  var chromeWidth: CGFloat
  var chromeHeight: CGFloat
  var drawnSurface: NSSize
  var closedSurface: NSSize

  struct Metrics: Equatable {
    var compactSideWidth: CGFloat
    var activeSideWidth: CGFloat
    var voiceSideWidth: CGFloat
    var thinkingSideWidth: CGFloat
    var hiddenCenterWidth: CGFloat
    var chromeHeight: CGFloat
    var expandedWidth: CGFloat
    var hoverMenuHeight: CGFloat
    var minBarSize: NSSize
    var voiceBarSize: NSSize
  }

  /// Side width of one notch lobe. Capture uses the voice control; thinking
  /// uses the thinking mark; everything else that is not compact idle uses
  /// the active lobe.
  static func lobeWidth(
    phase: FloatingBarVoicePhase,
    isChatPresented: Bool,
    hasAgentPills: Bool,
    metrics: Metrics
  ) -> CGFloat {
    if phase.isCapturing { return metrics.voiceSideWidth }
    if isChatPresented {
      return hasAgentPills ? metrics.activeSideWidth : metrics.compactSideWidth
    }
    if phase == .thinking { return metrics.thinkingSideWidth }
    if !hasAgentPills && !phase.reservesSurface {
      return metrics.compactSideWidth
    }
    return metrics.activeSideWidth
  }

  static func chromeWidth(lobeWidth: CGFloat, hiddenCenterWidth: CGFloat) -> CGFloat {
    hiddenCenterWidth + lobeWidth * 2
  }

  /// The black chrome the view draws: idle island, or idle plus the hover
  /// menu hanging under it. Cards, banners, and conversation are composed
  /// on top of this by the window's closed-surface authority.
  static func drawnSurface(
    chromeWidth: CGFloat,
    chromeHeight: CGFloat,
    hoverMenuVisible: Bool,
    hoverMenuHeight: CGFloat,
    expandedWidth: CGFloat
  ) -> NSSize {
    if hoverMenuVisible {
      return NSSize(
        width: max(chromeWidth, expandedWidth),
        height: chromeHeight + hoverMenuHeight
      )
    }
    return NSSize(width: chromeWidth, height: chromeHeight)
  }

  static func make(
    phase: FloatingBarVoicePhase,
    isChatPresented: Bool,
    hasAgentPills: Bool,
    hoverMenuVisible: Bool,
    metrics: Metrics,
    closedSurface: NSSize
  ) -> FloatingBarLayout {
    let lobe = lobeWidth(
      phase: phase,
      isChatPresented: isChatPresented,
      hasAgentPills: hasAgentPills,
      metrics: metrics
    )
    let chrome = chromeWidth(lobeWidth: lobe, hiddenCenterWidth: metrics.hiddenCenterWidth)
    return FloatingBarLayout(
      voicePhase: phase,
      lobeWidth: lobe,
      chromeWidth: chrome,
      chromeHeight: metrics.chromeHeight,
      drawnSurface: drawnSurface(
        chromeWidth: chrome,
        chromeHeight: metrics.chromeHeight,
        hoverMenuVisible: hoverMenuVisible,
        hoverMenuHeight: metrics.hoverMenuHeight,
        expandedWidth: metrics.expandedWidth
      ),
      closedSurface: closedSurface
    )
  }
}

extension FloatingControlBarGeometry {
  /// Closed-conversation chrome size from a typed voice phase. A mounted
  /// notification card still wins; listening/thinking may only grow it.
  static func collapsedSurfaceSize(
    hasMountedNotification: Bool,
    phase: FloatingBarVoicePhase,
    notificationSize: NSSize,
    listeningSize: NSSize,
    thinkingSize: NSSize,
    idleSize: NSSize
  ) -> NSSize {
    collapsedSurfaceSize(
      hasMountedNotification: hasMountedNotification,
      isVoiceListening: phase.isListeningOrHint,
      isThinking: phase == .thinking || phase == .responding,
      notificationSize: notificationSize,
      listeningSize: listeningSize,
      thinkingSize: thinkingSize,
      idleSize: idleSize
    )
  }
}
