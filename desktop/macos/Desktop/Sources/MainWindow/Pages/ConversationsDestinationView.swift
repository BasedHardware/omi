import SwiftUI

struct ConversationsDestinationView: View {
  let appState: AppState
  let viewModelContainer: ViewModelContainer
  @Binding var memoryDestinationRawValue: Int
  @AppStorage("useLegacyHomeDesign") private var useLegacyHomeDesign = false

  var body: some View {
    switch MemoryHubDestination.presentation(
      for: .conversations,
      useLegacyHomeDesign: useLegacyHomeDesign
    ) {
    case .standaloneConversations:
      ConversationsPageHost(appState: appState)
    case .memoryHub:
      MemoryHubPage(
        appState: appState,
        viewModelContainer: viewModelContainer,
        memoriesViewModel: viewModelContainer.memoriesViewModel,
        destinationRawValue: $memoryDestinationRawValue
      )
    }
  }
}
