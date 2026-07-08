import SwiftUI

/// Slim window top bar for the redesign: the `omi` wordmark on the left and the
/// live Capture / Listening presence chips on the right (mockup titlebar).
struct RedesignTopBar: View {
  @ObservedObject var appState: AppState
  @AppStorage("screenAnalysisEnabled") private var screenAnalysisEnabled = true

  var body: some View {
    HStack {
      Text("omi").inkWordmark(17)
      Spacer()
      PresenceChips(
        capturing: screenAnalysisEnabled,
        listening: appState.isTranscribing)
    }
    .padding(.horizontal, 18)
    .frame(height: 40)
    .background(Ink.soft)
    .overlay(Rectangle().fill(Ink.hair).frame(height: 1), alignment: .bottom)
  }
}
