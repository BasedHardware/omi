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
  private let line = Ink.primary.opacity(0.16)

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
        Text(useCase.siteName)
          .font(.system(size: 15, weight: .semibold, design: .rounded))
          .foregroundColor(Ink.primary)
          .padding(.horizontal, OmiSpacing.lg)
          .padding(.vertical, 5)
          .background(Capsule().fill(block))
        Spacer(minLength: OmiSpacing.sm)
        Color.clear.frame(width: 34, height: 8)
      }
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.sm)

      Rectangle().fill(Ink.separator).frame(height: 1)

      Group {
        switch useCase.id {
        case FirstUseCase.game.id: minecraftPage
        case FirstUseCase.design.id: figmaPage
        case FirstUseCase.post.id: composePage
        default: shopPage
        }
      }
      .frame(maxWidth: .infinity, maxHeight: .infinity)
      .padding(OmiSpacing.md)
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

  // MARK: - Page sketches

  /// Minecraft, unmistakably: a square sun in a blue sky, a grass-and-dirt hill, an oak tree, a
  /// creeper, and the hotbar. The one sketch that uses real colour, because the colours are the
  /// recognition — a neutral voxel field reads as any block game.
  private enum Voxel: Int {
    case sky = 0
    case grass = 1
    case dirt = 2
    case stone = 3
    case leaves = 4
    case wood = 5
    case sun = 6
    case cloud = 7
  }

  private static let world: [[Int]] = [
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 6, 6],
    [0, 7, 7, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 6, 6],
    [0, 0, 0, 0, 4, 4, 4, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 4, 4, 4, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [1, 1, 1, 1, 1, 5, 1, 1, 1, 0, 0, 0, 0, 1, 1, 1],
    [2, 2, 2, 2, 2, 2, 2, 2, 2, 1, 1, 1, 1, 2, 2, 2],
    [2, 2, 3, 2, 2, 2, 3, 3, 2, 2, 2, 2, 2, 2, 3, 2],
    [3, 3, 3, 3, 2, 3, 3, 3, 3, 3, 2, 3, 3, 3, 3, 3],
  ]

  private func voxelFill(_ raw: Int) -> Color {
    switch Voxel(rawValue: raw) ?? .sky {
    case .sky: return Color(red: 0.55, green: 0.75, blue: 0.98)
    case .cloud: return Color.white.opacity(0.9)
    case .grass: return Color(red: 0.36, green: 0.68, blue: 0.24)
    case .dirt: return Color(red: 0.55, green: 0.36, blue: 0.20)
    case .stone: return Color(red: 0.50, green: 0.50, blue: 0.50)
    case .leaves: return Color(red: 0.22, green: 0.50, blue: 0.16)
    case .wood: return Color(red: 0.42, green: 0.27, blue: 0.13)
    case .sun: return Color(red: 0.99, green: 0.90, blue: 0.40)
    }
  }

  /// The creeper face: 8×8, 1 = black.
  private static let creeper: [[Int]] = [
    [0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0],
    [0, 1, 1, 0, 0, 1, 1, 0],
    [0, 1, 1, 0, 0, 1, 1, 0],
    [0, 0, 0, 1, 1, 0, 0, 0],
    [0, 0, 1, 1, 1, 1, 0, 0],
    [0, 0, 1, 1, 1, 1, 0, 0],
    [0, 0, 1, 0, 0, 1, 0, 0],
  ]

  private var creeperFace: some View {
    VStack(spacing: 0) {
      ForEach(Array(Self.creeper.enumerated()), id: \.offset) { _, row in
        HStack(spacing: 0) {
          ForEach(Array(row.enumerated()), id: \.offset) { _, on in
            Rectangle().fill(on == 1 ? Color.black.opacity(0.9) : Color(red: 0.36, green: 0.72, blue: 0.28))
          }
        }
      }
    }
    .aspectRatio(1, contentMode: .fit)
  }

  private var minecraftPage: some View {
    VStack(spacing: OmiSpacing.sm) {
      GeometryReader { proxy in
        let cell = proxy.size.width / CGFloat(Self.world[0].count)
        ZStack(alignment: .topLeading) {
          VStack(spacing: 0) {
            ForEach(Array(Self.world.enumerated()), id: \.offset) { _, row in
              HStack(spacing: 0) {
                ForEach(Array(row.enumerated()), id: \.offset) { _, raw in
                  Rectangle().fill(voxelFill(raw)).frame(height: cell)
                }
              }
            }
          }
          // The creeper stands on the low ground, two blocks tall.
          creeperFace
            .frame(width: cell * 1.6, height: cell * 1.6)
            .offset(x: cell * 10.2, y: cell * 4.4)
          Rectangle()
            .fill(Color(red: 0.36, green: 0.72, blue: 0.28))
            .frame(width: cell * 1.2, height: cell * 1.2)
            .offset(x: cell * 10.4, y: cell * 5.9)
          // Crosshair.
          Image(systemName: "plus")
            .font(.system(size: 12, weight: .regular))
            .foregroundColor(.white.opacity(0.9))
            .position(x: proxy.size.width / 2, y: cell * 4.5)
        }
      }
      .aspectRatio(16.0 / 9.0, contentMode: .fit)
      .clipped()
      .overlay(Rectangle().stroke(line, lineWidth: 1))

      HStack(spacing: 2) {
        ForEach(0..<9, id: \.self) { slot in
          RoundedRectangle(cornerRadius: 2)
            .fill(Color.black.opacity(0.55))
            .overlay(
              RoundedRectangle(cornerRadius: 2)
                .stroke(slot == 0 ? Color.white : Color.white.opacity(0.35), lineWidth: slot == 0 ? 1.5 : 1)
            )
            .overlay(
              Group {
                switch slot {
                case 0: RoundedRectangle(cornerRadius: 1).fill(voxelFill(Voxel.grass.rawValue)).padding(4)
                case 1: RoundedRectangle(cornerRadius: 1).fill(voxelFill(Voxel.wood.rawValue)).padding(4)
                case 2: RoundedRectangle(cornerRadius: 1).fill(voxelFill(Voxel.stone.rawValue)).padding(4)
                default: EmptyView()
                }
              }
            )
            .aspectRatio(1, contentMode: .fit)
        }
      }
      .frame(maxWidth: 200)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
  }

  private var figmaPage: some View {
    HStack(spacing: OmiSpacing.sm) {
      VStack(alignment: .leading, spacing: OmiSpacing.xs) {
        ForEach(0..<7, id: \.self) { index in
          sketchLine(width: index == 0 ? 36 : (index.isMultiple(of: 3) ? 30 : 42))
        }
        Spacer(minLength: 0)
      }
      .frame(width: 52)

      ZStack {
        RoundedRectangle(cornerRadius: 4, style: .continuous).fill(block)
        HStack(alignment: .top, spacing: OmiSpacing.md) {
          VStack(spacing: OmiSpacing.xs) {
            RoundedRectangle(cornerRadius: 3).fill(Ink.surface).frame(height: 18)
            RoundedRectangle(cornerRadius: 3).fill(blockStrong).frame(height: 36)
            RoundedRectangle(cornerRadius: 3).fill(Ink.surface).frame(height: 10)
            RoundedRectangle(cornerRadius: 3).fill(Ink.surface).frame(height: 10)
          }
          .padding(OmiSpacing.xs)
          .frame(width: 58)
          .background(RoundedRectangle(cornerRadius: 6).fill(Ink.surface.opacity(0.7)))
          .overlay(RoundedRectangle(cornerRadius: 6).stroke(Ink.accent, lineWidth: 1))

          VStack(alignment: .leading, spacing: OmiSpacing.xs) {
            RoundedRectangle(cornerRadius: 3).fill(blockStrong).frame(width: 60, height: 8)
            RoundedRectangle(cornerRadius: 3).fill(Ink.surface).frame(height: 44)
            Capsule().fill(Ink.primary.opacity(0.85)).frame(width: 40, height: 10)
          }
          .padding(OmiSpacing.xs)
          .frame(maxWidth: .infinity)
          .background(RoundedRectangle(cornerRadius: 6).fill(Ink.surface.opacity(0.7)))
        }
        .padding(OmiSpacing.md)
      }

      VStack(alignment: .leading, spacing: OmiSpacing.xs) {
        ForEach(0..<6, id: \.self) { index in
          HStack(spacing: OmiSpacing.xs) {
            RoundedRectangle(cornerRadius: 2).fill(index == 2 ? Ink.accent : blockStrong)
              .frame(width: 8, height: 8)
            sketchLine(width: 30)
          }
        }
        Spacer(minLength: 0)
      }
      .frame(width: 48)
    }
  }

  private var composePage: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      HStack(alignment: .top, spacing: OmiSpacing.sm) {
        Circle().fill(blockStrong).frame(width: 26, height: 26)
        Text("What's happening?")
          .font(.system(size: 15))
          .foregroundColor(Ink.secondary)
          .padding(.top, 3)
        Spacer(minLength: 0)
      }
      Spacer(minLength: 0)
      Rectangle().fill(Ink.separator).frame(height: 1)
      HStack(spacing: OmiSpacing.md) {
        ForEach(["photo", "chart.bar", "face.smiling", "calendar"], id: \.self) { symbol in
          Image(systemName: symbol)
            .font(.system(size: 12, weight: .medium))
            .foregroundColor(Ink.accent)
        }
        Spacer(minLength: 0)
        Text("Post")
          .font(.system(size: 11, weight: .bold))
          .foregroundColor(Ink.surface)
          .padding(.horizontal, OmiSpacing.md)
          .padding(.vertical, 5)
          .background(Capsule().fill(Ink.primary.opacity(0.85)))
      }
    }
  }

  private var shopPage: some View {
    VStack(spacing: OmiSpacing.sm) {
      HStack(spacing: OmiSpacing.xs) {
        RoundedRectangle(cornerRadius: 4).fill(block).frame(height: 16)
        Image(systemName: "magnifyingglass")
          .font(.system(size: 10, weight: .bold))
          .foregroundColor(Ink.surface)
          .frame(width: 22, height: 16)
          .background(RoundedRectangle(cornerRadius: 4).fill(Ink.primary.opacity(0.85)))
      }
      LazyVGrid(
        columns: [GridItem(.flexible(), spacing: OmiSpacing.sm), GridItem(.flexible(), spacing: OmiSpacing.sm)],
        spacing: OmiSpacing.sm
      ) {
        ForEach(0..<4, id: \.self) { index in
          VStack(alignment: .leading, spacing: 3) {
            RoundedRectangle(cornerRadius: 3).fill(index == 1 ? blockStrong : block).frame(height: 26)
            sketchLine(width: index.isMultiple(of: 2) ? 40 : 30)
            Text("★★★★☆")
              .font(.system(size: 7))
              .foregroundColor(Ink.primary.opacity(0.7))
            sketchLine(width: 18, strong: true)
          }
          .padding(OmiSpacing.xs)
          .background(RoundedRectangle(cornerRadius: 5).stroke(Ink.separator, lineWidth: 1))
        }
      }
      Spacer(minLength: 0)
    }
  }

  private func sketchLine(width: CGFloat, strong: Bool = false) -> some View {
    RoundedRectangle(cornerRadius: 2, style: .continuous)
      .fill(strong ? blockStrong : block)
      .frame(width: width, height: 5)
  }
}
