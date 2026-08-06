//
//  OmiQueryDotMark.swift — the eight-dot Omi mark at the leading edge of the query bar.
//
//  Eight dots on a ring at descending opacity, turning slowly. The descending opacity is what makes a
//  ring of identical circles read as *turning* at all: with eight equal dots the rotation is invisible
//  because every frame looks like every other one.
//
//  It is not decoration. The mark turns at a resting pace and quickens while Omi is actually working
//  on a turn, so the one always-visible piece of brand on the surface is also the surface's only
//  ambient "I am doing something" signal — which is the job a spinner would otherwise be added for.
//
//  Brand: `Ink.primary` at alphas and nothing else (INV-UI-1).
//

import OmiTheme
import SwiftUI

struct OmiQueryDotMark: View {
  var diameter: CGFloat = QueryShellLayout.markDiameter
  /// Quickens the turn while a turn is in flight.
  var isWorking: Bool = false

  @State private var isTurning = false

  /// Descending opacity around the ring, starting at the top. The first dot is solid so there is an
  /// unambiguous leading edge to read the rotation from.
  private static let alphas: [Double] = [1, 0.82, 0.64, 0.5, 0.4, 0.34, 0.46, 0.62]

  private var restingPeriod: Double { 9 }
  private var workingPeriod: Double { 1.6 }
  private var period: Double { isWorking ? workingPeriod : restingPeriod }

  private var dotDiameter: CGFloat { diameter * 0.17 }
  private var ringRadius: CGFloat { (diameter - dotDiameter) / 2 }

  var body: some View {
    ZStack {
      ForEach(Array(Self.alphas.enumerated()), id: \.offset) { index, alpha in
        Circle()
          .fill(Ink.primary.opacity(alpha))
          .frame(width: dotDiameter, height: dotDiameter)
          .offset(y: -ringRadius)
          .rotationEffect(.degrees(Double(index) / Double(Self.alphas.count) * 360))
      }
    }
    .frame(width: diameter, height: diameter)
    .rotationEffect(.degrees(isTurning ? 360 : 0))
    // Rebuilt whenever the pace changes so the new duration takes effect on the next cycle rather
    // than being ignored for the life of the running animation.
    .animation(turn, value: isTurning)
    .animation(turn, value: isWorking)
    .onAppear { isTurning = true }
    .accessibilityHidden(true)
  }

  /// `nil` under Reduce Motion, which is how SwiftUI spells "do not animate this" — a mark that spins
  /// forever is exactly the kind of perpetual motion the setting exists to stop.
  private var turn: Animation? {
    InkReduceMotion.animation(.linear(duration: period).repeatForever(autoreverses: false))
  }
}
