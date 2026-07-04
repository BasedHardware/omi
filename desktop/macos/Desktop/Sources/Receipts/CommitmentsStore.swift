import Foundation
import SwiftUI

/// Observable store for the Commitments page UI. Mirrors the TasksStore pattern
/// but simpler — local-only, no backend sync.
@MainActor
class CommitmentsStore: ObservableObject {
  static let shared = CommitmentsStore()

  @Published var pendingCommitments: [CommitmentRecord] = []
  @Published var fulfilledCommitments: [CommitmentRecord] = []
  @Published var missedCommitments: [CommitmentRecord] = []
  @Published var isLoading = false
  @Published var error: String?

  private init() {}

  // MARK: - Load

  func loadCommitments() async {
    isLoading = true
    defer { isLoading = false }

    do {
      async let pending = CommitmentStorage.shared.getCommitments(status: .pending)
      async let fulfilled = CommitmentStorage.shared.getCommitments(status: .fulfilled)
      async let missed = CommitmentStorage.shared.getCommitments(status: .missed)

      let (p, f, m) = try await (pending, fulfilled, missed)
      pendingCommitments = sortPending(p)
      fulfilledCommitments = f
      missedCommitments = m
      error = nil
    } catch {
      self.error = error.localizedDescription
      log("CommitmentsStore: Load failed: \(error.localizedDescription)")
    }
  }

  // MARK: - Mutations

  func markFulfilled(_ commitment: CommitmentRecord, evidence: String?, bySessionId: Int64?) async {
    guard let id = commitment.id else { return }
    do {
      try await CommitmentStorage.shared.markFulfilled(id: id, evidence: evidence, bySessionId: bySessionId)
      CommitmentNotificationScheduler.shared.cancelReminder(commitmentId: id)
      await loadCommitments()
    } catch {
      log("CommitmentsStore: markFulfilled failed: \(error.localizedDescription)")
    }
  }

  func markMissed(_ commitment: CommitmentRecord) async {
    guard let id = commitment.id else { return }
    do {
      try await CommitmentStorage.shared.markMissed(id: id)
      CommitmentNotificationScheduler.shared.cancelReminder(commitmentId: id)
      await loadCommitments()
    } catch {
      log("CommitmentsStore: markMissed failed: \(error.localizedDescription)")
    }
  }

  func markPending(_ commitment: CommitmentRecord) async {
    guard let id = commitment.id else { return }
    do {
      try await CommitmentStorage.shared.updateStatus(id: id, status: .pending)
      if commitment.deadline != nil {
        CommitmentNotificationScheduler.shared.scheduleReminder(for: commitment)
      }
      await loadCommitments()
    } catch {
      log("CommitmentsStore: markPending failed: \(error.localizedDescription)")
    }
  }

  func updateDeadline(_ commitment: CommitmentRecord, deadline: Date?) async {
    guard let id = commitment.id else { return }
    do {
      try await CommitmentStorage.shared.updateDeadline(id: id, deadline: deadline)
      var updated = commitment
      updated.deadline = deadline
      if deadline != nil {
        CommitmentNotificationScheduler.shared.scheduleReminder(for: updated)
      } else {
        CommitmentNotificationScheduler.shared.cancelReminder(commitmentId: id)
      }
      await loadCommitments()
    } catch {
      log("CommitmentsStore: updateDeadline failed: \(error.localizedDescription)")
    }
  }

  func deleteCommitment(_ commitment: CommitmentRecord) async {
    guard let id = commitment.id else { return }
    do {
      try await CommitmentStorage.shared.deleteCommitment(id: id)
      CommitmentNotificationScheduler.shared.cancelReminder(commitmentId: id)
      await loadCommitments()
    } catch {
      log("CommitmentsStore: delete failed: \(error.localizedDescription)")
    }
  }

  // MARK: - Helpers

  private func sortPending(_ commitments: [CommitmentRecord]) -> [CommitmentRecord] {
    commitments.sorted { a, b in
      let aDeadline = a.deadline ?? Date.distantFuture
      let bDeadline = b.deadline ?? Date.distantFuture
      return aDeadline < bDeadline
    }
  }

  var allCommitments: [CommitmentRecord] {
    pendingCommitments + missedCommitments + fulfilledCommitments
  }

  var pendingCount: Int { pendingCommitments.count }
  var overdueCount: Int { pendingCommitments.filter { $0.isOverdue }.count }
}
