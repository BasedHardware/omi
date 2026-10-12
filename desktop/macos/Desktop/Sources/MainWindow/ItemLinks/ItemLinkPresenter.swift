import Foundation
import OmiSupport

/// A record an item link resolved to, already shaped for its row.
enum ItemLinkResolvedItem {
  case conversation(ServerConversation)
  case task(TaskActionItem)
  case memory(ServerMemory)
}

/// One row of the item-list sheet, in URL order. `item == nil` is the muted
/// "No longer available" row: the record is gone, retired, or not this user's.
struct ItemLinkRow: Identifiable {
  let reference: ItemLinkReference
  let item: ItemLinkResolvedItem?

  var id: ItemLinkReference { reference }
  var isAvailable: Bool { item != nil }
}

/// The item-list sheet's state. `rows == nil` while the records load.
struct ItemLinkSheetState: Identifiable {
  let id: UInt
  let references: [ItemLinkReference]
  var rows: [ItemLinkRow]?
}

/// Looks up the records a link names, as the signed-in user. Every lookup
/// answers "not available" rather than throwing: a missing, deleted, or
/// foreign record is a row state, not an error page.
struct ItemLinkResolver: Sendable {
  var conversation: @Sendable (String) async -> ServerConversation?
  var task: @Sendable (String) async -> TaskActionItem?
  var memories: @Sendable ([String]) async -> [ServerMemory]

  /// Rows in exactly the order of `references`.
  func resolve(_ references: [ItemLinkReference]) async -> [ItemLinkRow] {
    let memoryIDs = references.filter { $0.kind == .memory }.map(\.id)
    let foundMemories = memoryIDs.isEmpty ? [] : await memories(memoryIDs)
    let memoryByID = Dictionary(lastWriteWins: foundMemories.map { ($0.id, $0) })

    // Conversations and tasks are independent single-record reads; run them
    // together so a 10-item link costs one round trip, not ten.
    let fetched = await withTaskGroup(of: (Int, ItemLinkResolvedItem?).self) { group in
      for (index, reference) in references.enumerated() {
        switch reference.kind {
        case .conversation:
          group.addTask { (index, await conversation(reference.id).map(ItemLinkResolvedItem.conversation)) }
        case .task:
          group.addTask { (index, await task(reference.id).map(ItemLinkResolvedItem.task)) }
        case .memory:
          continue
        }
      }
      var byIndex: [Int: ItemLinkResolvedItem] = [:]
      for await (index, item) in group {
        if let item { byIndex[index] = item }
      }
      return byIndex
    }

    return references.enumerated().map { index, reference in
      switch reference.kind {
      case .memory:
        return ItemLinkRow(reference: reference, item: memoryByID[reference.id].map(ItemLinkResolvedItem.memory))
      case .conversation, .task:
        return ItemLinkRow(reference: reference, item: fetched[index])
      }
    }
  }
}

extension ItemLinkResolver {
  /// The app's existing read paths: the conversation detail fetch the chat
  /// conversation links use, the local task mirror with an owner-scoped
  /// detail fetch behind it, and the local memory mirror (the backend exposes
  /// no single-memory read).
  static let live = ItemLinkResolver(
    conversation: { id in
      guard let fetched = try? await APIClient.shared.getConversation(id: id) else { return nil }
      guard
        let conversation = ChatFirstConversationLinkPolicy.validatedConversation(fetched, requestedID: id),
        !conversation.deleted
      else { return nil }
      return conversation
    },
    task: { id in
      let owner = await MainActor.run { RuntimeOwnerIdentity.currentOwnerId() }
      var found: TaskActionItem?
      if let record = try? await ActionItemStorage.shared.getActionItemByBackendId(id) {
        found = record.toTaskActionItem()
      } else if let owner {
        found = try? await APIClient.shared.getActionItem(id: id, expectedOwnerId: owner)
      }
      guard let task = found, task.id == id, !task.isRetired else { return nil }
      return task
    },
    memories: { ids in
      let found = (try? await MemoryStorage.shared.getMemories(backendIds: ids)) ?? []
      return found.filter { !$0.isDismissed }
    }
  )
}

/// Where an item row opens: the same detail surfaces chat links use.
struct ItemLinkNavigator {
  var openConversation: @MainActor (ServerConversation) -> Void
  var openTask: @MainActor (String) -> Void
  var openMemory: @MainActor (String) -> Void
  var revealMainWindow: @MainActor () -> Void

  @MainActor
  func open(_ item: ItemLinkResolvedItem) {
    switch item {
    case .conversation(let conversation): openConversation(conversation)
    case .task(let task): openTask(task.id)
    case .memory(let memory): openMemory(memory.id)
    }
  }

  @MainActor static let live = ItemLinkNavigator(
    openConversation: { ChatFirstShellNavigation.shared.open(conversation: $0) },
    openTask: { ChatFirstShellNavigation.shared.open(focus: .task(id: $0)) },
    openMemory: { ChatFirstShellNavigation.shared.open(focus: .memory(id: $0)) },
    revealMainWindow: { AppDelegate.summonWindowTarget()?.openMainAppWindow() }
  )
}

/// Owns item links between the URL event and the main window.
///
/// The URL handler only records the route (`receive`); the signed-in main
/// shell consumes it (`consumePending`) once it is mounted. A link that
/// arrives at cold launch, or while signed out, waits for the shell instead of
/// resolving against no session.
@MainActor
final class ItemLinkPresenter: ObservableObject {
  static let shared = ItemLinkPresenter(resolver: .live, navigator: .live)

  /// Bumped on every received link; the shell observes it.
  @Published private(set) var pendingGeneration: UInt = 0
  @Published var sheet: ItemLinkSheetState?

  private var pendingRoute: ItemLinkRoute?
  private var activeGeneration: UInt = 0
  private let resolver: ItemLinkResolver
  private let navigator: ItemLinkNavigator

  init(resolver: ItemLinkResolver, navigator: ItemLinkNavigator) {
    self.resolver = resolver
    self.navigator = navigator
  }

  /// Handles an app-scheme URL if it is an item link. Returns false for every
  /// other URL (the auth callback, the onboarding return) so the caller's
  /// existing routing runs unchanged.
  @discardableResult
  func receive(_ url: URL) -> Bool {
    guard let route = ItemLinkParser.parse(url) else { return false }
    pendingRoute = route
    pendingGeneration &+= 1
    navigator.revealMainWindow()
    return true
  }

  /// Called by the signed-in shell. Resolves and presents the newest link.
  func consumePending() async {
    guard let route = pendingRoute else { return }
    pendingRoute = nil
    activeGeneration &+= 1
    let generation = activeGeneration

    let references: [ItemLinkReference]
    switch route {
    case .single(let reference): references = [reference]
    case .list(let list): references = list
    }

    // A one-item link opens its detail directly; the sheet only appears when
    // that record is unavailable, so the user still learns why nothing opened.
    if references.count == 1 {
      sheet = nil
      let rows = await resolver.resolve(references)
      guard generation == activeGeneration else { return }
      guard !Task.isCancelled else { return requeue(route) }
      if let item = rows.first?.item {
        navigator.open(item)
      } else {
        sheet = ItemLinkSheetState(id: generation, references: references, rows: rows)
      }
      return
    }

    sheet = ItemLinkSheetState(id: generation, references: references, rows: references.isEmpty ? [] : nil)
    guard !references.isEmpty else { return }
    let rows = await resolver.resolve(references)
    guard generation == activeGeneration, sheet?.id == generation else { return }
    guard !Task.isCancelled else { return requeue(route) }
    sheet?.rows = rows
  }

  /// The shell went away mid-resolution (sign-out, window teardown). A
  /// cancelled lookup reads as "unavailable", so keep the link for the next
  /// mount instead of showing every row as gone.
  /// A newer link that is already pending wins.
  private func requeue(_ route: ItemLinkRoute) {
    sheet = nil
    if pendingRoute == nil { pendingRoute = route }
  }

  /// A row tap: close the sheet, then open the existing detail surface.
  func open(_ row: ItemLinkRow) {
    guard let item = row.item else { return }
    sheet = nil
    navigator.open(item)
  }

  func dismiss() {
    activeGeneration &+= 1
    sheet = nil
  }
}
