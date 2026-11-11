//
//  OmiQueryDotMark.swift — the eight-dot Omi mark at the leading edge of the query bar.
//
//  Eight dots on a ring. **At rest it does not move**, and that is the whole point: the mark turns
//  only while Omi is working on a turn, so turning *means* something. A mark that turns forever is a
//  spinner, and a spinner that is always on tells the user the app is always loading — a claim about
//  the app's own state that is false in every resting frame. It also costs a repaint every frame for
//  as long as the window is open, which measured as the only moving region on an otherwise static
//  surface and roughly a tenth of a core.
//
//  The two states differ by more than speed, so the difference survives both a still frame and
//  Reduce Motion:
//    - resting: eight dots at one opacity. No leading edge, so the ring reads as a mark.
//    - working: opacity descends around the ring — giving it a leading edge to read rotation from —
//      and the ring turns. With eight *equal* dots the rotation would be invisible anyway, because
//      every frame would look like every other one, which is why the ramp and the motion arrive
//      together and leave together.
//
//  Brand: `Ink.primary` at alphas and nothing else (INV-UI-1).
//

import OmiTheme
import SwiftUI

/// The mark's two states, and the motion each one is allowed, as plain values.
///
/// Split out from the view because the contract worth testing is not "does it look right" but "does
/// it ask the run loop for anything". A `View` body cannot be asked whether it is about to repaint;
/// this can be asked whether it hands out an animation at all.
enum OmiQueryMarkMotion {
  /// One full turn while working. There is deliberately no resting period: resting does not turn,
  /// so there is no duration to name.
  static let workingPeriod: Double = 1.6

  /// Descending opacity around the ring, starting at the top. The first dot is solid so there is an
  /// unambiguous leading edge to read the rotation from.
  static let workingAlphas: [Double] = [1, 0.82, 0.64, 0.5, 0.4, 0.34, 0.46, 0.62]

  /// The single opacity every dot rests at.
  ///
  /// Flat on purpose. A still ring that still carries the working ramp is a *stopped* spinner — one
  /// bright dot frozen at an arbitrary angle — which reads as stuck rather than as idle. Flattening
  /// the ramp is what turns the same eight dots back into a mark.
  static let restingAlpha: Double = 0.58

  static var dotCount: Int { workingAlphas.count }

  static func alphas(isWorking: Bool) -> [Double] {
    isWorking ? workingAlphas : Array(repeating: restingAlpha, count: dotCount)
  }

  /// Whether the ring is driven by a repeating animation at all — which is to say, whether this view
  /// asks for a frame when nothing about it has changed.
  ///
  /// Reduce Motion switches the rotation *off* rather than slowing it down: "animate this more
  /// gently" is not what the setting asks for. The working state stays legible without it because
  /// the opacity ramp is a state cue in its own right, which is exactly why the ramp and the
  /// rotation are two switches and not one.
  static func turns(isWorking: Bool, reduceMotion: Bool) -> Bool {
    isWorking && !reduceMotion
  }
}

struct OmiQueryDotMark: View {
  var diameter: CGFloat = QueryShellLayout.markDiameter
  /// Turns the mark while a turn is in flight. `false` is a *still* mark, not a slower one.
  var isWorking: Bool = false

  private var dotDiameter: CGFloat { diameter * 0.17 }
  private var ringRadius: CGFloat { (diameter - dotDiameter) / 2 }

  /// Read at evaluation time, which is the same discipline every other `InkReduceMotion` call site
  /// in the system uses — the setting is a call, not a stored copy that can go stale.
  private var turns: Bool {
    OmiQueryMarkMotion.turns(isWorking: isWorking, reduceMotion: InkReduceMotion.isEnabled)
  }

  var body: some View {
    Group {
      // Two branches rather than one branch handing `.animation` a `nil`. A `repeatForever` outlives
      // the value that started it: nilling the animation on the way back to rest leaves the running
      // repeat in place and the mark keeps turning — and keeps repainting — forever. Swapping the
      // branch destroys the animated subtree outright, which is the only version of "stop" the run
      // loop honours.
      if turns {
        ring.modifier(ContinuousTurn(period: OmiQueryMarkMotion.workingPeriod))
      } else {
        ring
      }
    }
    .frame(width: diameter, height: diameter)
    .accessibilityHidden(true)
  }

  private var ring: some View {
    let alphas = OmiQueryMarkMotion.alphas(isWorking: isWorking)
    return ZStack {
      ForEach(Array(alphas.enumerated()), id: \.offset) { index, alpha in
        Circle()
          .fill(Ink.primary.opacity(alpha))
          .frame(width: dotDiameter, height: dotDiameter)
          .offset(y: -ringRadius)
          .rotationEffect(.degrees(Double(index) / Double(alphas.count) * 360))
      }
    }
    // The ramp fades in and out so entering and leaving the working state is a transition rather
    // than a jump. It is driven by `isWorking`, so it runs once per state change and then stops.
    .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.settle)), value: isWorking)
  }
}

/// A ring that turns for exactly as long as it exists.
///
/// The rotation starts from `onAppear` rather than from a value change because this modifier is only
/// ever in the tree while the mark is working: its lifetime *is* the working state, so there is no
/// "stop" for it to express. Being removed is the stop.
private struct ContinuousTurn: ViewModifier {
  let period: Double

  @State private var angle: Double = 0

  func body(content: Content) -> some View {
    content
      .rotationEffect(.degrees(angle))
      .onAppear {
        withAnimation(.linear(duration: period).repeatForever(autoreverses: false)) {
          angle = 360
        }
      }
  }
}
