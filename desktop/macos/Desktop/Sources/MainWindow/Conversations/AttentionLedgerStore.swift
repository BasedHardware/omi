import Combine
import Foundation

/// The attention ledger owns eligibility; Home noise is never an attention predicate.
/// Future kinds decode as display-only so clients and backend can land independently.
struct AttentionLedgerItem: Decodable, Identifiable {
  let id: String
  let kind: String
  let conversationId: String
  let retryable: Bool
  let retry: AttentionLedgerRetry
  var title: String? = nil
  var notesOnly: Bool { kind == "conversation_notes_failed_with_outputs" }
  var canRetry: Bool {
    retryable && (notesOnly || kind == "conversation_summary_failed") && ["none", "failed"].contains(retry.state)
  }
  enum CodingKeys: String, CodingKey {
    case id, kind, retryable, retry, title
    case conversationId = "conversation_id"
  }
}

struct AttentionLedgerRetry: Decodable {
  let state: String
  var operationId: String? = nil
  enum CodingKeys: String, CodingKey {
    case state
    case operationId = "operation_id"
  }
}

struct AttentionLedgerPage: Decodable {
  var enabled: Bool? = nil
  let items: [AttentionLedgerItem]
}

extension APIClient {
  func getAttentionLedger() async throws -> AttentionLedgerPage { try await get("v1/attention-items") }
  func retryAttentionLedger(
    _ id: String, idempotencyKey: String, customBaseURL: String? = nil
  ) async throws -> AttentionLedgerRetry {
    let encoded = id.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? id
    return try await post(
      "v1/attention-items/\(encoded)/retry", customBaseURL: customBaseURL, idempotencyKey: idempotencyKey)
  }
}

/// Account-fenced retries retain errors and suppress stale ledger/list responses after success.
/// The view's existing placement switch controls admission; this store never changes tasks/events.
@MainActor
final class AttentionLedgerStore: ObservableObject {
  @Published private var items: [AttentionLedgerItem] = []
  @Published private(set) var retrying = Set<String>()
  @Published private(set) var errors = Set<String>()
  @Published private(set) var loadFailed = false
  private var accepted: [String: (conversation: String, operation: String?)] = [:]
  // Keep ambiguous attempts in memory until acknowledged, scoped to this account session.
  private var retryKeys: [String: String] = [:]
  private var readGeneration = 0
  private var session = 0
  private var identity: String?
  private let load: () async throws -> AttentionLedgerPage
  private let retryCall: (String, String) async throws -> AttentionLedgerRetry
  private let owner: () -> String?

  init(
    load: (() async throws -> AttentionLedgerPage)? = nil,
    retry: ((String, String) async throws -> AttentionLedgerRetry)? = nil,
    owner: (() -> String?)? = nil
  ) {
    self.load = load ?? { try await APIClient.shared.getAttentionLedger() }
    retryCall = retry ?? { try await APIClient.shared.retryAttentionLedger($0, idempotencyKey: $1) }
    self.owner = owner ?? { AuthState.shared.userId }
  }

  var rows: [AttentionLedgerItem] {
    var result: [AttentionLedgerItem] = []
    for item in items where !accepted.values.contains(where: { $0.conversation == item.conversationId }) {
      if let index = result.firstIndex(where: { $0.conversationId == item.conversationId }) {
        if item.notesOnly && !result[index].notesOnly { result[index] = item }
      } else {
        result.append(item)
      }
    }
    return result
  }
  var conversationIds: Set<String> { Set(rows.map(\.conversationId) + accepted.values.map(\.conversation)) }

  func reset() {
    session += 1
    readGeneration += 1
    identity = nil
    items = []
    accepted = [:]
    retryKeys = [:]
    errors = []
    retrying = []
    loadFailed = false
  }

  func refresh() async {
    let currentOwner = owner()
    if currentOwner != identity {
      reset()
      identity = currentOwner
    }
    guard currentOwner != nil else { return }
    readGeneration += 1
    let request = readGeneration
    do {
      let page = try await load()
      guard request == readGeneration, currentOwner == owner() else { return }
      let incoming = page.enabled == false ? [] : page.items
      for item in incoming where item.notesOnly {
        for (id, ack) in Array(accepted) where ack.conversation == item.conversationId && id != item.id {
          accepted.removeValue(forKey: id)
        }
      }
      for item in incoming where item.retry.state == "failed" {
        if let operation = accepted[item.id]?.operation, operation == item.retry.operationId {
          accepted.removeValue(forKey: item.id)
          errors.insert(item.id)
        }
      }
      items = incoming
      loadFailed = false
    } catch {
      if request == readGeneration, currentOwner == owner() { loadFailed = true }
    }
  }

  func retry(_ item: AttentionLedgerItem) async {
    guard item.canRetry, !retrying.contains(item.id),
      !accepted.values.contains(where: { $0.conversation == item.conversationId }),
      identity != nil, identity == owner()
    else { return }
    let key = retryKeys[item.id] ?? UUID().uuidString
    retryKeys[item.id] = key
    let attemptSession = session
    readGeneration += 1
    retrying.insert(item.id)
    errors.remove(item.id)
    defer { if attemptSession == session { retrying.remove(item.id) } }
    do {
      let result = try await retryCall(item.id, key)
      guard attemptSession == session, identity == owner() else { return }
      if ["in_progress", "succeeded", "failed"].contains(result.state) {
        retryKeys.removeValue(forKey: item.id)
      }
      guard ["in_progress", "succeeded"].contains(result.state) else { throw APIError.invalidResponse }
      accepted[item.id] = (item.conversationId, result.operationId)
      items.removeAll { $0.id == item.id }
    } catch {
      if attemptSession == session, identity == owner() {
        if case APIError.httpError(statusCode: 409, detail: "not_retryable") = error {
          retryKeys.removeValue(forKey: item.id)
        }
        errors.insert(item.id)
      }
    }
  }
}
