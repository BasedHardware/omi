import SwiftUI

private struct ModalContentHeightKey: PreferenceKey {
  static let defaultValue: CGFloat = 0
  static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
    value = max(value, nextValue())
  }
}

/// Sizes a modal to its content: fixed width, height fits the content up to
/// `maxHeight`, and anything taller scrolls. No more dead space under short
/// content, no overflow for long content.
struct FittedModal: ViewModifier {
  let width: CGFloat
  let maxHeight: CGFloat

  @State private var contentHeight: CGFloat = 0

  func body(content: Content) -> some View {
    ScrollView {
      content
        .frame(width: width)
        .background(
          GeometryReader { geo in
            Color.clear.preference(key: ModalContentHeightKey.self, value: geo.size.height)
          }
        )
    }
    .frame(width: width, height: min(contentHeight, maxHeight))
    .scrollDisabled(contentHeight <= maxHeight)
    .scrollBounceBehavior(.basedOnSize)
    .onPreferenceChange(ModalContentHeightKey.self) { contentHeight = $0 }
  }
}

extension View {
  package func fittedModal(width: CGFloat, maxHeight: CGFloat) -> some View {
    modifier(FittedModal(width: width, maxHeight: maxHeight))
  }
}
