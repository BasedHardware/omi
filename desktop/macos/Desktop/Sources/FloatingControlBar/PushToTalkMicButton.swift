import OmiTheme
import SwiftUI

/// The visible push-to-talk affordance shared by the main-window chat composer
/// and the floating ask bar. Push-to-talk used to be reachable only by holding
/// a modifier key; this is the clickable equivalent.
///
/// It is a trigger, not a capture path. Every click enters the single
/// `PushToTalkManager` state machine the keyboard shortcut drives, so there is
/// no second audio lifecycle and no second transcript writer. A click carries
/// no "hold", so it takes the hands-free lane the double-tap shortcut already
/// uses: click to start locked listening, click again to send.
///
/// **It renders on two grounds that are not the same colour**, and that is what its palette is built
/// around. The main window's composer is light-pinned glass; the floating ask bar is the notch pill's
/// black glass. Its first version was drawn in the legacy dark palette — a hardcoded `#FFFFFF`
/// listening ring and a fixed grey glyph — which compiled, drew, and was invisible in the composer.
/// Every colour below is either dynamic (`Ink.*`, which resolves against whichever ground it is on)
/// or a system semantic, so neither call site has to know which surface it is.
struct PushToTalkMicButton: View {
  /// Glyph tint while idle so each composer can match its own chrome. `Ink.secondary` and not the
  /// third rung: this sits on glass, which carries two rungs (see `Ink.tertiary`).
  var idleTint: Color = Ink.secondary
  var diameter: CGFloat = 32
  var glyphSize: CGFloat = OmiType.heading

  @ObservedObject private var manager = PushToTalkManager.shared
  @ObservedObject private var usageLimiter = FloatingBarUsageLimiter.shared
  @ObservedObject private var shortcutSettings = ShortcutSettings.shared

  @State private var isHovering = false

  private var state: PushToTalkButtonState { manager.pushToTalkButtonState }

  var body: some View {
    Button(action: { manager.togglePushToTalkFromButton() }) {
      ZStack {
        // Green rather than the palette's accent: "on" has to read as on without a label, and this is
        // the one job `Ink.listeningGreen` exists for. The old white ring said nothing on a dark
        // surface and nothing at all on a light one.
        Circle().fill(state == .listening ? Ink.listeningGreen.opacity(0.16) : hoverFill)
        glyph
      }
      .frame(width: diameter, height: diameter)
      .contentShape(Circle())
    }
    .buttonStyle(.plain)
    .onHover { isHovering = $0 }
    // Colour only, never scale — a control this size bouncing reads as a toy, and on a translucent
    // panel a scaling shape drags its own wash across the desktop behind it.
    .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.press)), value: isHovering)
    .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.press)), value: state)
    .help(helpText)
    .accessibilityLabel(Text(accessibilityLabel))
    // Deliberately never `.disabled` while blocked: a disabled button swallows
    // the click, and a blocked click must surface the usage-limit popup.
    .accessibilityAddTraits(state == .listening ? .isSelected : [])
  }

  /// Nothing at rest. A wash on `labelColor`, so it darkens the light composer and lightens the pill
  /// from one value.
  private var hoverFill: Color { isHovering ? Ink.rowFill : .clear }

  @ViewBuilder
  private var glyph: some View {
    switch state {
    case .listening:
      // Same waveform the floating bar shows while listening, so both surfaces
      // read from one mic level rather than inventing a second animation.
      VoiceWaveformBars(isActive: true)
        .scaleEffect(0.75)
    case .committing:
      ProgressView()
        .controlSize(.small)
    case .idle:
      Image(systemName: "mic")
        .scaledFont(size: glyphSize, weight: .medium)
        .foregroundColor(idleTint)
    case .blocked:
      // Derived from the caller's tint rather than a fourth fixed grey: "unavailable" is the idle
      // glyph turned down, and it has to stay turned down by the same amount on both grounds.
      Image(systemName: "mic.slash")
        .scaledFont(size: glyphSize, weight: .medium)
        .foregroundColor(idleTint.opacity(0.55))
    }
  }

  private var shortcutLabel: String { shortcutSettings.pttShortcut.displayLabel }

  private var helpText: String {
    switch state {
    case .idle:
      return "Ask by voice — click to start, click again to send (or hold \(shortcutLabel))"
    case .listening:
      return "Stop and send (or press \(shortcutLabel))"
    case .committing:
      return "Sending your voice message…"
    case .blocked:
      return "Monthly free message limit reached — click to see your options"
    }
  }

  private var accessibilityLabel: String {
    switch state {
    case .idle: return "Start voice input"
    case .listening: return "Stop voice input and send"
    case .committing: return "Sending voice input"
    case .blocked: return "Voice input unavailable, monthly message limit reached"
    }
  }
}
