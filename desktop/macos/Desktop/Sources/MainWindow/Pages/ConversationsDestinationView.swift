import SwiftUI

struct ConversationsDestinationView: View {
  let appState: AppState
  let viewModelContainer: ViewModelContainer
  let presentation: MemoryHubDestination.Presentation
  @Binding var memoryDestinationRawValue: Int

  var body: some View {
    switch presentation {
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
