import OmiTheme
import SwiftUI

/// The live transcript — what Omi is hearing right now, streaming in as you speak.
/// Opened by tapping the "Recording" row on Today. Binds to LiveTranscriptMonitor.
struct SBLiveTranscript: View {
  @Environment(\.sbTheme) private var sb
  @ObservedObject private var monitor = LiveTranscriptMonitor.shared
  var title: String
  var onBack: () -> Void

  var body: some View {
    ScrollViewReader { proxy in
      ScrollView {
        VStack(alignment: .leading, spacing: 0) {
          Button(action: onBack) {
            Text("← Back").geist(size: 13.5).foregroundStyle(sb.ink(.w4))
          }
          .buttonStyle(.plain)
          .padding(.bottom, 10)

          HStack(spacing: 10) {
            Text(title).geist(size: 23, weight: .semibold, tracking: 23 * -0.02).foregroundStyle(sb.ink)
            SBMiniWaveform()
            Spacer()
          }
          HStack(spacing: 6) {
            Circle().fill(sb.ink(.w6)).frame(width: 6, height: 6)
            Text("recording now — live").geistMono(size: 12).foregroundStyle(sb.ink(.w45))
          }
          .padding(.top, 4).padding(.bottom, 16)

          if monitor.segments.isEmpty {
            Text("Listening… whatever's said appears here, live.")
              .geist(size: 14).foregroundStyle(sb.ink(.w35)).padding(.vertical, 10)
          }

          ForEach(monitor.segments) { seg in
            VStack(alignment: .leading, spacing: 3) {
              Text(seg.isUser ? "You" : "Speaker \(seg.speaker + 1)")
                .geistMono(size: 11, weight: .medium, tracking: 11 * 0.06)
                .foregroundStyle(seg.isUser ? sb.ink(.w6) : sb.ink(.w4))
              Text(seg.text)
                .geist(size: 14.5).foregroundStyle(sb.ink(.w8)).lineSpacing(3)
                .fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.vertical, 7)
            .id(seg.id)
          }
          Color.clear.frame(height: 2).id("live-bottom")
        }
        .padding(.horizontal, 30).padding(.bottom, 24)
      }
      .onChange(of: monitor.segments.count) { _, _ in
        withAnimation { proxy.scrollTo("live-bottom", anchor: .bottom) }
      }
    }
  }
}
