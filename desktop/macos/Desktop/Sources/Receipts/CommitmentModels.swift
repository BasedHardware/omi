import Foundation
import GRDB

// MARK: - Commitment Status

enum CommitmentStatus: String, Codable, CaseIterable {
  case pending
  case fulfilled
  case missed

  var displayName: String {
    switch self {
    case .pending: return "Pending"
    case .fulfilled: return "Fulfilled"
    case .missed: return "Missed"
    }
  }
}

// MARK: - Commitment Record

/// Database record for commitments — promises the user (or someone in a conversation)
/// made, tracked through to fulfillment. Local-only MVP (no backend sync).
struct CommitmentRecord: Codable, FetchableRecord, PersistableRecord, Identifiable {
  var id: Int64?

  // Core commitment fields
  var text: String
  var speaker: String?
  var deadline: Date?
  var status: String

  // Source — which conversation this came from
  var sourceSessionId: Int64?
  var sourceConversationId: String?

  // Follow-through evidence
  var fulfilledAt: Date?
  var fulfilledByEvidence: String?
  var fulfilledBySessionId: Int64?

  // Extraction metadata
  var confidence: Double?
  var embedding: Data?

  // Timestamps
  var createdAt: Date
  var updatedAt: Date

  static let databaseTableName = "commitments"

  // MARK: - Initialization

  init(
    id: Int64? = nil,
    text: String,
    speaker: String? = nil,
    deadline: Date? = nil,
    status: CommitmentStatus = .pending,
    sourceSessionId: Int64? = nil,
    sourceConversationId: String? = nil,
    fulfilledAt: Date? = nil,
    fulfilledByEvidence: String? = nil,
    fulfilledBySessionId: Int64? = nil,
    confidence: Double? = nil,
    embedding: Data? = nil,
    createdAt: Date = Date(),
    updatedAt: Date = Date()
  ) {
    self.id = id
    self.text = text
    self.speaker = speaker
    self.deadline = deadline
    self.status = status.rawValue
    self.sourceSessionId = sourceSessionId
    self.sourceConversationId = sourceConversationId
    self.fulfilledAt = fulfilledAt
    self.fulfilledByEvidence = fulfilledByEvidence
    self.fulfilledBySessionId = fulfilledBySessionId
    self.confidence = confidence
    self.embedding = embedding
    self.createdAt = createdAt
    self.updatedAt = updatedAt
  }

  mutating func didInsert(_ inserted: InsertionSuccess) {
    id = inserted.rowID
  }

  // MARK: - Computed

  var commitmentStatus: CommitmentStatus {
    CommitmentStatus(rawValue: status) ?? .pending
  }

  var isPending: Bool { commitmentStatus == .pending }
  var isFulfilled: Bool { commitmentStatus == .fulfilled }
  var isMissed: Bool { commitmentStatus == .missed }

  /// True if the deadline has passed and the commitment is still pending.
  var isOverdue: Bool {
    guard let deadline = deadline else { return false }
    return deadline < Date() && isPending
  }
}

// MARK: - Extracted Commitment (LLM output)

/// Intermediate struct produced by the LLM extractor, before persistence.
struct ExtractedCommitment: Codable {
  let text: String
  let speaker: String?
  let deadlineISO: String?
  let confidence: Double

  enum CodingKeys: String, CodingKey {
    case text
    case speaker
    case deadlineISO = "deadline_iso"
    case confidence
  }

  var deadline: Date? {
    guard let iso = deadlineISO, !iso.isEmpty else { return nil }
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    if let date = formatter.date(from: iso) { return date }
    formatter.formatOptions = [.withInternetDateTime]
    return formatter.date(from: iso)
  }
}

/// Result envelope from the extraction LLM call.
struct CommitmentExtractionResult: Codable {
  let hasCommitments: Bool
  let commitments: [ExtractedCommitment]

  enum CodingKeys: String, CodingKey {
    case hasCommitments = "has_commitments"
    case commitments
  }
}

// MARK: - Follow-Through Result

/// Result of scanning a conversation for evidence that prior commitments were fulfilled.
struct CommitmentFollowThroughResult: Codable {
  let commitmentId: Int64
  let fulfilled: Bool
  let evidence: String?
  let confidence: Double

  enum CodingKeys: String, CodingKey {
    case commitmentId = "commitment_id"
    case fulfilled
    case evidence
    case confidence
  }
}

/// LLM output envelope for a batch of follow-through checks.
struct FollowThroughBatchResult: Codable {
  let results: [CommitmentFollowThroughResult]
}

// MARK: - Processed Session Record

/// Tracks which conversations have already been analyzed for commitments,
/// regardless of whether any commitments were found. Prevents re-processing
/// of completed sessions on every launch backfill.
struct ProcessedSessionRecord: Codable, FetchableRecord, PersistableRecord {
  var id: Int64?
  var sessionId: Int64
  var processedAt: Date

  static let databaseTableName = "processed_sessions"
}

// MARK: - UserDefaults keys (commitments analysis opt-in)

let commitmentsAnalysisEnabledKey = "commitmentsAnalysisEnabled"

// MARK: - Storage Error

enum CommitmentStorageError: LocalizedError {
  case databaseNotInitialized
  case recordNotFound

  var errorDescription: String? {
    switch self {
    case .databaseNotInitialized:
      return "Commitment storage database is not initialized"
    case .recordNotFound:
      return "Commitment record not found"
    }
  }
}
