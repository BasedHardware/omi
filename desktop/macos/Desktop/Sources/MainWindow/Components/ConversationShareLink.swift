import AppKit
import OmiTheme
import SwiftUI

/// Transient user-facing feedback for the "copy share link" affordance.
///
/// Minting a conversation share link is not a plain read: the backend flips the
/// conversation's visibility to "shared" before the `https://h.omi.me` URL
/// resolves (`APIClient.getConversationShareLink`). The copied confirmation
/// therefore has to disclose who can open the link. The wording lives here so
/// every surface (conversation detail, meeting-notes chat card) discloses the
/// same thing.
enum ConversationShareLinkFeedback: Equatable {
  case copied
  case failed

  var message: String {
    switch self {
    case .copied: return "Link copied — anyone with the link can view"
    case .failed: return "Couldn't create link"
    }
  }

  var systemImage: String {
    switch self {
    case .copied: return "checkmark"
    case .failed: return "exclamationmark.triangle"
    }
  }

  /// How long the transient confirmation stays visible.
  static let displaySeconds: TimeInterval = 4
}

enum ConversationShareLinkAction {
  /// Mints a share link and copies it to the pasteboard.
  ///
  /// The URL is copied only when minting succeeded: the mint call is the
  /// visibility mutation that makes the URL resolve, so copying after a
  /// failure would hand the user a link that may 404 while the UI reads as
  /// success. The pasteboard write's own result is honored too — "Link
  /// copied" is never shown for a write NSPasteboard rejected. Failure
  /// feedback is non-blocking; callers keep every other affordance (like
  /// opening the conversation) available.
  @MainActor
  static func run(
    mintLink: () async throws -> String,
    copyToPasteboard: (String) -> Bool,
    onFailure: (Error) -> Void = { _ in }
  ) async -> ConversationShareLinkFeedback {
    do {
      let link = try await mintLink()
      return copyToPasteboard(link) ? .copied : .failed
    } catch {
      onFailure(error)
      return .failed
    }
  }
}

/// The 28pt header-toolbar control for copying a conversation share link.
///
/// Minting the link sets the conversation's visibility to shared, so the
/// transient confirmation says who can open it instead of reading as a plain
/// copy. The message renders as an overlay anchored under the glyph so the
/// header row never reflows and neighboring titles are never crushed while
/// feedback shows.
struct ConversationShareLinkButton: View {
  let conversationId: String
  var canShare: Bool = true
  var onCopied: (() -> Void)? = nil

  @State private var isCopyingLink = false
  @State private var feedback: ConversationShareLinkFeedback?
  @State private var feedbackGeneration = 0

  var body: some View {
    Button(action: { Task { await copyLink() } }) {
      Image(systemName: icon)
        .scaledFont(size: OmiType.body)
        .foregroundColor(color)
        .frame(width: 28, height: 28)
        .background(
          Circle()
            .fill(Ink.rowFillHover)
        )
    }
    .buttonStyle(.plain)
    .disabled(isCopyingLink || !canShare)
    .help(
      canShare
        ? "Copy share link — anyone with the link can view"
        : "Sharing is unavailable while the transcript is locked"
    )
    .accessibilityLabel(feedback?.message ?? "Copy share link")
    .overlay(alignment: .trailing) {
      if let feedback {
        Text(feedback.message)
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundColor(color)
          .padding(.horizontal, OmiSpacing.md)
          .padding(.vertical, OmiSpacing.xs)
          .background(
            Capsule()
              .fill(Ink.surface)
          )
          .overlay(
            Capsule()
              .stroke(Ink.glassEdge, lineWidth: 1)
          )
          .fixedSize()
          .offset(y: 34)
          .allowsHitTesting(false)
          .zIndex(1)
      }
    }
  }

  private var icon: String {
    if isCopyingLink { return "arrow.triangle.2.circlepath" }
    return feedback?.systemImage ?? "link"
  }

  private var color: Color {
    switch feedback {
    case .copied: return Ink.listeningGreen
    case .failed: return Ink.errorRed
    case nil: return Ink.secondary
    }
  }

  private func copyLink() async {
    guard !isCopyingLink, canShare else { return }
    isCopyingLink = true
    defer { isCopyingLink = false }

    let outcome = await ConversationShareLinkAction.run(
      mintLink: { try await APIClient.shared.getConversationShareLink(id: conversationId) },
      copyToPasteboard: { link in
        NSPasteboard.general.clearContents()
        return NSPasteboard.general.setString(link, forType: .string)
      },
      onFailure: { logError("Failed to get share link", error: $0) }
    )

    if outcome == .copied {
      onCopied?()
    }
    show(outcome)
  }

  private func show(_ outcome: ConversationShareLinkFeedback) {
    feedback = outcome
    feedbackGeneration += 1
    let generation = feedbackGeneration
    DispatchQueue.main.asyncAfter(deadline: .now() + ConversationShareLinkFeedback.displaySeconds) {
      // A newer click owns the confirmation; only the latest one clears it.
      guard feedbackGeneration == generation else { return }
      feedback = nil
    }
  }
}
