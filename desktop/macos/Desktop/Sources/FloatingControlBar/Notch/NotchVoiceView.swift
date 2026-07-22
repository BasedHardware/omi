import SwiftUI

/// The expanded voice content below the morphing Omi orb: the live transcript
/// while listening, or the streaming reply while responding, centered under the
/// orb. Reports its measured height so the panel grows in height as words wrap
/// to new lines (the width is fixed). The reply is a tap target that opens the
/// main app window (full text chat lives in the app now).
struct NotchVoiceView: View {
  enum Phase { case listening, responding }
  let phase: Phase
  /// Vertical space reserved at the top for the camera housing + the orb, so
  /// the text sits below them. Matches the orb overlay's offset in NotchView.
  let topReserve: CGFloat
  let onHeightChange: (CGFloat) -> Void
  let onOpenApp: () -> Void

  @EnvironmentObject var barState: FloatingControlBarState

  var body: some View {
    VStack(spacing: 0) {
      Color.clear.frame(height: topReserve)
      transcript
        .font(.system(size: 13, weight: phase == .listening ? .medium : .regular))
        .foregroundStyle(.white.opacity(isPlaceholder ? 0.5 : 0.92))
        .multilineTextAlignment(.center)
        .frame(maxWidth: .infinity, alignment: .center)
        .fixedSize(horizontal: false, vertical: true)
        .padding(.horizontal, 26)
        .padding(.bottom, 14)
    }
    .onGeometryChange(for: CGFloat.self) {
      $0.size.height
    } action: {
      onHeightChange($0)
    }
  }

  private var text: String {
    switch phase {
    case .listening: return barState.liveVoiceUserText
    case .responding: return barState.liveVoiceAssistantText
    }
  }

  private var isPlaceholder: Bool { text.isEmpty }

  @ViewBuilder
  private var transcript: some View {
    switch phase {
    case .listening:
      Text(text.isEmpty ? "Listening…" : text)
    case .responding:
      // ponytail: voice replies are short — clips at half-screen and the tap
      // opens the app for the full conversation. Add an inner ScrollView if
      // long spoken replies become common.
      Text(text.isEmpty ? "Thinking…" : text)
        .contentShape(Rectangle())
        .onTapGesture(perform: onOpenApp)
        .accessibilityAddTraits(.isButton)
        .accessibilityHint("Open the full conversation")
    }
  }
}
