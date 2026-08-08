import OmiTheme
import SwiftUI

//  The Omi mark, the wordmark, and the one object they become — beats 2, 3 and 4.
//
//  The geometry is the eight-dot Omi logo, authored on a 260-unit canvas: four dots on the axes at
//  radius 86.71 and four on the diagonals at 91.92, so the mark reads as a ring rather than as a
//  square. `angle(i) = i·π/4` clockwise from due north, and `direction(θ) = (sin θ, −cos θ)`, which
//  lands correctly in SwiftUI's y-down space.
//
//  Beat 2 draws the mark by *arrival*. There is no outline to stroke on — the mark is eight fills —
//  so the honest animation is placement: one `placed` progress walks 0 → 1, dot `i` takes
//  `clamp(placed·8 − i, 0, 1)` of it (`OmiCinematicMarkDraw.arrival`), and the director steps
//  `placed` once per dot under a spring so each one lands with a little overshoot next to its own
//  click. When the last dot is down, the mark takes over its own comet pulse — the same 0.9 s lap,
//  0.5 idle brightness and 0.18 pulse width the mark uses everywhere else — so the hand-off from
//  "being drawn" to "alive" is a change of driver rather than a change of drawing.
//
//  Beats 3 and 4 are one object changing shape, and there is deliberately no
//  `matchedGeometryEffect`: nothing here ever changes view identity. The mark, the wordmark and the
//  shell are the same three views from beat 2 to beat 5, and only their frames and offsets move —
//  so SwiftUI interpolates real continuity rather than being asked to fake it across an identity
//  break.

// MARK: - Palette

/// The cinematic's colours.
///
/// Deliberately **not** the app's semantic ladder, and this is the one surface where that is
/// correct. The app's tokens colour a *panel*, and flip with the system appearance so a panel is a
/// panel in both. The cinematic is not a panel — it is a dimmed *desktop*, and "dim" has to mean
/// darker in both appearances. Handing this surface to a semantic label colour would draw
/// near-black type on a near-black scrim in Light.
///
/// So: the scrim is black and everything on it is white, at the alphas the app uses for the same
/// roles. White is also exactly the neutral `INV-UI-1` asks for, and this surface spends no accent
/// at all — the intro has one thing to look at per beat and a hue would be a second.
enum OmiCinematicPalette {
  /// The dim over the desktop. Not fully opaque: the last few per cent keep the user's own desktop
  /// faintly present, so the intro reads as happening *on their Mac*.
  static let scrim = Color.black.opacity(0.96)
  /// The mark, the wordmark, the typed question.
  static let ink = Color.white
  /// A line someone reads rather than the headline.
  static let inkSecondary = Color.white.opacity(0.58)
  /// The edge of the prompt shell and of a window card.
  static let hairline = Color.white.opacity(0.20)
  /// The prompt shell's fill.
  static let shellFill = Color.white.opacity(0.07)
  /// A window card's ground.
  static let cardFill = Color.white.opacity(0.06)
}

// MARK: - Geometry

/// The eight-dot Omi mark's geometry and its comet pulse.
enum OmiCinematicMark {
  /// The canvas the geometry was authored on; every value below is in this space and scales.
  static let canvas: CGFloat = 260
  static let centre: CGFloat = 129.5
  static let dotRadius: CGFloat = 17.2
  /// Dots 0/2/4/6 — N, E, S, W.
  static let axisRadius: CGFloat = 86.71
  /// Dots 1/3/5/7. Further out, so the mark reads as a ring rather than a square.
  static let diagonalRadius: CGFloat = 91.92
  static let glowBlur: CGFloat = 9
  static let glowOpacity: Double = 0.3

  /// One full lap of the pulse.
  static let lapSeconds: Double = 0.9
  /// How far a dot dims between pulses, and how wide the travelling bright spot is as a fraction of
  /// a lap. 0.18 against a 0.125 dot spacing gives a comet rather than a blink.
  static let idleBrightness: Double = 0.5
  static let pulseWidth: Double = 0.18

  /// Dot centres in canvas space.
  static let dotCentres: [CGPoint] = (0..<OmiCinematicMarkDraw.dotCount).map { index in
    let theta = Double(index) * .pi / 4
    let radius = index.isMultiple(of: 2) ? axisRadius : diagonalRadius
    return CGPoint(
      x: centre + radius * CGFloat(sin(theta)),
      y: centre - radius * CGFloat(cos(theta))
    )
  }

  /// 1 when the mark is static; a travelling bump between `idleBrightness` and 1 while pulsing.
  static func brightness(index: Int, phase: Double?) -> Double {
    guard let phase else { return 1 }
    let peak = Double(index) / Double(OmiCinematicMarkDraw.dotCount)
    var distance = abs(phase - peak)
    if distance > 0.5 { distance = 1 - distance }
    let bump = max(0, 1 - distance / pulseWidth)
    return idleBrightness + (1 - idleBrightness) * bump
  }

  /// Where the comet is at `date`, as a fraction of a lap. Pure, so a frame of the pulse is a value
  /// a test can assert rather than a moment it has to wait for.
  static func phase(at date: Date) -> Double {
    (date.timeIntervalSinceReferenceDate / lapSeconds).truncatingRemainder(dividingBy: 1)
  }
}

// MARK: - The mark

/// The Omi mark, arriving one dot at a time and then pulsing.
///
/// Drawn as eight `Circle` views rather than into a `Canvas`, and that is load-bearing: the arrival
/// is an animated `Double` on the director, and SwiftUI can only interpolate it through animatable
/// modifiers (`scaleEffect`, `opacity`). A `Canvas` closure re-reads the value but is never
/// interpolated, so the same code inside one would snap through eight discrete steps.
struct OmiCinematicMarkView: View {
  var draw: OmiCinematicMarkDraw
  var size: CGFloat
  /// True once every dot has landed. The pulse never runs during the arrival.
  var pulsing: Bool = false
  var color: Color = OmiCinematicPalette.ink

  private var isPulsing: Bool { pulsing && !OmiMotion.reduceMotion }
  private var scale: CGFloat { size / OmiCinematicMark.canvas }

  var body: some View {
    Group {
      if isPulsing {
        TimelineView(.animation(minimumInterval: 1.0 / 30.0, paused: false)) { timeline in
          ring(phase: OmiCinematicMark.phase(at: timeline.date))
        }
      } else {
        ring(phase: nil)
      }
    }
    .frame(width: size, height: size)
    .accessibilityHidden(true)
  }

  private func ring(phase: Double?) -> some View {
    ZStack {
      ForEach(0..<OmiCinematicMarkDraw.dotCount, id: \.self) { index in
        dot(index: index, level: OmiCinematicMark.brightness(index: index, phase: phase))
      }
    }
    .frame(width: size, height: size)
  }

  private func dot(index: Int, level: Double) -> some View {
    let diameter = OmiCinematicMark.dotRadius * 2 * scale
    let position = OmiCinematicMark.dotCentres[index]
    return ZStack {
      Circle()
        .fill(color)
        .blur(radius: OmiCinematicMark.glowBlur * scale)
        .opacity(OmiCinematicMark.glowOpacity * level)
      Circle()
        .fill(color)
        .opacity(level)
    }
    // The pulse is a function of the clock and must never be animated: inside a beat's transaction
    // it would lag a frame behind itself and smear. The arrival's own scale and opacity are applied
    // *outside* this, so they still ride the director's spring.
    .transaction { $0.animation = nil }
    .frame(width: diameter, height: diameter)
    .scaleEffect(OmiCinematicMarkDraw.entranceScale(dot: index, placed: draw.placed))
    .opacity(OmiCinematicMarkDraw.arrival(dot: index, placed: draw.placed))
    .position(x: position.x * scale, y: position.y * scale)
  }
}

// MARK: - The vessel

/// The metrics of the one object beats 2–5 share, per form.
///
/// Every field is interpolated by SwiftUI because the views holding them never change identity —
/// see the note at the top of this file.
struct OmiCinematicVesselMetrics: Equatable {
  /// The mark's rendered box.
  var markSize: CGFloat
  /// The mark's offset from the composition's centre.
  var markOffset: CGSize
  /// The shell — nothing in beat 2, a bar in beat 3, a prompt field in beats 4–5.
  var shellSize: CGSize
  var shellOpacity: Double
  /// The wordmark under the mark in beat 2, gone by beat 3.
  var wordmarkOffset: CGSize
  var wordmarkOpacity: Double
  var wordmarkScale: CGFloat
  /// The typed question inside the shell.
  var questionOpacity: Double
  /// How far in from the shell's leading edge the question starts — the mark's slot.
  var questionInset: CGFloat

  static func metrics(for form: OmiCinematicForm) -> OmiCinematicVesselMetrics {
    switch form {
    case .mark:
      // The shell already exists at the wordmark's own footprint, at zero opacity, so beat 3 is a
      // bar *growing out of the wordmark* rather than a bar appearing over it.
      return OmiCinematicVesselMetrics(
        markSize: 132,
        markOffset: CGSize(width: 0, height: -56),
        shellSize: CGSize(width: 260, height: 46),
        shellOpacity: 0,
        wordmarkOffset: CGSize(width: 0, height: 62),
        wordmarkOpacity: 1,
        wordmarkScale: 1,
        questionOpacity: 0,
        questionInset: 44)
    case .bar:
      return OmiCinematicVesselMetrics(
        markSize: 30,
        markOffset: CGSize(width: -104, height: 0),
        shellSize: CGSize(width: 268, height: 52),
        shellOpacity: 1,
        wordmarkOffset: .zero,
        wordmarkOpacity: 0,
        wordmarkScale: 0.68,
        questionOpacity: 0,
        questionInset: 44)
    case .prompt:
      return OmiCinematicVesselMetrics(
        markSize: 28,
        markOffset: CGSize(width: -(Self.promptWidth / 2 - 30), height: 0),
        shellSize: CGSize(width: Self.promptWidth, height: Self.promptShellHeight),
        shellOpacity: 1,
        wordmarkOffset: .zero,
        wordmarkOpacity: 0,
        wordmarkScale: 0.6,
        questionOpacity: 1,
        questionInset: 56)
    }
  }

  /// The prompt's width, and therefore the width of the card grid under it — the grid is three
  /// cards across and lines up with the field exactly.
  static let promptWidth: CGFloat = 560
  /// The prompt shell's height. The composition centres a block of this plus the grid.
  static let promptShellHeight: CGFloat = 58
  /// The fixed box the vessel is laid out in, so growing the shell never moves the composition's
  /// centre — the shell stretches, the layout does not.
  static let stageHeight: CGFloat = 220
}

/// The mark, the wordmark, the shell and the typed question, as one object.
struct OmiCinematicVessel: View {
  var draw: OmiCinematicMarkDraw
  var form: OmiCinematicForm
  var pulsing: Bool
  var question: String
  var showsCaret: Bool
  /// Reduce Motion: the caret stops blinking too.
  var animatesCaret: Bool

  private var metrics: OmiCinematicVesselMetrics { .metrics(for: form) }

  var body: some View {
    let m = metrics
    ZStack {
      shell(m)
      questionField(m)
      wordmark(m)
      OmiCinematicMarkView(draw: draw, size: m.markSize, pulsing: pulsing)
        .offset(x: m.markOffset.width, y: m.markOffset.height)
    }
    // A fixed box so the composition's centre does not move as the shell grows — the shell is what
    // stretches, not the layout around it.
    .frame(
      width: OmiCinematicVesselMetrics.promptWidth,
      height: OmiCinematicVesselMetrics.stageHeight,
      alignment: .center)
  }

  private func shell(_ m: OmiCinematicVesselMetrics) -> some View {
    Capsule(style: .continuous)
      .fill(OmiCinematicPalette.shellFill)
      .overlay(
        Capsule(style: .continuous)
          .strokeBorder(OmiCinematicPalette.hairline, lineWidth: 1)
      )
      .frame(width: m.shellSize.width, height: m.shellSize.height)
      .opacity(m.shellOpacity)
  }

  /// "omi", resolving under the mark. `draw.wordmark` is its own sub-beat, so every dot is down
  /// before a letter of it is legible.
  private func wordmark(_ m: OmiCinematicVesselMetrics) -> some View {
    Text(verbatim: "omi")
      .font(.openRunde(40, .semiBold))
      .tracking(1.5)
      .foregroundStyle(OmiCinematicPalette.ink)
      .opacity(draw.wordmark * m.wordmarkOpacity)
      // Resolves *out* of a blur rather than out of nothing: at this size a plain opacity ramp
      // reads as a label switching on.
      .blur(radius: (1 - draw.wordmark) * 9)
      .scaleEffect(m.wordmarkScale)
      .offset(x: m.wordmarkOffset.width, y: m.wordmarkOffset.height)
      .fixedSize()
  }

  /// The typed question, and the caret that follows it.
  ///
  /// `.center` and deliberately **not** `.firstTextBaseline`: `OmiCinematicCaret` is a `Rectangle`,
  /// and SwiftUI resolves both text baselines of a view containing no text to its own *bottom
  /// edge*, so under baseline alignment the caret hangs its whole height above the baseline instead
  /// of straddling it and drags the stack off the shell's centre. `barHeight` is exactly the line
  /// box the text is laid out in, and concentric with that line box is where a text caret goes — so
  /// centring *reaches* baseline alignment's intended result along the one axis SwiftUI can measure
  /// here without being told the face's ascent.
  private func questionField(_ m: OmiCinematicVesselMetrics) -> some View {
    HStack(alignment: .center, spacing: 3) {
      Text(verbatim: question)
        .font(.openRunde(OmiCinematicCaret.questionPointSize))
        .foregroundStyle(OmiCinematicPalette.ink)
        .fixedSize()
      OmiCinematicCaret(visible: showsCaret, animated: animatesCaret)
      Spacer(minLength: 0)
    }
    .padding(.leading, m.questionInset)
    .padding(.trailing, 22)
    .frame(width: m.shellSize.width, height: m.shellSize.height, alignment: .leading)
    .opacity(m.questionOpacity)
    .clipShape(Capsule(style: .continuous))
  }
}

/// The prompt's caret. Blinks on macOS's own cadence; static under Reduce Motion, where a blinking
/// bar is exactly the kind of motion the setting is asking us to stop.
struct OmiCinematicCaret: View {
  var visible: Bool
  var animated: Bool

  /// The period macOS blinks a text caret at.
  nonisolated static let blinkSeconds: Double = 1.06

  /// The size the question is set at. `barHeight` tracks it; changing one without the other leaves
  /// the caret the wrong height for the line it belongs to.
  static let questionPointSize: CGFloat = 17

  /// The bar's height, and the reason `questionField` can centre rather than baseline-align it.
  /// One line box tall at `questionPointSize`, rounded away from the baseline the way TextKit
  /// rounds ascender and descender.
  static let barHeight: CGFloat = 21

  /// Phase as a pure function of the clock, so the caret does not need state and cannot get out of
  /// step with itself across a re-render. `nonisolated` because SwiftUI infers main-actor isolation
  /// for members of a `View` and this is arithmetic.
  nonisolated static func isOn(at date: Date) -> Bool {
    let half = blinkSeconds / 2
    return Int((date.timeIntervalSinceReferenceDate / half).rounded(.down)).isMultiple(of: 2)
  }

  var body: some View {
    Group {
      if animated {
        TimelineView(.periodic(from: .now, by: Self.blinkSeconds / 2)) { context in
          bar.opacity(Self.isOn(at: context.date) ? 1 : 0.12)
        }
      } else {
        bar
      }
    }
    .opacity(visible ? 1 : 0)
    .accessibilityHidden(true)
  }

  private var bar: some View {
    Rectangle()
      .fill(OmiCinematicPalette.ink)
      .frame(width: 2, height: Self.barHeight)
  }
}
