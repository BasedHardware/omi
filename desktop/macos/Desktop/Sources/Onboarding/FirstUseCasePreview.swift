import AppKit
import OmiTheme
import SwiftUI

/// The picture beside the chips: a sketch of the site the case opens, with the Omi bar over it
/// carrying the question. Drawn, not screenshotted, so it renders identically in both appearances,
/// weighs nothing, and cannot go stale against a site's real chrome.
///
/// Everything is an `Ink` alpha over the panel — the sketch is a diagram of *where* the ask happens,
/// not a brand reproduction, and a neutral sketch keeps the one dark element, the bar, the thing the
/// eye lands on.
struct FirstUseCasePreview: View {
  let useCase: FirstUseCase

  private let block = Ink.primary.opacity(0.10)
  private let blockStrong = Ink.primary.opacity(0.22)

  var body: some View {
    ZStack(alignment: .bottom) {
      browserWindow
        .padding(.horizontal, OmiSpacing.lg)
        .padding(.top, OmiSpacing.lg)
        .padding(.bottom, 44)

      omiBar
        .padding(.bottom, OmiSpacing.lg)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(
      RoundedRectangle(cornerRadius: 18, style: .continuous)
        .fill(Ink.rowFill)
    )
    .overlay(
      RoundedRectangle(cornerRadius: 18, style: .continuous)
        .stroke(Ink.separator, lineWidth: 1)
    )
    .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
    .accessibilityElement(children: .ignore)
    .accessibilityLabel("\(useCase.siteName) with the Omi bar asking: \(useCase.question)")
  }

  // MARK: - Browser chrome

  private var browserWindow: some View {
    VStack(spacing: 0) {
      HStack(spacing: OmiSpacing.sm) {
        HStack(spacing: 5) {
          ForEach(0..<3, id: \.self) { _ in
            Circle().fill(blockStrong).frame(width: 8, height: 8)
          }
        }
        Spacer(minLength: OmiSpacing.sm)
        Text(useCase.siteName.lowercased())
          .font(.system(size: 10, weight: .medium, design: .rounded))
          .foregroundColor(Ink.secondary)
          .padding(.horizontal, OmiSpacing.md)
          .padding(.vertical, 3)
          .background(Capsule().fill(block))
        Spacer(minLength: OmiSpacing.sm)
        Color.clear.frame(width: 34, height: 8)
      }
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.sm)

      Rectangle().fill(Ink.separator).frame(height: 1)

      // One big monochrome brand mark: the place, at a glance, in the panel's own ink.
      GeometryReader { proxy in
        let side = min(proxy.size.width, proxy.size.height) * 0.56
        BrandMark(useCase: useCase)
          .frame(width: side, height: side)
          .position(x: proxy.size.width / 2, y: proxy.size.height / 2 - side * 0.08)
      }
    }
    .background(
      RoundedRectangle(cornerRadius: 12, style: .continuous)
        .fill(Ink.surface)
    )
    .overlay(
      RoundedRectangle(cornerRadius: 12, style: .continuous)
        .stroke(Ink.separator, lineWidth: 1)
    )
    .shadow(color: Color.black.opacity(0.10), radius: 14, y: 6)
  }

  // MARK: - The bar

  private var omiBar: some View {
    HStack(spacing: OmiSpacing.sm) {
      Image(systemName: "sparkles")
        .font(.system(size: 12, weight: .semibold))
      Text(useCase.question)
        .font(.system(size: 13, weight: .medium))
        .lineLimit(1)
      Spacer(minLength: OmiSpacing.md)
      Image(systemName: "return")
        .font(.system(size: 11, weight: .bold))
        .opacity(0.7)
    }
    .foregroundColor(.white)
    .padding(.horizontal, OmiSpacing.lg)
    .padding(.vertical, OmiSpacing.md)
    .frame(maxWidth: 360)
    .background(
      Capsule().fill(Color.black.opacity(0.90))
    )
    .shadow(color: Color.black.opacity(0.25), radius: 12, y: 4)
    .id(useCase.id)
    .transition(.opacity.combined(with: .move(edge: .bottom)))
  }
}

// MARK: - Brand marks

/// The four marks, drawn in `Ink.primary` so they sit on the glass like the rest of the type and
/// never carry a brand colour the panel has to answer for. Each is the shape people recognise
/// from the icon alone: Figma's five tiles, the X, the creeper, the amazon smile.
struct BrandMark: View {
  let useCase: FirstUseCase

  var body: some View {
    switch useCase.id {
    case FirstUseCase.design.id: FigmaMark()
    case FirstUseCase.post.id: XMark()
    case FirstUseCase.game.id: CreeperMark()
    default: AmazonMark()
    }
  }
}

/// Figma: a 2×3 grid of tiles; top row two half-pills, middle a half-pill and a circle, bottom a
/// pill rounded on three corners.
struct FigmaMark: View {
  var body: some View {
    GeometryReader { proxy in
      let unit = min(proxy.size.width / 2, proxy.size.height / 3)
      let gap = unit * 0.06
      let tile = unit - gap
      let x0 = (proxy.size.width - unit * 2) / 2
      let y0 = (proxy.size.height - unit * 3) / 2
      let r = tile / 2
      ZStack(alignment: .topLeading) {
        UnevenRoundedRectangle(cornerRadii: .init(topLeading: r, bottomLeading: r), style: .continuous)
          .frame(width: tile, height: tile).offset(x: x0, y: y0)
        UnevenRoundedRectangle(cornerRadii: .init(bottomTrailing: r, topTrailing: r), style: .continuous)
          .frame(width: tile, height: tile).offset(x: x0 + unit, y: y0)
        UnevenRoundedRectangle(cornerRadii: .init(topLeading: r, bottomLeading: r), style: .continuous)
          .frame(width: tile, height: tile).offset(x: x0, y: y0 + unit)
        Circle()
          .frame(width: tile, height: tile).offset(x: x0 + unit, y: y0 + unit)
        UnevenRoundedRectangle(
          cornerRadii: .init(topLeading: r, bottomLeading: r, bottomTrailing: r), style: .continuous
        )
        .frame(width: tile, height: tile).offset(x: x0, y: y0 + unit * 2)
      }
      .foregroundColor(Ink.primary)
    }
  }
}

/// X: one heavy stroke corner to corner, a lighter one crossing it with the gap the mark is
/// known for.
struct XMark: View {
  var body: some View {
    GeometryReader { proxy in
      let w = proxy.size.width
      let h = proxy.size.height
      Path { p in
        // Heavy stroke: top-left → bottom-right.
        p.move(to: CGPoint(x: w * 0.06, y: 0))
        p.addLine(to: CGPoint(x: w * 0.30, y: 0))
        p.addLine(to: CGPoint(x: w * 0.94, y: h))
        p.addLine(to: CGPoint(x: w * 0.70, y: h))
        p.closeSubpath()
        // Light stroke: top-right → bottom-left, broken by the heavy one.
        p.move(to: CGPoint(x: w * 0.80, y: 0))
        p.addLine(to: CGPoint(x: w * 0.94, y: 0))
        p.addLine(to: CGPoint(x: w * 0.56, y: h * 0.44))
        p.addLine(to: CGPoint(x: w * 0.49, y: h * 0.36))
        p.closeSubpath()
        p.move(to: CGPoint(x: w * 0.44, y: h * 0.56))
        p.addLine(to: CGPoint(x: w * 0.51, y: h * 0.64))
        p.addLine(to: CGPoint(x: w * 0.20, y: h))
        p.addLine(to: CGPoint(x: w * 0.06, y: h))
        p.closeSubpath()
      }
      .fill(Ink.primary)
    }
  }
}

/// The creeper face on an 8×8 grid.
struct CreeperMark: View {
  private static let face: [[Int]] = [
    [0, 0, 0, 0, 0, 0, 0, 0],
    [0, 1, 1, 0, 0, 1, 1, 0],
    [0, 1, 1, 0, 0, 1, 1, 0],
    [0, 0, 0, 1, 1, 0, 0, 0],
    [0, 0, 1, 1, 1, 1, 0, 0],
    [0, 0, 1, 1, 1, 1, 0, 0],
    [0, 0, 1, 0, 0, 1, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0],
  ]

  var body: some View {
    VStack(spacing: 0) {
      ForEach(Array(Self.face.enumerated()), id: \.offset) { _, row in
        HStack(spacing: 0) {
          ForEach(Array(row.enumerated()), id: \.offset) { _, on in
            Rectangle().fill(on == 1 ? Ink.primary : Ink.primary.opacity(0.12))
          }
        }
      }
    }
    .aspectRatio(1, contentMode: .fit)
    .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
  }
}

/// amazon: the lowercase wordmark with the smile from a to z.
struct AmazonMark: View {
  var body: some View {
    GeometryReader { proxy in
      let w = proxy.size.width
      VStack(spacing: w * 0.02) {
        Text("amazon")
          .font(.system(size: w * 0.24, weight: .bold, design: .rounded))
          .tracking(-w * 0.012)
          .lineLimit(1)
          .fixedSize()
          .foregroundColor(Ink.primary)
        Path { p in
          p.move(to: CGPoint(x: w * 0.06, y: 0))
          p.addQuadCurve(to: CGPoint(x: w * 0.80, y: 0), control: CGPoint(x: w * 0.43, y: w * 0.22))
        }
        .stroke(Ink.primary, style: StrokeStyle(lineWidth: w * 0.05, lineCap: .round))
        .frame(height: w * 0.12)
        .overlay(alignment: .topTrailing) {
          Path { p in
            p.move(to: CGPoint(x: 0, y: -w * 0.05))
            p.addLine(to: CGPoint(x: w * 0.09, y: 0))
            p.addLine(to: CGPoint(x: -w * 0.01, y: w * 0.05))
          }
          .stroke(Ink.primary, style: StrokeStyle(lineWidth: w * 0.05, lineCap: .round, lineJoin: .round))
          .frame(width: w * 0.09, height: w * 0.1)
          .offset(x: -w * 0.12, y: w * 0.0)
        }
      }
      .frame(width: w)
      .position(x: w / 2, y: proxy.size.height / 2)
    }
  }
}
