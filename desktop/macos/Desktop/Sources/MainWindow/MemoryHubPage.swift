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
  /// Rewind lives on the shell rail, not in this hub, so the Activity spine's way into it has to be
  /// supplied by the host that owns the rail index. Hosts without one leave the card inert.
  var onOpenRewind: (() -> Void)? = nil
  /// How the host opens one exact conversation.
  ///
  /// The chat-first shell supplies its typed deep link (`navigation.open(conversation:)`), which
  /// carries the record to the Conversations host. Hosts without one fall back to the automation
  /// singleton below — correct for the modern shell, where this page mounts `ConversationsPageHost`
  /// itself and that host is guaranteed to be the one that consumes the request.
  var onOpenConversationRecord: ((ServerConversation) -> Void)? = nil

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

  /// **The hub wears no switcher.** It used to carry one directly above Activity's own filter row —
  /// two chip rows a few points apart, sharing three of their words, doing different things. The
  /// row that survived is Activity's, and every chip in it navigates (`ActivityDestinationChip`),
  /// so the hub's four pages are reached from one place with one rule. Landing on any of them and
  /// pressing `Activity` in the top bar comes back to that row (INV-NAV-1).
  var body: some View {
    hubContent
  }

  /// Puts the way back to Activity on the page itself.
  ///
  /// Activity's chip row is what opened this page, and the row stayed behind on Activity's panel.
  /// The top-bar pill does return, but that is window chrome answering for a control the page
  /// offered — the page has to carry its own way back (INV-NAV-1).
  @ViewBuilder
  private func backToActivity<Content: View>(@ViewBuilder _ content: () -> Content) -> some View {
    VStack(alignment: .leading, spacing: 0) {
      HStack {
        ActivityBackButton { select(.activity) }
        Spacer(minLength: 0)
      }
      .padding(.top, 18)
      .padding(.horizontal, 28)
      .padding(.bottom, 6)
      content()
    }
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
        onOpenRewind: { onOpenRewind?() },
        onOpenHubDestination: select
      )
      .frame(maxWidth: .infinity, maxHeight: .infinity)
    case .memories:
      backToActivity {
        adaptiveContent(
          MemoriesPage(viewModel: viewModelContainer.memoriesViewModel),
          conversationID: viewModelContainer.memoriesViewModel.linkedConversation?.id
        )
      }
    case .conversations:
      backToActivity {
        ConversationsPageHost(appState: appState)
          .frame(maxWidth: .infinity, maxHeight: .infinity)
      }
    case .brainMap:
      backToActivity {
        brainMapDestination
          .frame(maxWidth: .infinity, maxHeight: .infinity)
      }
      // The lifecycle capability is established by the first authoritative
      // memory response. Without this, opening straight into a persisted
      // Brain Map destination would resolve the compatibility graph before
      // the server capability was known purely because Memories was never visited.
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
