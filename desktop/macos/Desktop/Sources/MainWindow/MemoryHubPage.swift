import OmiTheme
import SwiftUI

/// What the Brain Map does when a user clicks a cited memory.
///
/// The order is the contract: the graph is left only once the memory is
/// actually open. Leaving first strands the user on the Memories page with an
/// empty detail panel whenever the citation is not on this device — the graph
/// cites the whole cache, so that is a routine outcome, not an edge case.
@MainActor
enum MemoryAtlasCitationOpen {
  static func open(
    id memoryID: String,
    in memoriesViewModel: MemoriesViewModel,
    leave: () -> Void
  ) async {
    guard await memoriesViewModel.openMemory(id: memoryID) else { return }
    leave()
  }
}

/// Isolated page content switch — does NOT observe AppState or ViewModelContainer
/// as @ObservedObject, so pages like TasksPage won't re-render when unrelated
/// AppState properties (conversations, permissions, etc.) change.
struct MemoryHubPage: View {
  let appState: AppState
  let viewModelContainer: ViewModelContainer
  /// Observed, not just read through the container: the canonical lifecycle
  /// capability arrives with the first authoritative memory response, and the
  /// Brain Map destination must re-resolve its presentation when it flips.
  @ObservedObject var memoriesViewModel: MemoriesViewModel
  @ObservedObject private var conversationDetailState = ConversationDetailAutomationState.shared
  @Binding var destinationRawValue: Int
  /// How this shell applies a hub selection. The modern shell only has to write the persisted
  /// destination; the chat-first shell also moves its own typed route, so it passes its own.
  var onSelectDestination: ((MemoryHubDestination) -> Void)? = nil

  private var destination: MemoryHubDestination {
    MemoryHubDestination(rawValue: destinationRawValue) ?? .memories
  }

  /// Canonical-cohort users get the atlas on the Brain Map destination; users
  /// who have not entered the canonical lifecycle keep the legacy graph.
  private var brainMapPresentationMode: MemoryGraphPresentationMode {
    MemoryGraphPresentationMode.resolve(
      canonicalLifecycleExposed: memoriesViewModel.canonicalLifecycleExposed,
      forceCanonicalAtlasForLocalQA: MemoryGraphPresentationMode.localQAOverrideEnabled,
      capabilityEstablished: memoriesViewModel.canonicalLifecycleCapabilityEstablished
    )
  }

  /// The hub wears its own switcher. It used to live in the top bar's `Library` hover menu, which
  /// made the window's chrome responsible for one page's three views — and made Brain Map reachable
  /// only by hovering. A page's tabs belong to the page (INV-NAV-1: same destinations, same owner).
  var body: some View {
    VStack(spacing: 0) {
      MemoryHubSwitcher(selection: destination, onSelect: select)
        .padding(.top, 22)
        .padding(.horizontal, 28)
        .padding(.bottom, 4)
      hubContent
    }
  }

  private func select(_ next: MemoryHubDestination) {
    OmiUISound.play(.navigate)
    OmiMotion.withGated(.easeOut(duration: InkMotion.checkbox)) {
      if let onSelectDestination {
        onSelectDestination(next)
      } else {
        destinationRawValue = next.rawValue
      }
    }
  }

  @ViewBuilder
  private var hubContent: some View {
    switch destination {
    case .memories:
      adaptiveContent(
        MemoriesPage(viewModel: viewModelContainer.memoriesViewModel),
        conversationID: viewModelContainer.memoriesViewModel.linkedConversation?.id
      )
    case .conversations:
      ConversationsPageHost(appState: appState)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    case .brainMap:
      brainMapDestination
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        // The lifecycle capability is established by the first authoritative
        // memory response. Without this, opening straight into a persisted
        // Brain Map destination would resolve the legacy graph for a canonical
        // user purely because the Memories destination was never visited.
        .task { await memoriesViewModel.loadMemoriesIfNeeded() }
    }
  }

  @ViewBuilder
  private var brainMapDestination: some View {
    switch brainMapPresentationMode {
    case .canonicalAtlas:
      // The Memory view model publishes for list/sync changes that do not
      // alter the Brain Map. Keep the expensive Canvas subtree out of those
      // parent transactions; it independently observes the graph view model
      // and still updates immediately for a graph revision or rebuild.
      CanonicalBrainMapDestination(
        graphViewModel: viewModelContainer.memoryGraphViewModel,
        memoriesViewModel: memoriesViewModel,
        onLeave: { destinationRawValue = MemoryHubDestination.memories.rawValue }
      )
      .equatable()
    case .legacyBrainMap:
      MemoryGraphPage(viewModel: viewModelContainer.memoryGraphViewModel)
    case .undetermined:
      // Neither surface may mount before the cohort is known. The legacy graph
      // in particular latches the shared view model's in-flight guard and runs
      // an empty-graph rebuild bootstrap, so a one-frame appearance left the
      // atlas permanently blank and fired a destructive rebuild.
      ZStack {
        Color.clear  // The shell's glass is the ground.
        ProgressView().tint(Ink.secondary)
      }
      .accessibilityIdentifier("brain_map_resolving_cohort")
    }
  }

  /// An update island around the Canvas-heavy Brain Map.
  ///
  /// `MemoryHubPage` has to observe `MemoriesViewModel` long enough to resolve
  /// the canonical cohort, but its normal list refreshes must not rebuild the
  /// map's SwiftUI graph. Reference identity is intentional: evidence reads
  /// and open actions use the current model at invocation time, while the map
  /// itself observes `MemoryGraphViewModel` for the only state that changes its
  /// projection.
  private struct CanonicalBrainMapDestination: View, Equatable {
    let graphViewModel: MemoryGraphViewModel
    let memoriesViewModel: MemoriesViewModel
    let onLeave: () -> Void

    nonisolated static func == (lhs: Self, rhs: Self) -> Bool {
      lhs.graphViewModel === rhs.graphViewModel && lhs.memoriesViewModel === rhs.memoriesViewModel
    }

    var body: some View {
      CanonicalMemoryAtlasTabView(
        viewModel: graphViewModel,
        evidenceProvider: { memoryIDs in
          MemoryAtlasEvidence.resolve(memoryIDs, in: await memoriesViewModel.memories(withIDs: memoryIDs))
        },
        onOpenMemory: { memoryID in
          Task { @MainActor in
            await MemoryAtlasCitationOpen.open(
              id: memoryID, in: memoriesViewModel, leave: onLeave)
          }
        },
        onLeave: onLeave
      )
    }
  }

  private func adaptiveContent<Content: View>(
    _ content: Content,
    conversationID: String?
  ) -> some View {
    let usesAvailableWidth = MemoryHubLayoutPolicy.usesAvailableWidth(
      conversationID: conversationID,
      presentedConversationID: conversationDetailState.openConversationId,
      transcriptDrawerOpen: conversationDetailState.transcriptDrawerOpen,
      memoryDetailOpen: memoriesViewModel.selectedMemory != nil
    )

    return
      content
      .frame(
        maxWidth: usesAvailableWidth ? .infinity : MemoryHubLayoutPolicy.readableContentWidth,
        maxHeight: .infinity
      )
      .frame(maxWidth: .infinity, maxHeight: .infinity)
      .animation(.easeInOut(duration: 0.22), value: usesAvailableWidth)
  }
}
