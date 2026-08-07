//
//  ShellStatusIcons.swift — the top bar's right cluster: microphone, screen capture, settings.
//
//  **Icons only, no words.** The old cluster spelled out `Listening` and `Capture` as filled pills,
//  which is two paragraphs of chrome permanently occupying the corner of a window whose whole point is
//  the search field in the middle of it. The two things a label was carrying are carried instead by
//  the two cues an icon can hold without spending any width: a **state dot**, which says on / off /
//  needs-attention at a glance, and a **tooltip**, which says the whole sentence to anyone who asks.
//
//  A wordless control has to be legible without its label, so the dot is not optional and it is not
//  decorative. Every button here is on when its dot is filled green, off when the dot is hollow, and
//  blocked when it is filled with the error colour — one vocabulary across all of them, which is what
//  makes the cluster readable at all.
//
//  **The glyph names the capability; the dot reports the toggle.** A control that redraws its glyph
//  when it is switched on is doing the dot's job a second time and doing it worse: the user has to
//  learn two shapes to recognise one button, and two adjacent controls that each swap silhouette stop
//  reading as two capabilities at all. The one thing a glyph may say besides its name is that the
//  capability is *unavailable* — a slash — which is not a toggle position and never competes with the
//  dot, because a blocked control is never also on.
//
//  It drives `CaptureListeningLogic` — the same functions the old pills and Home's header call — so
//  this is a second *rendering* of the capture state and never a second copy of the behaviour.
//
//  Brand: `Ink` semantics and system colours only (INV-UI-1).
//

import OmiTheme
import SwiftUI

// MARK: - The dot

/// The live-state dot on a wordless control.
///
/// **The ring makes the mark visible; the fill says which state it is.** Those are two different jobs
/// and the shipped dot conflated them, which is why the cluster read as "two identical buttons with
/// two identical badges".
///
/// `Ink.listeningGreen` and `Ink.errorRed` are `systemGreen` and `systemRed`, and on this panel
/// neither of them can carry visibility on its own: measured against the glass ground over the two
/// desktops that bound the range, green lands at **1.28:1** and red at **1.25:1** over a black
/// desktop. That is not a tuning problem — it is what a saturated mid-luminance hue does against a
/// light ground, and no alpha fixes it. So visibility is the *ring's* job (WCAG 2.1 SC 1.4.11 asks
/// for 3:1 on a graphic's **boundary**), and the hue is left free to do the only thing it is good at,
/// which is naming the state.
///
/// Two things follow, and both are the opposite of what shipped:
///
/// - **The ring is ink, not ground.** It was `Ink.surface` — the panel's own colour — on the theory
///   that a halo of the ground separates the dot from whatever is under it. But this panel is pinned
///   light, so the ground is light over *both* desktops (152/255 and 243/255) and a light halo on it
///   measures 2.61:1 and 1.10:1: invisible exactly where it was needed. An edge that separates a mark
///   from a light ground has to be darker than the ground, so it is `Ink.primary` at the weight that
///   clears 3:1 on the darker of the two.
/// - **The ring is drawn outside the fill, not inside it.** `strokeBorder` insets, so a 1.5 pt ring on
///   the fill's own 6.5 pt frame left **3.5 pt** of colour — a little over a third of the 9.5 pt slot
///   the layout reserves, and the reason the state read as a speck. The numbers below are unchanged
///   from the ones that shipped; they are simply now the numbers that render.
struct ShellStatusDot: View {
  let state: HomeStatusState

  /// The coloured core. The layout reserves `diameter + 2 * ringWidth`, which is where 9.5 comes from.
  static let diameter: CGFloat = 6.5
  static let ringWidth: CGFloat = 1.5

  /// The edge that makes the dot a mark rather than a tint.
  ///
  /// A floor, not a taste. `Ink.primary` resolves to black on the pinned-light panel; the glass ground
  /// over a *white* desktop is 243/255 and needs α ≥ 0.42 to clear 3:1, over a *black* desktop it is
  /// 152/255 and needs α ≥ 0.51. Then the whole of a 1.5 pt stroke on a 9.5 pt circle is curve, and
  /// antialiasing renders it at roughly three-quarters of its nominal alpha — measured, not assumed —
  /// so the number that lands on 3:1 is the arithmetic floor over that loss, not the floor itself.
  /// `ShellStatusIconLegibilityTests` reads the value back off the rendered pixels for this reason.
  static let ring = Ink.primary.opacity(0.72)

  /// The whole vocabulary of a wordless control, as a function rather than a `switch` inside a
  /// `body`: three states must land on three *distinguishable* fills, and "off" must never resolve
  /// to something a glance reads as "on". That is a claim a test can hold only if it can call this.
  ///
  /// "Off" is `.clear` — a **hollow** dot, not a faint one. Faint was the old answer and it measured
  /// 1.57:1 over a light desktop, i.e. a control reporting nothing at all. Empty-versus-filled is the
  /// one distinction that survives at this size (it is what a radio button is made of), it needs no
  /// third colour, and it is genuinely the quietest of the three in ink while being the equal of them
  /// in legibility, because the ring is what is being read.
  static func fill(for state: HomeStatusState) -> Color {
    switch state {
    case .active: return Ink.listeningGreen
    case .inactive: return .clear
    case .blocked: return Ink.errorRed
    }
  }

  private static var outerDiameter: CGFloat { diameter + ringWidth * 2 }

  var body: some View {
    ZStack {
      Circle()
        .fill(Self.fill(for: state))
        .frame(width: Self.diameter, height: Self.diameter)
      Circle()
        .strokeBorder(Self.ring, lineWidth: Self.ringWidth)
    }
    .frame(width: Self.outerDiameter, height: Self.outerDiameter)
    .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.press)), value: state)
  }
}

// MARK: - The glyphs

/// One glyph per capability, chosen here rather than inline so a test can assert the rule the header
/// states: the glyph is the control's *name*, and a name does not change when the thing is toggled.
enum ShellStatusGlyph {
  /// The listening control, in every state it can actually be toggled between.
  ///
  /// It used to draw `waveform` while transcribing and `mic` while idle. Two problems, one cause: the
  /// silhouette changed with the toggle, so the button appeared to become a different button; and
  /// `waveform` shares **56%** of its rendered pixels with the screen glyph beside it (measured), so
  /// the two live controls collapsed into one repeated wide smear precisely when both were on — the
  /// state in which telling them apart matters most.
  static let listening = "mic"

  /// Transcription cannot run. Availability, not a toggle position — see the header.
  static let listeningBlocked = "mic.slash"

  /// The screen-capture control.
  ///
  /// `rectangle.inset.filled.and.person.filled` was an unusual composite, and its problem was never
  /// contrast — rendered on the glass it measures the same 4.06:1 / 5.72:1 as everything else here.
  /// It was **interior detail at 13 pt**: a filled slab with a figure inset into it, where the figure
  /// is the whole of what distinguishes the symbol and is also the first thing to dissolve. What is
  /// left is a slab. It also claims a *person on a screen*, which is a meeting, not what this control
  /// does.
  ///
  /// `display` is the conventional macOS glyph for the screen itself — which is exactly what the
  /// tooltip claims ("Capturing your screen") — and it survives the size because it has no interior
  /// detail to lose: one wide rounded rectangle on a short pedestal.
  ///
  /// Honest about the silhouette numbers, because they only tell half the story. Against `mic` the
  /// new pair shares 34% of its pixels and the old one shared 31% — a wash. The 56% is what the old
  /// pair measured **while listening**, when the mic became `waveform`; that is the state the reported
  /// screenshot was in, and it is fixed by `listening` above rather than by this line.
  static let screen = "display"

  /// The listening control's glyph. Availability is the only input, because it is the only thing
  /// about this control that a glyph is allowed to say.
  static func listeningGlyph(isBlocked: Bool) -> String {
    isBlocked ? listeningBlocked : listening
  }
}

// MARK: - The button

/// One wordless control: a glyph, its state dot, and the sentence the dot is short for.
struct ShellStatusIconButton: View {
  let systemImage: String
  /// The whole sentence, shown on hover and read by VoiceOver. Never abbreviated — this is the only
  /// place the removed label still exists.
  let tooltip: String
  let state: HomeStatusState
  var isBusy: Bool = false
  /// Settings has no live state of its own; passing `false` drops the dot entirely rather than
  /// drawing a permanently faint one, which would read as "off".
  var showsDot: Bool = true
  var isSelected: Bool = false
  let action: () -> Void

  var body: some View {
    Button(action: action) {
      Group {
        if isBusy {
          ProgressView().controlSize(.small)
        } else {
          Image(systemName: systemImage)
            .scaledFont(size: OmiType.body, weight: .semibold)
        }
      }
      .overlay(alignment: .topTrailing) {
        if showsDot {
          ShellStatusDot(state: state).offset(x: 6, y: -5)
        }
      }
    }
    .buttonStyle(GlassIconButtonStyle(isActive: isSelected || state == .active))
    .help(tooltip)
    .accessibilityLabel(Text(tooltip))
    .accessibilityAddTraits(state == .active ? .isSelected : [])
  }
}

// MARK: - The cluster

/// Microphone and screen capture — the two live-state controls of the top bar's right cluster.
///
/// The settings gear sits beside them but is deliberately *not* in here: it is navigation, not
/// capture, and `TopNavigationBarLayout` pins it to the lane's trailing edge as its own slot so the
/// two capture icons can shrink and reflow without the way out of the page moving.
struct ShellStatusIcons: View {
  @ObservedObject var appState: AppState

  @State private var isCaptureMonitoring = false
  @State private var isTogglingCapture = false
  @State private var isTogglingListening = false

  @AppStorage("screenAnalysisEnabled") private var screenAnalysisEnabled = true
  @AppStorage("transcriptionEnabled") private var transcriptionEnabled = true
  @AppStorage("systemAudioCaptureMode") private var systemAudioCaptureModeRaw =
    AssistantSettings.SystemAudioCaptureMode.onlyDuringMeetings.rawValue

  var body: some View {
    HStack(spacing: 2) {
      ShellStatusIconButton(
        systemImage: listeningGlyph,
        tooltip: listeningTooltip,
        state: listeningState,
        isBusy: isTogglingListening,
        action: toggleListening
      )
      .accessibilityIdentifier("shell-status-listening")

      ShellStatusIconButton(
        systemImage: ShellStatusGlyph.screen,
        tooltip: captureTooltip,
        state: captureState,
        isBusy: isTogglingCapture,
        action: toggleCapture
      )
      .accessibilityIdentifier("shell-status-capture")
    }
    .onAppear(perform: syncCaptureState)
    .onReceive(NotificationCenter.default.publisher(for: .screenCapturePermissionLost)) { _ in
      syncCaptureState()
    }
    .onReceive(NotificationCenter.default.publisher(for: .screenCaptureKitBroken)) { _ in
      syncCaptureState()
    }
  }

  // MARK: Derived state

  private var transcriptionUnavailable: Bool { appState.transcriptionServiceError != nil }

  private var listeningState: HomeStatusState {
    if transcriptionUnavailable { return .blocked }
    return appState.isTranscribing ? .active : .inactive
  }

  private var listeningGlyph: String {
    ShellStatusGlyph.listeningGlyph(isBlocked: transcriptionUnavailable)
  }

  /// The sentence the dot is short for. It names the *mode* as well as the state, because "listening"
  /// with no qualifier is the claim the meetings-only mode does not actually make.
  private var listeningTooltip: String {
    if transcriptionUnavailable {
      return "Transcription unavailable — open Settings to reconnect"
    }
    let mode = CaptureListeningLogic.listeningModeTitle(
      appState: appState, raw: systemAudioCaptureModeRaw)
    return appState.isTranscribing
      ? "Listening — \(mode). Click to stop."
      : "Not listening. Click to start."
  }

  private var captureState: HomeStatusState {
    CaptureListeningLogic.captureStatus(appState: appState, isCaptureMonitoring: isCaptureMonitoring)
  }

  private var captureTooltip: String {
    switch captureState {
    case .blocked:
      return "Screen capture needs permission — click to grant it"
    case .active:
      return "Capturing your screen — Rewind is recording. Click to stop."
    case .inactive:
      return "Screen capture is off — nothing is being recorded. Click to start."
    }
  }

  // MARK: Actions — the shared logic, never a second copy

  private func toggleListening() {
    OmiUISound.play(appState.isTranscribing ? .captureEnd : .captureStart)
    CaptureListeningLogic.toggleListening(
      appState: appState,
      transcriptionEnabled: $transcriptionEnabled,
      isTogglingListening: $isTogglingListening)
  }

  private func toggleCapture() {
    OmiUISound.play(captureState == .active ? .captureEnd : .captureStart)
    CaptureListeningLogic.toggleCapture(
      appState: appState, screenAnalysisEnabled: $screenAnalysisEnabled,
      isCaptureMonitoring: $isCaptureMonitoring, isTogglingCapture: $isTogglingCapture)
  }

  private func syncCaptureState() {
    CaptureListeningLogic.syncCaptureState(
      screenAnalysisEnabled: $screenAnalysisEnabled, isCaptureMonitoring: $isCaptureMonitoring)
  }
}
