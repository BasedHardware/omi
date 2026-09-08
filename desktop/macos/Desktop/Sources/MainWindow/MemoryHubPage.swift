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
  @State private var brainMapSearchText = ""
  /// How this shell applies a hub selection. The modern shell only has to write the persisted
  /// destination; the chat-first shell also moves its own typed route, so it passes its own.
  var onSelectDestination: ((MemoryHubDestination) -> Void)? = nil
  /// How the host opens one exact conversation.
  ///
  /// The chat-first shell supplies its typed deep link (`navigation.open(conversation:)`), which
  /// carries the record to the Conversations host. Hosts without one fall back to the automation
  /// singleton below — correct for the modern shell, where this page mounts `ConversationsPageHost`
  /// itself and that host is guaranteed to be the one that consumes the request.
  var onOpenConversationRecord: ((ServerConversation) -> Void)? = nil
  /// Optional exact record supplied by a Chat-first Activity deep-link. It is
  /// passed to the same hub-owned ConversationsPageHost used by the
  /// Conversations destination, so Activity does not open a second detail
  /// presentation on the dedicated Chat-first route.
  var initialConversation: ServerConversation? = nil
  /// Optional timestamp carried by a conversation deep link. The hub remains
  /// the sole presentation owner; this only seeds the transcript/playback
  /// focus inside its canonical Conversations destination.
  var initialCaptureMomentTimestamp: TimeInterval? = nil
  var onCaptureFocusResolved: ((Bool) -> Void)? = nil
  /// Canonical detail capabilities supplied by the owning shell. Activity and
  /// the Conversations destination forward the same callbacks so opening the
  /// same record never changes which actions are available.
  var onDiscussInChat: ((ServerConversation) -> Void)? = nil
  var onOpenLinkedTask: ((String) -> Void)? = nil
  var onConversationSelectionChanged: ((ServerConversation?) -> Void)? = nil

  private var destination: MemoryHubDestination {
    MemoryHubDestination(rawValue: destinationRawValue) ?? .memories
  }

  /// The universal assertion-backed graph gets the atlas on the Brain Map destination; users
  /// who have not entered the canonical lifecycle keep the legacy graph.
  private var brainMapPresentationMode: MemoryGraphPresentationMode {
    MemoryGraphPresentationMode.resolve(
      canonicalLifecycleExposed: memoriesViewModel.canonicalLifecycleExposed,
      forceCanonicalAtlasForLocalQA: MemoryGraphPresentationMode.localQAOverrideEnabled,
      capabilityEstablished: memoriesViewModel.canonicalLifecycleCapabilityEstablished
    )
  }

  /// Brain is a stable parent with one persistent peer-navigation row. Switching sections never
  /// becomes a drill-in, so Conversations, Memories, Rewind, and Brain Map do not replace the row
  /// with a back button.
  var body: some View {
    hubContent
  }

  private func select(_ next: MemoryHubDestination) {
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
    case .activity:
      ActivityHubTab(
        appState: appState,
        memoriesViewModel: memoriesViewModel,
        onOpenConversation: { conversation in
          // Clicking a conversation in Activity used to write its id into the automation singleton
          // and then call `select(.conversations)` — a plain destination change, which is the one
          // primitive defined to *discard* an unconsumed deep link (`selectPrimary` nils
          // `pendingConversation`). The id was dropped a frame after it was written and the user
          // landed on the conversation list. When the host owns a typed deep link, use it.
          if let onOpenConversationRecord {
            onOpenConversationRecord(conversation)
          } else {
            ConversationDetailAutomationState.shared.requestOpen(
              conversationId: conversation.id, showTranscript: false)
            select(.conversations)
          }
        },
        onOpenMemory: { memory in
          // Same gate the Brain Map's citations use: leave Activity only once the memory is really
          // open, so an unresolvable memory does not strand the user on an empty detail panel.
          Task {
            await MemoryAtlasCitationOpen.open(
              id: memory.id, in: memoriesViewModel, leave: { select(.memories) })
          }
        },
        onOpenBrainMap: { select(.brainMap) },
        onOpenRewind: { select(.rewind) },
        selectedDestination: destination,
        onSelectDestination: select
      )
      .frame(maxWidth: .infinity, maxHeight: .infinity)
    case .memories:
      MemoriesPage(
        viewModel: viewModelContainer.memoriesViewModel,
        brainDestination: destination,
        onSelectBrainDestination: select,
        onOpenConversation: openConversation
      )
      .frame(maxWidth: .infinity, maxHeight: .infinity)
    case .conversations:
      ConversationsPageHost(
        appState: appState,
        brainDestination: destination,
        onSelectBrainDestination: select,
        initialConversation: initialConversation,
        initialCaptureMomentTimestamp: initialCaptureMomentTimestamp,
        onCaptureFocusResolved: onCaptureFocusResolved,
        onDiscussInChat: onDiscussInChat,
        onOpenLinkedTask: onOpenLinkedTask,
        onSelectionChanged: onConversationSelectionChanged
      )
      .frame(maxWidth: .infinity, maxHeight: .infinity)
    case .rewind:
      RewindPage(
        appState: appState,
        brainDestination: destination,
        onSelectBrainDestination: select
      )
      .frame(maxWidth: .infinity, maxHeight: .infinity)
    case .brainMap:
      BrainSectionPageLayout(
        selected: destination,
        onSelect: select,
        search: {
          QuerySearchBar(
            text: $brainMapSearchText,
            accessibilityID: "brain-map-search-field",
            placeholder: "Search your entities…",
            searchSurface: .brainMap
          )
        },
        content: { brainMapDestination }
      )
      .frame(maxWidth: .infinity, maxHeight: .infinity)
      // The lifecycle capability is established by the first authoritative
      // memory response. Without this, opening straight into a persisted
      // Brain Map destination would resolve the compatibility graph before
      // the server capability was known purely because Memories was never visited.
      .task { await memoriesViewModel.loadMemoriesIfNeeded() }
    }
  }

  private func openConversation(_ conversationID: String) {
    guard !conversationID.isEmpty else { return }
    if let onOpenConversationRecord {
      Task { @MainActor in
        guard let conversation = try? await APIClient.shared.getConversation(id: conversationID) else {
          return
        }
        onOpenConversationRecord(conversation)
      }
    } else {
      ConversationDetailAutomationState.shared.requestOpen(
        conversationId: conversationID,
        showTranscript: false
      )
      select(.conversations)
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
        searchText: $brainMapSearchText,
        onLeave: { destinationRawValue = MemoryHubDestination.memories.rawValue }
      )
    case .legacyBrainMap:
      MemoryGraphPage(
        viewModel: viewModelContainer.memoryGraphViewModel,
        searchText: brainMapSearchText
      )
    case .undetermined:
      // Neither surface may mount before the server capability is known. The compatibility graph
      // in particular latches the shared view model's in-flight guard and runs
      // an empty-graph rebuild bootstrap, so a one-frame appearance left the
      // atlas permanently blank and fired a destructive rebuild.
      ZStack {
        Color.clear  // The shell's glass is the ground.
        ProgressView().tint(Ink.secondary)
      }
      .accessibilityIdentifier("brain_map_resolving_capability")
    }
  }

  /// An update island around the Canvas-heavy Brain Map.
  ///
  /// `MemoryHubPage` has to observe `MemoriesViewModel` long enough to resolve
  /// the server lifecycle capability, but its normal list refreshes must not rebuild the
  /// map's SwiftUI graph. Reference identity is intentional: evidence reads
  /// and open actions use the current model at invocation time, while the map
  /// itself observes `MemoryGraphViewModel` for the only state that changes its
  /// projection.
  private struct CanonicalBrainMapDestination: View {
    let graphViewModel: MemoryGraphViewModel
    let memoriesViewModel: MemoriesViewModel
    @Binding var searchText: String
    let onLeave: () -> Void

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
        searchText: $searchText,
        showsSearchField: false,
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
