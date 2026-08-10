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
//  **The glyph names the capability; the slash says it is not running; the dot says why.** A dot is a
//  9.5 pt mark that has to be *decoded* — hollow-versus-filled is a real distinction, but it is a
//  distinction you have to know the code for, and "off" is the state a user most needs to read without
//  being taught. So off also gets the mark that needs no teaching: a diagonal through the glyph, the
//  same one SF Symbols draws on every `.slash` variant. The dot stays, and keeps the job the slash
//  cannot do — separating *you switched this off* (hollow) from *something is blocking it* (red).
//
//  **The slash is drawn over the glyph, never instead of it.** The rejected design swapped `mic` for
//  `waveform` when listening: the silhouette changed with the toggle, so one button read as two, and
//  `waveform` shares 56% of its pixels with the screen glyph beside it — the two live controls
//  collapsed into one smear exactly when both were on. That failure came from *replacing* the
//  silhouette. `ShellStatusSlash` adds to it: the base glyph is byte-identical in every state and the
//  diagonal is additional ink on top, so the capability still reads from the shape and only the
//  running/not-running bit moves. `ShellStatusIconLegibilityTests` measures both halves of that claim.
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

// MARK: - The off-mark

/// The diagonal a control wears whenever its capability is **not running** — switched off, or blocked.
///
/// **Hand-drawn rather than taken from SF Symbols, because half the pair does not exist.** `mic.slash`
/// ships; `display.slash` does not (checked on the SDK this builds against). The choices were an
/// inconsistent cluster — Apple's slash on one control, something else on the other — or changing the
/// screen glyph to whichever symbol happens to have a `.slash` sibling, which is the tail wagging the
/// dog and would also put the two adjacent silhouettes back in play. One drawn mark used by both keeps
/// the cluster's rule intact: the same state wears the same mark on every control.
///
/// **It also keeps the base glyph exactly intact, which the SF variants do not.** `mic` → `mic.slash`
/// is a different symbol whose mic body is redrawn around the diagonal; an overlay leaves `mic`
/// literally unchanged underneath and only adds ink. That is the whole distinction between this and
/// the `waveform`/`mic` swap the header rejects, and it is what the legibility test measures.
///
/// Geometry is expressed as fractions of the glyph, never as points, so the mark tracks the glyph at
/// every Dynamic Type scale `scaledFont` produces instead of staying 13 pt on a 25 pt symbol.
struct ShellStatusSlash: Shape {
  /// Is the capability off? A shape rather than a branch in the caller's `body`, so the button's view
  /// identity is the same in both states and only the path it draws changes.
  var isOff: Bool
  /// The wider pass, punched out of the glyph beneath so the diagonal reads as a line laid *over* the
  /// shape rather than merging into its stems. SF Symbols carves the same clearance into its own
  /// `.slash` variants; on a translucent panel it has to be a real hole (`.destinationOut`) because
  /// there is no opaque ground colour to paint the gap with.
  var isClearance: Bool

  /// The square the diagonal spans, as a fraction of the glyph's shorter side. Taken from the shorter
  /// side because SF Symbols' canvas varies in aspect (`mic` renders 15×17, `display` 19×16 at 13 pt),
  /// and the shorter side is the more stable of the two — it keeps the mark the same size and the same
  /// angle on both controls, which is what makes it read as one shared vocabulary.
  static let extent: CGFloat = 0.78
  /// The diagonal's weight as a fraction of that square — matched to the semibold stems it crosses.
  static let weight: CGFloat = 0.105
  /// Clearance punched on each side of the diagonal, as a fraction of its weight.
  static let clearance: CGFloat = 0.6

  func path(in rect: CGRect) -> Path {
    guard isOff else { return Path() }
    let side = min(rect.width, rect.height) * Self.extent
    let square = CGRect(
      x: rect.midX - side / 2, y: rect.midY - side / 2, width: side, height: side)
    var line = Path()
    // Top-leading to bottom-trailing: the direction every `.slash` symbol in SF Symbols runs, so the
    // drawn mark and the system's own read as the same mark.
    line.move(to: CGPoint(x: square.minX, y: square.minY))
    line.addLine(to: CGPoint(x: square.maxX, y: square.maxY))

    let lineWidth = side * Self.weight
    return line.strokedPath(
      StrokeStyle(
        lineWidth: isClearance ? lineWidth * (1 + 2 * Self.clearance) : lineWidth,
        lineCap: .round))
  }
}

// MARK: - The glyphs

/// One glyph per capability, chosen here rather than inline so a test can assert the rule the header
/// states: the glyph is the control's *name*, and a name does not change — in any state.
enum ShellStatusGlyph {
  /// The listening control, in **every** state. There is no second listening symbol any more: off and
  /// blocked draw this same `mic` and add `ShellStatusSlash` on top, so there is nothing left in this
  /// type that could reintroduce a state-dependent silhouette.
  ///
  /// It used to draw `waveform` while transcribing and `mic` while idle. Two problems, one cause: the
  /// silhouette changed with the toggle, so the button appeared to become a different button; and
  /// `waveform` shares **56%** of its rendered pixels with the screen glyph beside it (measured), so
  /// the two live controls collapsed into one repeated wide smear precisely when both were on — the
  /// state in which telling them apart matters most.
  static let listening = "mic"

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
}

// MARK: - The sentence

/// What a wordless control says when you hover it, and what VoiceOver reads.
///
/// **It leads with the capability's name.** The shipped strings opened with the *state* — "Listening
/// — In meeting", "Not listening" — which answers a question the user can only be asking if they
/// already know which control they are pointing at. On a cluster whose entire premise is that the
/// labels were removed, the tooltip is the one place the label still exists, so it has to start by
/// being the label: **Audio**, **Screen**. The state follows it, then what to do about it.
///
/// Free functions over plain values rather than computed properties on the view, so the wording is
/// reachable from a test without standing up an `AppState`.
enum ShellStatusTooltip {
  /// `mode` is `CaptureListeningLogic.listeningModeTitle` — "In meeting", "Always", a named mic. The
  /// mode is not decoration: "listening" with no qualifier is a claim the meetings-only mode does not
  /// actually make.
  static func audio(state: HomeStatusState, mode: String) -> String {
    switch state {
    case .blocked:
      return "Audio — transcription unavailable. Open Settings to reconnect."
    case .active:
      return "Audio — listening (\(mode)). Click to stop."
    case .inactive:
      return "Audio — off. Nothing is being transcribed. Click to start."
    }
  }

  static func screen(state: HomeStatusState) -> String {
    switch state {
    case .blocked:
      return "Screen — capture needs permission. Click to grant it."
    case .active:
      return "Screen — capturing. Rewind is recording. Click to stop."
    case .inactive:
      return "Screen — off. Nothing is being recorded. Click to start."
    }
  }
}

// MARK: - The button

/// One wordless control: a glyph, the off-slash when its capability is not running, its state dot, and
/// the sentence the two marks are short for.
struct ShellStatusIconButton: View {
  let systemImage: String
  /// The whole sentence, shown on hover and read by VoiceOver. Never abbreviated — this is the only
  /// place the removed label still exists, so it opens with the capability's name (`ShellStatusTooltip`).
  let tooltip: String
  /// `nil` for a control with no live capability behind it. Settings is one: it is navigation, and a
  /// permanently hollow dot or a permanent slash on the gear would both report a state it does not
  /// have. Modelled as absence rather than as `.inactive` so that reading is unavailable.
  let state: HomeStatusState?
  var isBusy: Bool = false
  /// Suppresses **only** the dot, never the glyph or its slash.
  ///
  /// This is a test seam and is documented as one: `ShellStatusIconLegibilityTests` isolates the
  /// badge's pixels by rendering the same control with and without it and taking the difference, which
  /// is exact only while this flag moves nothing else. Product code leaves it alone and passes
  /// `state: nil` for a control that has no badge to draw.
  var showsDot: Bool = true
  var isSelected: Bool = false
  let action: () -> Void

  /// Not running: switched off, or blocked. A control with no live capability is never "off" — it has
  /// nothing to be off — which is what keeps the slash off the settings gear.
  private var isOff: Bool {
    guard let state else { return false }
    return state != .active
  }

  private var isActive: Bool { state == .active }

  var body: some View {
    Button(action: action) {
      Group {
        if isBusy {
          ProgressView().controlSize(.small)
        } else {
          Image(systemName: systemImage)
            .scaledFont(size: OmiType.body, weight: .semibold)
            // Punch the clearance out of the glyph, close the group so the hole cannot reach the
            // panel's own chrome, then lay the diagonal into it.
            .overlay { ShellStatusSlash(isOff: isOff, isClearance: true).blendMode(.destinationOut) }
            .compositingGroup()
            .overlay { ShellStatusSlash(isOff: isOff, isClearance: false) }
        }
      }
      .overlay(alignment: .topTrailing) {
        if let state, showsDot {
          ShellStatusDot(state: state).offset(x: 6, y: -5)
        }
      }
    }
    .buttonStyle(GlassIconButtonStyle(isActive: isSelected || isActive))
    .help(tooltip)
    .accessibilityLabel(Text(tooltip))
    .accessibilityAddTraits(isActive ? .isSelected : [])
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
        systemImage: ShellStatusGlyph.listening,
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

  private var listeningTooltip: String {
    ShellStatusTooltip.audio(
      state: listeningState,
      mode: CaptureListeningLogic.listeningModeTitle(
        appState: appState, raw: systemAudioCaptureModeRaw))
  }

  private var captureState: HomeStatusState {
    CaptureListeningLogic.captureStatus(appState: appState, isCaptureMonitoring: isCaptureMonitoring)
  }

  private var captureTooltip: String { ShellStatusTooltip.screen(state: captureState) }

  // MARK: Actions — the shared logic, never a second copy

  private func toggleListening() {
    CaptureListeningLogic.toggleListening(
      appState: appState,
      transcriptionEnabled: $transcriptionEnabled,
      isTogglingListening: $isTogglingListening)
  }

  private func toggleCapture() {
    CaptureListeningLogic.toggleCapture(
      appState: appState, screenAnalysisEnabled: $screenAnalysisEnabled,
      isCaptureMonitoring: $isCaptureMonitoring, isTogglingCapture: $isTogglingCapture)
  }

  private func syncCaptureState() {
    CaptureListeningLogic.syncCaptureState(
      screenAnalysisEnabled: $screenAnalysisEnabled, isCaptureMonitoring: $isCaptureMonitoring)
  }
}
