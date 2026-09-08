import CryptoKit
import Foundation

enum KnowledgeLedgerMirrorSnapshotError: Error, Equatable, Sendable {
  case invalidPage
  case ownerChanged
  case authorityChanged
  case cursorLoop
  case duplicateMemoryID
  case invalidAlias
  case incomplete
}

struct KnowledgeLedgerMirrorAlias: Decodable, Equatable, Sendable {
  let aliasMemoryID: String
  let canonicalMemoryID: String
  let sourceMemoryID: String
  let reason: String

  enum CodingKeys: String, CodingKey {
    case aliasMemoryID = "alias_memory_id"
    case canonicalMemoryID = "canonical_memory_id"
    case sourceMemoryID = "source_memory_id"
    case reason
  }
}

struct KnowledgeLedgerMirrorRow: Decodable, Sendable {
  let memoryID: String
  let itemRevision: Int
  let status: String
  let sourceState: String
  let canonicalMemoryID: String?
  let contentPurged: Bool
  let memory: ServerMemory?

  enum CodingKeys: String, CodingKey {
    case memoryID = "memory_id"
    case itemRevision = "item_revision"
    case status
    case sourceState = "source_state"
    case canonicalMemoryID = "canonical_memory_id"
    case contentPurged = "content_purged"
    case memory
  }
}

struct KnowledgeLedgerMirrorPage: Decodable, Sendable {
  let schemaVersion: String
  let ownerID: String
  let accountGeneration: Int
  let sourceGeneration: Int
  let writerEpoch: Int
  let headCommitID: String
  let commitSequence: Int
  let epochID: String
  let pageRevision: String
  let chainRevision: String
  let scannedCount: Int
  let projectedCount: Int
  let rows: [KnowledgeLedgerMirrorRow]
  let aliases: [KnowledgeLedgerMirrorAlias]
  let nextCursor: String?
  let finalPage: Bool
  let failureReason: String?

  enum CodingKeys: String, CodingKey {
    case schemaVersion = "schema_version"
    case ownerID = "owner_id"
    case accountGeneration = "account_generation"
    case sourceGeneration = "source_generation"
    case writerEpoch = "writer_epoch"
    case headCommitID = "head_commit_id"
    case commitSequence = "commit_sequence"
    case epochID = "epoch_id"
    case pageRevision = "page_revision"
    case chainRevision = "chain_revision"
    case scannedCount = "scanned_count"
    case projectedCount = "projected_count"
    case rows, aliases
    case nextCursor = "next_cursor"
    case finalPage = "final_page"
    case failureReason = "failure_reason"
  }
}

struct KnowledgeLedgerMirrorSnapshot: Sendable {
  static let schemaVersion = "knowledge_ledger_mirror.v1"

  let ownerID: String
  let accountGeneration: Int
  let sourceGeneration: Int
  let writerEpoch: Int
  let headCommitID: String
  let commitSequence: Int
  let epochID: String
  let contentRevision: String
  let chainRevision: String
  let scannedCount: Int
  let projectedCount: Int
  let rows: [KnowledgeLedgerMirrorRow]
  let aliases: [KnowledgeLedgerMirrorAlias]
}

/// Pure cursor-chain validator. It holds pages only in memory and publishes a
/// snapshot after the server marks the complete, generation-fenced chain final.
/// A failed or interrupted chain therefore cannot mutate the active SQLite mirror.
struct KnowledgeLedgerMirrorAccumulator {
  private let expectedOwnerID: String
  private var authority: KnowledgeLedgerMirrorPage?
  private var expectedCursor: String?
  private var seenCursors = Set<String>()
  private var seenMemoryIDs = Set<String>()
  private var aliasTargets: [String: String] = [:]
  private var contentRevision = ""
  private var scannedCount = 0
  private var projectedCount = 0
  private var chainRevision = ""
  private var rows: [KnowledgeLedgerMirrorRow] = []
  private var aliases: [KnowledgeLedgerMirrorAlias] = []
  private var complete = false

  init(expectedOwnerID: String) {
    self.expectedOwnerID = expectedOwnerID
  }

  mutating func consume(_ page: KnowledgeLedgerMirrorPage, requestedCursor: String?) throws -> String? {
    guard !complete, requestedCursor == expectedCursor,
      page.schemaVersion == KnowledgeLedgerMirrorSnapshot.schemaVersion,
      page.ownerID == expectedOwnerID,
      page.accountGeneration >= 0,
      page.sourceGeneration >= 0,
      page.writerEpoch >= 0,
      page.commitSequence >= 0,
      Self.isDigest(page.epochID),
      Self.isDigest(page.pageRevision),
      Self.isDigest(page.chainRevision),
      page.scannedCount >= scannedCount,
      page.projectedCount >= projectedCount,
      page.projectedCount - projectedCount == page.rows.count,
      page.scannedCount - scannedCount >= page.rows.count,
      !page.headCommitID.isEmpty,
      page.failureReason == nil
    else { throw KnowledgeLedgerMirrorSnapshotError.invalidPage }

    if let authority {
      guard page.ownerID == authority.ownerID,
        page.accountGeneration == authority.accountGeneration,
        page.sourceGeneration == authority.sourceGeneration,
        page.writerEpoch == authority.writerEpoch,
        page.headCommitID == authority.headCommitID,
        page.commitSequence == authority.commitSequence,
        page.epochID == authority.epochID
      else { throw KnowledgeLedgerMirrorSnapshotError.authorityChanged }
    } else {
      authority = page
    }

    for row in page.rows {
      guard Self.isBoundedID(row.memoryID), row.itemRevision > 0,
        !row.status.isEmpty, !row.sourceState.isEmpty,
        seenMemoryIDs.insert(row.memoryID).inserted
      else { throw KnowledgeLedgerMirrorSnapshotError.duplicateMemoryID }
      if row.contentPurged {
        guard row.memory == nil else { throw KnowledgeLedgerMirrorSnapshotError.invalidPage }
      } else {
        guard let memory = row.memory, memory.id == row.memoryID,
          memory.ledgerMetadata["ledger_schema_version"] == "knowledge_ledger.v1"
        else { throw KnowledgeLedgerMirrorSnapshotError.invalidPage }
      }
      if let canonicalMemoryID = row.canonicalMemoryID {
        guard Self.isBoundedID(canonicalMemoryID), canonicalMemoryID != row.memoryID else {
          throw KnowledgeLedgerMirrorSnapshotError.invalidAlias
        }
      }
      rows.append(row)
    }
    for alias in page.aliases {
      guard Self.isBoundedID(alias.aliasMemoryID), Self.isBoundedID(alias.canonicalMemoryID),
        alias.sourceMemoryID == alias.aliasMemoryID,
        alias.aliasMemoryID != alias.canonicalMemoryID,
        alias.reason == "canonical_memory_id" || alias.reason == "superseded_by"
      else { throw KnowledgeLedgerMirrorSnapshotError.invalidAlias }
      if let prior = aliasTargets[alias.aliasMemoryID], prior != alias.canonicalMemoryID {
        throw KnowledgeLedgerMirrorSnapshotError.invalidAlias
      }
      aliasTargets[alias.aliasMemoryID] = alias.canonicalMemoryID
      aliases.append(alias)
    }
    contentRevision = Self.chainedPageRevision(
      prior: contentRevision,
      pageRevision: page.pageRevision)
    scannedCount = page.scannedCount
    projectedCount = page.projectedCount
    chainRevision = page.chainRevision

    if page.finalPage {
      guard page.nextCursor == nil else { throw KnowledgeLedgerMirrorSnapshotError.invalidPage }
      complete = true
      expectedCursor = nil
      return nil
    }
    guard let nextCursor = page.nextCursor, !nextCursor.isEmpty, nextCursor.count <= 2_048,
      nextCursor != requestedCursor, seenCursors.insert(nextCursor).inserted
    else { throw KnowledgeLedgerMirrorSnapshotError.cursorLoop }
    expectedCursor = nextCursor
    return nextCursor
  }

  func finalized() throws -> KnowledgeLedgerMirrorSnapshot {
    guard complete, let authority else { throw KnowledgeLedgerMirrorSnapshotError.incomplete }
    let rowIDs = Set(rows.map(\.memoryID))
    guard aliasTargets.allSatisfy({ rowIDs.contains($0.key) && rowIDs.contains($0.value) }) else {
      throw KnowledgeLedgerMirrorSnapshotError.invalidAlias
    }
    for start in aliasTargets.keys {
      var visited = Set<String>()
      var current: String? = start
      while let node = current, let next = aliasTargets[node] {
        guard visited.insert(node).inserted else {
          throw KnowledgeLedgerMirrorSnapshotError.invalidAlias
        }
        current = next
      }
    }
    return KnowledgeLedgerMirrorSnapshot(
      ownerID: authority.ownerID,
      accountGeneration: authority.accountGeneration,
      sourceGeneration: authority.sourceGeneration,
      writerEpoch: authority.writerEpoch,
      headCommitID: authority.headCommitID,
      commitSequence: authority.commitSequence,
      epochID: authority.epochID,
      contentRevision: contentRevision,
      chainRevision: chainRevision,
      scannedCount: scannedCount,
      projectedCount: projectedCount,
      rows: rows.sorted { $0.memoryID < $1.memoryID },
      aliases: aliases.sorted {
        ($0.aliasMemoryID, $0.canonicalMemoryID, $0.reason)
          < ($1.aliasMemoryID, $1.canonicalMemoryID, $1.reason)
      })
  }

  private static func isDigest(_ value: String) -> Bool {
    value.count == 64 && value.allSatisfy { $0.isHexDigit && !$0.isUppercase }
  }

  private static func chainedPageRevision(prior: String, pageRevision: String) -> String {
    let payload = prior.isEmpty ? pageRevision : "\(prior)\n\(pageRevision)"
    return SHA256.hash(data: Data(payload.utf8))
      .map { String(format: "%02x", $0) }.joined()
  }

  private static func isBoundedID(_ value: String) -> Bool {
    !value.isEmpty && value.count <= 256 && !value.contains("/")
  }
}

extension APIClient {
  func getKnowledgeLedgerMirrorPage(
    cursor: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> KnowledgeLedgerMirrorPage {
    var endpoint = "v1/jit/knowledge-ledger/mirror-snapshot?page_size=500"
    if let cursor {
      guard let encoded = cursor.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed)
      else { throw KnowledgeLedgerMirrorSnapshotError.invalidPage }
      endpoint += "&cursor=\(encoded)"
    }
    let page: KnowledgeLedgerMirrorPage = try await get(
      endpoint,
      expectedOwnerId: authorizationSnapshot.ownerID,
      authorizationSnapshot: authorizationSnapshot)
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
      throw KnowledgeLedgerMirrorSnapshotError.ownerChanged
    }
    return page
  }

  func getKnowledgeLedgerMirrorSnapshot(
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> KnowledgeLedgerMirrorSnapshot {
    var accumulator = KnowledgeLedgerMirrorAccumulator(
      expectedOwnerID: authorizationSnapshot.ownerID)
    var cursor: String?
    while true {
      let page = try await getKnowledgeLedgerMirrorPage(
        cursor: cursor,
        authorizationSnapshot: authorizationSnapshot)
      cursor = try accumulator.consume(page, requestedCursor: cursor)
      if page.finalPage { return try accumulator.finalized() }
    }
  }
}

actor KnowledgeLedgerMirrorCoordinator {
  typealias PageFetcher =
    @Sendable (
      _ cursor: String?,
      _ authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
    ) async throws -> KnowledgeLedgerMirrorPage

  static let shared = KnowledgeLedgerMirrorCoordinator()

  private let pageFetcher: PageFetcher
  private var inFlight: [String: Task<KnowledgeLedgerMirrorReceipt, Error>] = [:]
  private var inFlightGeneration: [String: Int] = [:]

  init(
    pageFetcher: @escaping PageFetcher = { cursor, authorizationSnapshot in
      try await APIClient.shared.getKnowledgeLedgerMirrorPage(
        cursor: cursor, authorizationSnapshot: authorizationSnapshot)
    }
  ) {
    self.pageFetcher = pageFetcher
  }

  func sync(
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
    knownAuthority: JITTriggerSnapshot? = nil
  ) async throws -> KnowledgeLedgerMirrorReceipt {
    let ownerID = authorizationSnapshot.ownerID
    if let knownAuthority,
      knownAuthority.complete,
      knownAuthority.accountGeneration >= 0,
      !knownAuthority.headCommitID.isEmpty,
      knownAuthority.commitSequence >= 0,
      try await MemoryStorage.shared.authoritativeKnowledgeLedgerMirrorIsFresh(
        ownerID: ownerID,
        accountGeneration: knownAuthority.accountGeneration,
        headCommitID: knownAuthority.headCommitID,
        commitSequence: knownAuthority.commitSequence)
    {
      // The trigger snapshot is already a fresh, generation-fenced authority
      // read. A matching local receipt avoids downloading the entire mirror on
      // every captured context while retaining a cheap server freshness check.
      if let receipt = try await MemoryStorage.shared.authoritativeKnowledgeLedgerMirrorReceipt(
        ownerID: ownerID)
      {
        return receipt
      }
    }
    if let existing = inFlight[ownerID] {
      do {
        let receipt = try await existing.value
        if let knownAuthority {
          if let active = try await MemoryStorage.shared
            .authoritativeKnowledgeLedgerMirrorAuthority(ownerID: ownerID),
            active.matches(knownAuthority)
          {
            return receipt
          }
          // The joined task was started without this newer authority. It has
          // finished, so remove that stale task before immediately starting a
          // fresh known-authority sync. Never return its activation to the
          // caller that supplied the newer head.
          inFlight[ownerID] = nil
          return try await sync(
            authorizationSnapshot: authorizationSnapshot,
            knownAuthority: knownAuthority)
        }
        return receipt
      } catch {
        if let knownAuthority {
          // A failed older task cannot satisfy a known-authority caller. Once
          // it is finished, retry from the current head rather than surfacing
          // the stale task's failure or leaving an older activation active.
          inFlight[ownerID] = nil
          return try await sync(
            authorizationSnapshot: authorizationSnapshot,
            knownAuthority: knownAuthority)
        }
        throw error
      }
    }
    let task = Task {
      var cursor = try await MemoryStorage.shared.stagedKnowledgeLedgerMirrorCursor(ownerID: ownerID)
      // A durable cursor is not self-authenticating. Bind it to the trigger
      // snapshot authority that caused this sync before asking the backend to
      // resume it. A cursor from an older generation/head/sequence must be
      // discarded so its rows can never be activated under a newer head.
      if cursor != nil {
        let stagedAuthority = try await MemoryStorage.shared
          .stagedKnowledgeLedgerMirrorAuthority(ownerID: ownerID)
        let authorityMatches: Bool
        if let knownAuthority {
          authorityMatches = stagedAuthority?.matches(knownAuthority) == true
        } else {
          authorityMatches = stagedAuthority != nil
        }
        if !authorityMatches {
          try await MemoryStorage.shared.clearKnowledgeLedgerMirrorStaging(ownerID: ownerID)
          cursor = nil
        }
      }
      var restartedExpiredCursor = false
      var restartedConflictingAuthority = false
      while true {
        let page: KnowledgeLedgerMirrorPage
        do {
          page = try await pageFetcher(cursor, authorizationSnapshot)
        } catch let error as APIError {
          guard !restartedExpiredCursor, cursor != nil,
            case .httpError(let statusCode, _) = error,
            [400, 404, 410].contains(statusCode)
          else { throw error }
          // Backend cursors are intentionally short-lived. Discard only the
          // partial epoch on an explicit cursor-expiry response, then restart
          // from a newly issued head; network errors retain the cursor.
          try await MemoryStorage.shared.clearKnowledgeLedgerMirrorStaging(ownerID: ownerID)
          cursor = nil
          restartedExpiredCursor = true
          continue
        }
        if let knownAuthority {
          let pageAuthority = KnowledgeLedgerMirrorAuthority(
            ownerID: page.ownerID,
            accountGeneration: page.accountGeneration,
            sourceGeneration: page.sourceGeneration,
            writerEpoch: page.writerEpoch,
            headCommitID: page.headCommitID,
            commitSequence: page.commitSequence,
            epochID: page.epochID)
          guard pageAuthority.matches(knownAuthority) else {
            // Do not even stage rows from a head that differs from the
            // authoritative trigger snapshot. Restart once at a fresh head;
            // this prevents an old pre-deletion page from ever activating.
            guard !restartedConflictingAuthority else {
              throw KnowledgeLedgerMirrorSyncError.conflictingAuthority
            }
            restartedConflictingAuthority = true
            try await MemoryStorage.shared.clearKnowledgeLedgerMirrorStaging(ownerID: ownerID)
            cursor = nil
            continue
          }
        }
        let result = try await MemoryStorage.shared.stageAuthoritativeKnowledgeLedgerMirrorPage(
          page,
          requestedCursor: cursor,
          authorizationSnapshot: authorizationSnapshot)
        switch result {
        case .next(let nextCursor):
          cursor = nextCursor
        case .activated(let receipt):
          if let knownAuthority {
            let activeAuthority = try await MemoryStorage.shared
              .authoritativeKnowledgeLedgerMirrorAuthority(ownerID: ownerID)
            guard activeAuthority?.matches(knownAuthority) == true else {
              // Activation is transactional, but the trigger authority may
              // have advanced while pages were downloading. Do not return a
              // stale receipt; discard the newly active epoch and restart at
              // the current server head once. If it keeps moving, let the
              // caller retry with a newer trigger snapshot.
              guard !restartedConflictingAuthority else {
                throw KnowledgeLedgerMirrorSyncError.conflictingAuthority
              }
              restartedConflictingAuthority = true
              try await MemoryStorage.shared.clearKnowledgeLedgerMirrorStaging(ownerID: ownerID)
              cursor = nil
              continue
            }
          }
          return receipt
        }
      }
    }
    let generation = (inFlightGeneration[ownerID] ?? 0) + 1
    inFlightGeneration[ownerID] = generation
    inFlight[ownerID] = task
    do {
      let receipt = try await task.value
      if inFlightGeneration[ownerID] == generation {
        inFlight[ownerID] = nil
      }
      return receipt
    } catch {
      if inFlightGeneration[ownerID] == generation {
        inFlight[ownerID] = nil
      }
      throw error
    }
  }
}
