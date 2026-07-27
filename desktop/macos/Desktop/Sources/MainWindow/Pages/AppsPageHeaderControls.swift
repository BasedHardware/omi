import OmiTheme
import SwiftUI

enum AppsHeaderMetrics {
  static let searchFieldMaxWidth: CGFloat = 360
  static let controlIconSize: CGFloat = 16
  static let controlHeight: CGFloat = 44
}

/// Keeps the flexible search field from squeezing labelled controls. At compact
/// widths the same controls stack instead of truncating.
struct AppsHeaderRow<Search: View, Filters: View, Create: View, Dismiss: View>: View {
  let search: Search
  let filters: Filters
  let create: Create
  let dismiss: Dismiss

  init(
    @ViewBuilder search: () -> Search,
    @ViewBuilder filters: () -> Filters,
    @ViewBuilder create: () -> Create,
    @ViewBuilder dismiss: () -> Dismiss
  ) {
    self.search = search()
    self.filters = filters()
    self.create = create()
    self.dismiss = dismiss()
  }

  var body: some View {
    ViewThatFits(in: .horizontal) {
      HStack(spacing: OmiSpacing.md) {
        search
          .frame(maxWidth: AppsHeaderMetrics.searchFieldMaxWidth)
        filters
          .fixedSize(horizontal: true, vertical: false)
        create
        dismiss
      }

      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        HStack(spacing: OmiSpacing.sm) {
          search
          dismiss
        }

        HStack(spacing: OmiSpacing.sm) {
          filters
            .fixedSize(horizontal: true, vertical: false)
          create
        }
      }
    }
  }
}

struct FilterToggle: View {
  let icon: String
  let label: String
  let isActive: Bool
  let action: () -> Void

  var body: some View {
    Button(action: action) {
      HStack(spacing: OmiSpacing.xs) {
        Image(systemName: icon)
          .scaledFont(size: OmiType.caption)
          .frame(width: AppsHeaderMetrics.controlIconSize)
        Text(label)
          .scaledFont(size: OmiType.body)
          .lineLimit(1)
      }
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.sm)
      .background(
        Capsule(style: .continuous)
          .fill(Color.white.opacity(isActive ? 0.14 : 0.06))
          .overlay(
            Capsule(style: .continuous)
              .stroke(Color.white.opacity(isActive ? 0.2 : 0.08), lineWidth: 1)
          )
      )
      .foregroundColor(isActive ? OmiColors.textPrimary : OmiColors.textSecondary)
      .fixedSize(horizontal: true, vertical: false)
    }
    .buttonStyle(.plain)
  }
}

struct SmallHeaderButton: View {
  let icon: String
  let label: String
  let color: Color
  let action: () -> Void

  @State private var isHovering = false

  var body: some View {
    Button(action: action) {
      HStack(spacing: OmiSpacing.xs) {
        Image(systemName: icon)
          .scaledFont(size: OmiType.caption)
          .frame(width: AppsHeaderMetrics.controlIconSize)
          .foregroundColor(color)
        Text(label)
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundColor(OmiColors.textSecondary)
          .lineLimit(1)
      }
      .padding(.horizontal, OmiSpacing.sm)
      .padding(.vertical, OmiSpacing.xs)
      .background(
        Capsule(style: .continuous)
          .fill(Color.white.opacity(isHovering ? 0.12 : 0.06))
          .overlay(
            Capsule(style: .continuous)
              .stroke(Color.white.opacity(isHovering ? 0.18 : 0.08), lineWidth: 1)
          )
      )
      .fixedSize(horizontal: true, vertical: false)
    }
    .buttonStyle(.plain)
    .onHover { hovering in
      OmiMotion.withGated(.easeOut(duration: 0.12)) { isHovering = hovering }
    }
  }
}
