import Foundation

/// The capture archive has a single, non-negotiable provenance query. It is
/// intentionally separate from `ConversationListQuery`, whose legacy callers
/// may display mixed desktop, phone, and hardware conversations.
struct CaptureArchiveQuery: Equatable, Sendable {
  static let pageSize = 50

  let offset: Int
  let limit: Int
  /// These are deliberately constants rather than caller-controlled query
  /// knobs. The archive must never be repurposed as a generic conversations
  /// list by accidentally changing a page request.
  let statuses: [ConversationStatus] = [.completed, .processing]
  let source: ConversationSource = .omi
  let includeDiscarded = false

  init(offset: Int = 0, limit: Int = CaptureArchiveQuery.pageSize) {
    self.offset = offset
    self.limit = limit
  }
}

private enum CaptureArchiveRepositoryError: Error {
  /// A filtered server/cache response containing another provenance is a
  /// contract failure, not an opportunity to client-filter a mixed page.
  case receivedNonArchiveCapture
}

extension ServerConversation {
  fileprivate var isOmiCaptureArchiveRecord: Bool {
    source == .omi && !discarded && (status == .completed || status == .processing)
  }
}

protocol CaptureArchiveRemoteDataSource: Sendable {
  func list(query: CaptureArchiveQuery) async throws -> [ServerConversation]
  func count(query: CaptureArchiveQuery) async throws -> Int
  func detail(id: String) async throws -> ServerConversation
}

protocol CaptureArchiveLocalDataSource: Sendable {
  func list(query: CaptureArchiveQuery) async throws -> [ServerConversation]
  func count(query: CaptureArchiveQuery) async throws -> Int
  func detail(id: String) async throws -> ServerConversation?
  func store(_ conversation: ServerConversation) async throws
}

struct LiveCaptureArchiveRemoteDataSource: CaptureArchiveRemoteDataSource {
  func list(query: CaptureArchiveQuery) async throws -> [ServerConversation] {
    try await APIClient.shared.getConversations(
      limit: query.limit,
      offset: query.offset,
      statuses: query.statuses,
      sources: [query.source],
      includeDiscarded: query.includeDiscarded
    )
  }

  func count(query: CaptureArchiveQuery) async throws -> Int {
    try await APIClient.shared.getConversationsCount(
      includeDiscarded: query.includeDiscarded,
      statuses: query.statuses,
      sources: [query.source]
    )
  }

  func detail(id: String) async throws -> ServerConversation {
    try await APIClient.shared.getConversation(id: id)
  }
}

struct LiveCaptureArchiveLocalDataSource: CaptureArchiveLocalDataSource {
  func list(query: CaptureArchiveQuery) async throws -> [ServerConversation] {
    precondition(query.source == .omi && query.includeDiscarded == false)
    return try await TranscriptionStorage.shared.getLocalOmiCaptureConversations(
      limit: query.limit,
      offset: query.offset
    )
  }

  func count(query: CaptureArchiveQuery) async throws -> Int {
    precondition(query.source == .omi && query.includeDiscarded == false)
    return try await TranscriptionStorage.shared.getLocalOmiCaptureConversationsCount()
  }

  func detail(id: String) async throws -> ServerConversation? {
    try await TranscriptionStorage.shared.getCachedConversation(id: id)
  }

  func store(_ conversation: ServerConversation) async throws {
    _ = try await TranscriptionStorage.shared.syncServerConversation(conversation)
  }
}

/// Read-only cache/network owner for the cohort-only Omi capture archive. It
/// has no mutation or mixed-source fallback path by design.
@MainActor
final class CaptureArchiveRepository: ObservableObject {
  @Published private(set) var captures: [ServerConversation] = []
  @Published private(set) var selectedCapture: ServerConversation?
  @Published private(set) var count: Int?
  @Published private(set) var isLoading = false
  @Published private(set) var isLoadingMore = false
  @Published private(set) var errorMessage: String?

  private let remote: any CaptureArchiveRemoteDataSource
  private let local: any CaptureArchiveLocalDataSource
  private var hasLoaded = false

  init(
    remote: any CaptureArchiveRemoteDataSource = LiveCaptureArchiveRemoteDataSource(),
    local: any CaptureArchiveLocalDataSource = LiveCaptureArchiveLocalDataSource()
  ) {
    self.remote = remote
    self.local = local
  }

  var hasMore: Bool {
    guard let count else { return false }
    return captures.count < count
  }

  func loadInitial(force: Bool = false) async {
    guard force || !hasLoaded else { return }
    hasLoaded = true
    isLoading = true
    errorMessage = nil

    let query = CaptureArchiveQuery()
    do {
      async let cachedRows = local.list(query: query)
      async let cachedCount = local.count(query: query)
      let (unvalidatedRows, localCount) = try await (cachedRows, cachedCount)
      captures = try validatedArchiveRows(unvalidatedRows)
      count = localCount
    } catch {
      // A stale cache must not block the server-authoritative source-scoped
      // request. The subsequent failure still surfaces honestly below.
    }

    await reloadFirstPage(query: query)
    isLoading = false
  }

  func refresh() async {
    await loadInitial(force: true)
  }

  func loadNextPage() async {
    guard !isLoadingMore, !isLoading, errorMessage == nil, hasMore else { return }
    isLoadingMore = true
    defer { isLoadingMore = false }

    let query = CaptureArchiveQuery(offset: captures.count)
    do {
      let page = try validatedArchiveRows(await remote.list(query: query))
      for capture in page where !captures.contains(where: { $0.id == capture.id }) {
        captures.append(capture)
        try? await local.store(capture)
      }
    } catch {
      // Do not retry without the source predicate. The user must choose Refresh.
      errorMessage = "Omi-device captures are unavailable. Refresh to try again."
    }
  }

  func select(_ capture: ServerConversation) {
    selectedCapture = capture
  }

  /// Detail always revalidates from the source-scoped list's selected capture.
  /// It never falls back to a generic list request if the detail read fails.
  func loadDetail(id: String) async -> ServerConversation? {
    if let cached = try? await local.detail(id: id), cached.isOmiCaptureArchiveRecord {
      selectedCapture = cached
    }

    do {
      let detail = try await remote.detail(id: id)
      guard detail.isOmiCaptureArchiveRecord else {
        errorMessage = "This capture is no longer available."
        return nil
      }
      selectedCapture = detail
      if let index = captures.firstIndex(where: { $0.id == detail.id }) {
        captures[index] = detail
      } else {
        captures.insert(detail, at: 0)
      }
      try? await local.store(detail)
      return detail
    } catch {
      errorMessage = "This Omi-device capture is unavailable. Refresh to try again."
      return nil
    }
  }

  private func reloadFirstPage(query: CaptureArchiveQuery) async {
    do {
      async let remoteRows = remote.list(query: query)
      async let remoteCount = remote.count(query: query)
      let (unvalidatedRows, remoteTotal) = try await (remoteRows, remoteCount)
      let rows = try validatedArchiveRows(unvalidatedRows)
      captures = rows
      count = remoteTotal
      errorMessage = nil
      for capture in rows {
        try? await local.store(capture)
      }
    } catch {
      // Cache rows may remain visible, but the state is never silently healthy:
      // archive data is unavailable rather than silently replaced with a mixed list.
      errorMessage = "Omi-device captures are unavailable. Refresh to try again."
    }
  }

  private func validatedArchiveRows(_ rows: [ServerConversation]) throws -> [ServerConversation] {
    guard rows.allSatisfy(\.isOmiCaptureArchiveRecord) else {
      throw CaptureArchiveRepositoryError.receivedNonArchiveCapture
    }
    return rows
  }
}
