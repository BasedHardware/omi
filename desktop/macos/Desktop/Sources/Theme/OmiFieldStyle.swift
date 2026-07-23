import SwiftUI

extension View {
  /// Consistent search / text-field chrome: a capsule with a subtle translucent
  /// fill and a focus ring, matching the app's chip and segmented-control
  /// language. Wrap the field's `HStack { icon; TextField; clear }` with it.
  package func omiSearchFieldChrome(isFocused: Bool = false, minHeight: CGFloat? = nil) -> some View {
    self
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.sm + 1)
      .frame(minHeight: minHeight)
      .background(
        Capsule(style: .continuous)
          .fill(Color.white.opacity(isFocused ? 0.10 : 0.06))
      )
      .overlay(
        Capsule(style: .continuous)
          .stroke(
            isFocused ? Color.white.opacity(0.22) : Color.white.opacity(0.08),
            lineWidth: 1)
      )
      .omiAnimation(.easeOut(duration: 0.15), value: isFocused)
  }
}
