import OmiTheme
import SwiftUI

struct HomeStatItem: Identifiable {
  let id = UUID()
  let title: String
  let value: String
  let systemImage: String
  let action: () -> Void
}

struct HomeValueHero: View {
  let snapshot: HomeValueSnapshot

  var body: some View {
    VStack(spacing: OmiSpacing.sm) {
      HStack(spacing: OmiSpacing.xs) {
        HomeOmiMarkIcon(size: 22, cornerRadius: 7)

        Text("A SECOND BRAIN YOU TRUST MORE THAN YOUR FIRST")
          .scaledFont(size: OmiType.micro, weight: .bold)
          .tracking(1.25)
          .foregroundStyle(HomePalette.muted)
      }

      Text(snapshot.title)
        .font(.system(size: 34, weight: .medium, design: .serif))
        .foregroundStyle(HomePalette.ink)
        .multilineTextAlignment(.center)
        .fixedSize(horizontal: false, vertical: true)

      Text(snapshot.subtitle)
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundStyle(HomePalette.secondary)
        .multilineTextAlignment(.center)
        .lineSpacing(3)
        .frame(maxWidth: 720)
        .fixedSize(horizontal: false, vertical: true)
    }
    .padding(.horizontal, OmiSpacing.lg)
    .accessibilityElement(children: .combine)
  }
}

/// The four Home metrics form one glanceable object instead of separate cards.
struct HomeStatRibbon: View {
  let items: [HomeStatItem]

  var body: some View {
    HStack(spacing: 0) {
      ForEach(Array(items.enumerated()), id: \.element.id) { index, item in
        if index > 0 {
          Rectangle()
            .fill(HomePalette.hairline.opacity(0.7))
            .frame(width: 1)
            .padding(.vertical, OmiSpacing.lg)
        }
        HomeStatRibbonCell(item: item)
      }
    }
    .frame(height: 76)
    .background(HomePalette.tile.opacity(0.88))
    .clipShape(RoundedRectangle(cornerRadius: OmiChrome.controlRadius, style: .continuous))
    .overlay(
      RoundedRectangle(cornerRadius: OmiChrome.controlRadius, style: .continuous)
        .stroke(HomePalette.hairline.opacity(0.8), lineWidth: 1)
    )
    .shadow(color: .black.opacity(0.16), radius: 10, y: 8)
  }
}

private struct HomeStatRibbonCell: View {
  let item: HomeStatItem

  @State private var isHovering = false

  var body: some View {
    Button(action: item.action) {
      VStack(spacing: OmiSpacing.xxs) {
        HStack(alignment: .firstTextBaseline, spacing: OmiSpacing.xs) {
          Image(systemName: item.systemImage)
            .scaledFont(size: OmiType.caption, weight: .semibold)
            .foregroundStyle(isHovering ? HomePalette.ink : HomePalette.secondary)

          Text(item.value)
            .font(.system(size: 22, weight: .medium, design: .serif))
            .foregroundStyle(HomePalette.ink)
            .lineLimit(1)
            .minimumScaleFactor(0.6)
        }

        Text(item.title)
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundStyle(isHovering ? HomePalette.secondary : HomePalette.muted)
          .lineLimit(1)
          .minimumScaleFactor(0.78)
      }
      .frame(maxWidth: .infinity)
      .padding(.vertical, OmiSpacing.md)
      .padding(.horizontal, OmiSpacing.sm)
      .background(isHovering ? HomePalette.tileHover : Color.clear)
      .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
    .onHover { isHovering = $0 }
    .accessibilityLabel("\(item.title), \(item.value)")
  }
}
