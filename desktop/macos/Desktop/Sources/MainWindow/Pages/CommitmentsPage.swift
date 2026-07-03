import SwiftUI

struct CommitmentsPage: View {
  @ObservedObject private var store = CommitmentsStore.shared
  @State private var selectedCommitmentId: Int64?

  var body: some View {
    VStack(spacing: 0) {
      headerView
      Divider().background(OmiColors.border)
      contentScrollView
    }
    .background(OmiColors.backgroundPrimary)
    .task {
      await store.loadCommitments()
    }
    .refreshable {
      await store.loadCommitments()
    }
  }

  // MARK: - Header

  private var headerView: some View {
    HStack {
      Text("Commitments")
        .font(.title2)
        .fontWeight(.semibold)
        .foregroundColor(OmiColors.textPrimary)

      if store.pendingCount > 0 {
        Text("\(store.pendingCount)")
          .font(.caption)
          .fontWeight(.semibold)
          .foregroundColor(OmiColors.backgroundPrimary)
          .padding(.horizontal, 8)
          .padding(.vertical, 2)
          .background(OmiColors.warning)
          .clipShape(Capsule())
      }

      Spacer()

      if store.isLoading {
        ProgressView()
          .scaleEffect(0.7)
      }
    }
    .padding(.horizontal, 20)
    .padding(.vertical, 12)
  }

  // MARK: - Content

  @ViewBuilder
  private var contentScrollView: some View {
    if store.isLoading && store.allCommitments.isEmpty {
      loadingView
    } else if let error = store.error {
      errorView(error)
    } else if store.allCommitments.isEmpty {
      emptyView
    } else {
      ScrollView {
        LazyVStack(spacing: 16) {
          if !store.pendingCommitments.filter({ $0.isOverdue }).isEmpty {
            commitmentSection(
              title: "Overdue",
              icon: "exclamationmark.circle.fill",
              color: OmiColors.error,
              commitments: store.pendingCommitments.filter { $0.isOverdue }
            )
          }

          let onTrack = store.pendingCommitments.filter { !$0.isOverdue }
          if !onTrack.isEmpty {
            commitmentSection(
              title: "Pending",
              icon: "clock.fill",
              color: OmiColors.warning,
              commitments: onTrack
            )
          }

          if !store.missedCommitments.isEmpty {
            commitmentSection(
              title: "Missed",
              icon: "xmark.circle.fill",
              color: OmiColors.error,
              commitments: store.missedCommitments
            )
          }

          if !store.fulfilledCommitments.isEmpty {
            commitmentSection(
              title: "Fulfilled",
              icon: "checkmark.circle.fill",
              color: OmiColors.success,
              commitments: store.fulfilledCommitments
            )
          }
        }
        .padding(20)
      }
    }
  }

  // MARK: - Section

  private func commitmentSection(
    title: String,
    icon: String,
    color: Color,
    commitments: [CommitmentRecord]
  ) -> some View {
    VStack(alignment: .leading, spacing: 8) {
      HStack(spacing: 6) {
        Image(systemName: icon)
          .foregroundColor(color)
          .font(.caption)
        Text(title)
          .font(.headline)
          .foregroundColor(OmiColors.textSecondary)
        Text("\(commitments.count)")
          .font(.caption)
          .foregroundColor(OmiColors.textTertiary)
      }
      .padding(.bottom, 4)

      ForEach(commitments, id: \.id) { commitment in
        CommitmentRow(commitment: commitment, color: color)
          .contextMenu {
            Button("Mark as Fulfilled") {
              Task { await store.markFulfilled(commitment, evidence: nil, bySessionId: nil) }
            }
            Button("Mark as Missed") {
              Task { await store.markMissed(commitment) }
            }
            Button("Mark as Pending") {
              Task { await store.markPending(commitment) }
            }
            Divider()
            Button("Delete", role: .destructive) {
              Task { await store.deleteCommitment(commitment) }
            }
          }
      }
    }
  }

  // MARK: - States

  private var loadingView: some View {
    VStack(spacing: 12) {
      ProgressView()
        .scaleEffect(0.8)
      Text("Loading commitments...")
        .font(.caption)
        .foregroundColor(OmiColors.textTertiary)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
  }

  private func errorView(_ message: String) -> some View {
    VStack(spacing: 12) {
      Image(systemName: "exclamationmark.triangle.fill")
        .font(.title)
        .foregroundColor(OmiColors.error)
      Text(message)
        .font(.caption)
        .foregroundColor(OmiColors.textTertiary)
        .multilineTextAlignment(.center)
      Button("Retry") {
        Task { await store.loadCommitments() }
      }
      .buttonStyle(.bordered)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
  }

  private var emptyView: some View {
    VStack(spacing: 12) {
      Image(systemName: "handshake.fill")
        .font(.system(size: 36))
        .foregroundColor(OmiColors.textTertiary)
      Text("No commitments yet")
        .font(.headline)
        .foregroundColor(OmiColors.textSecondary)
      Text("Commitments you make in conversations will appear here")
        .font(.caption)
        .foregroundColor(OmiColors.textTertiary)
        .multilineTextAlignment(.center)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
  }
}

// MARK: - Commitment Row

private struct CommitmentRow: View {
  let commitment: CommitmentRecord
  let color: Color

  var body: some View {
    HStack(alignment: .top, spacing: 10) {
      RoundedRectangle(cornerRadius: 2)
        .fill(color)
        .frame(width: 3)

      VStack(alignment: .leading, spacing: 4) {
        Text(commitment.text)
          .font(.body)
          .foregroundColor(OmiColors.textPrimary)
          .fixedSize(horizontal: false, vertical: true)

        HStack(spacing: 12) {
          if let speaker = commitment.speaker {
            Label(speaker, systemImage: "person.fill")
              .labelStyle(.titleAndIcon)
              .font(.caption)
              .foregroundColor(OmiColors.textTertiary)
          }

          if let deadline = commitment.deadline {
            Label(
              deadline.formatted(.relative(presentation: .named)),
              systemImage: "calendar"
            )
            .labelStyle(.titleAndIcon)
            .font(.caption)
            .foregroundColor(commitment.isOverdue ? OmiColors.error : OmiColors.textTertiary)
          }
        }
      }

      Spacer()
    }
    .padding(12)
    .background(OmiColors.backgroundSecondary)
    .clipShape(RoundedRectangle(cornerRadius: 8))
    .overlay(
      RoundedRectangle(cornerRadius: 8)
        .stroke(OmiColors.border, lineWidth: 0.5)
    )
  }
}
