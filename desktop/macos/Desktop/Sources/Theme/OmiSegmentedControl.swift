import SwiftUI

/// The app's one segmented control: a single rounded track whose selected fill
/// slides between segments (matchedGeometry + spring), with a soft hover on the
/// unselected ones. Same visual language as the shell's top nav so every
/// section switcher across the app reads as one control.
package struct OmiSegmentedControl: View {
  package let segments: [String]
  @Binding package var selection: Int

  @Namespace private var namespace

  package init(segments: [String], selection: Binding<Int>) {
    self.segments = segments
    self._selection = selection
  }

  package var body: some View {
    HStack(spacing: 2) {
      ForEach(Array(segments.enumerated()), id: \.offset) { index, title in
        OmiSegment(
          title: title,
          isSelected: selection == index,
          namespace: namespace
        ) {
          OmiMotion.withGated(.spring(response: 0.32, dampingFraction: 0.82)) {
            selection = index
          }
        }
      }
    }
    .padding(3)
    .background(
      Capsule(style: .continuous)
        .fill(Color.white.opacity(0.05))
        .overlay(Capsule(style: .continuous).stroke(Color.white.opacity(0.07), lineWidth: 1))
    )
  }
}

private struct OmiSegment: View {
  let title: String
  let isSelected: Bool
  var namespace: Namespace.ID
  let action: () -> Void

  @State private var isHovering = false

  var body: some View {
    Button(action: action) {
      Text(title)
        .scaledFont(size: OmiType.caption, weight: .semibold)
        .foregroundColor(isSelected ? OmiColors.textPrimary : OmiColors.textTertiary)
        .padding(.horizontal, OmiSpacing.md)
        .padding(.vertical, 6)
        .background {
          ZStack {
            if isSelected {
              Capsule(style: .continuous)
                .fill(Color.white.opacity(0.12))
                .matchedGeometryEffect(id: "omiSegmentedSelection", in: namespace)
            } else if isHovering {
              Capsule(style: .continuous)
                .fill(Color.white.opacity(0.05))
            }
          }
        }
        .contentShape(Capsule())
    }
    .buttonStyle(.plain)
    .onHover { hovering in
      OmiMotion.withGated(.easeOut(duration: 0.12)) { isHovering = hovering }
    }
  }
}
