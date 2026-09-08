import Foundation

/// One-shot "open the main chat" request raised by surfaces outside the main
/// window (the floating bar's "Continue in Omi" affordances). Revealing the
/// window alone is not enough: the main window may be resting on any tab, so
/// the conversation the user asked to continue would be nowhere in sight.
///
/// Flow: the raiser calls `request()` (which also posts
/// `.openMainChatRequested`); `DesktopHomeView` selects the Chat route on the
/// notification, and `QueryShellHome` — the one chat destination — takes any
/// pending draft when its composer mounts or is already mounted.
@MainActor
final class MainChatNavigationRequestStore {
  static let shared = MainChatNavigationRequestStore()

  enum DraftDisposition { case replace, append }
  private var draftDisposition = DraftDisposition.replace
  private var draftAuthorization: RuntimeOwnerAuthorizationSnapshot?
  private let isAuthorized: (RuntimeOwnerAuthorizationSnapshot) -> Bool

  init(
    isAuthorized: @escaping (RuntimeOwnerAuthorizationSnapshot) -> Bool = RuntimeOwnerIdentity.isAuthorizationCurrent
  ) {
    self.isAuthorized = isAuthorized
  }

  private(set) var isPending = false
  /// Text to place in the composer, focused and **not sent**. Set by surfaces
  /// that want the user to glance at a suggested question before asking it
  /// (the first-real-app notch card, the daily summary's follow-up). Consumed
  /// by whichever shell's composer mounts or is already mounted.
  private(set) var pendingDraft: String?
  /// Image staged alongside the draft (the first-real-app card attaches the
  /// screen it saw, so the question has its referent in hand). Same ownership
  /// rule as the draft: every request replaces the slot, and exactly one
  /// composer takes what it finds.
  private(set) var pendingAttachment: ChatAttachment?
  /// Monotonic request generation. A requester that must suspend before it
  /// can commit (the card's frame decode) reserves a generation up front; if
  /// any other request lands in the meantime, the reservation goes stale and
  /// the older requester's commit is dropped — a slow card handoff can never
  /// overwrite a newer request's draft and attachment.
  private var requestGeneration = 0

  func request(
    draft: String? = nil,
    attachment: ChatAttachment? = nil,
    disposition: DraftDisposition = .replace,
    authorization: RuntimeOwnerAuthorizationSnapshot? = nil
  ) {
    requestGeneration &+= 1
    isPending = true
    // Every request owns the draft slot: a plain "Continue in Omi" must never
    // surface a suggestion left over from an earlier, unconsumed request.
    let trimmed = draft?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    pendingDraft = trimmed.isEmpty ? nil : draft
    pendingAttachment = attachment
    draftDisposition = disposition
    draftAuthorization = authorization
    NotificationCenter.default.post(name: .openMainChatRequested, object: nil)
  }

  /// Reserve the request slot without posting the open-chat notification.
  /// Pair with `commit(draft:attachment:generation:)` once the suspended work
  /// (e.g. the frame decode) finishes. Any `request()` or later `reserve()`
  /// invalidates the returned generation.
  @discardableResult
  func reserve() -> Int {
    requestGeneration &+= 1
    return requestGeneration
  }

  /// The current request generation — what `reserve()` last returned, unless
  /// a newer `request()` or `reserve()` has since overtaken it. A requester
  /// that reserved before suspending re-checks this before committing through
  /// its normal `request` seam.
  var currentGeneration: Int { requestGeneration }

  /// Returns whether a request was pending, and clears it. The draft survives
  /// this call so a shell that consumes the navigation before its composer is
  /// mounted still finds the text when the composer appears.
  func consume() -> Bool {
    defer { isPending = false }
    return isPending
  }

  /// Returns the pending composer draft, and clears it. Exactly one composer
  /// takes it; a second caller gets `nil`. `existingDraft` defaults to empty
  /// so plain replace-style callers can omit it.
  func consumeDraft(existingDraft: String = "") -> String? {
    defer {
      pendingDraft = nil
      draftAuthorization = nil
      draftDisposition = .replace
    }
    if let draftAuthorization, !isAuthorized(draftAuthorization) { return nil }
    guard let pendingDraft else { return nil }
    if draftDisposition == .append,
      !existingDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
      existingDraft.trimmingCharacters(in: .whitespacesAndNewlines) != pendingDraft
    {
      return existingDraft + "\n\n" + pendingDraft
    }
    return pendingDraft
  }

  /// Returns the pending attachment, and clears it. Taken together with the
  /// draft: a request is one unit, and the composer that takes the text is
  /// the one that stages the image.
  func consumeAttachment() -> ChatAttachment? {
    defer { pendingAttachment = nil }
    return pendingAttachment
  }
}

extension Notification.Name {
  static let openMainChatRequested = Notification.Name("openMainChatRequested")
}
