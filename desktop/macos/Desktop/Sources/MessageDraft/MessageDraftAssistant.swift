import AppKit
import Foundation

/// Settings for message-draft assist. One switch, like form assist; the bounds below
/// are cost contracts, not preferences.
@MainActor
enum MessageDraftSettings {
  private static let enabledKey = "messageDraftEnabled"

  static var isEnabled: Bool {
    get {
      guard UserDefaults.standard.object(forKey: enabledKey) != nil else { return true }
      return UserDefaults.standard.bool(forKey: enabledKey)
    }
    set { UserDefaults.standard.set(newValue, forKey: enabledKey) }
  }
}

private struct MessageDraftModelResponse: Decodable {
  let subject: String?
  let body: String
}

/// Offers to write the message the user is about to send.
///
/// The shape is deliberately opposite to form assist's: showing the card is free — no
/// model call, no tree walk, one focused-element read — and the model runs only when
/// the user says yes. That is what pays for firing on something as common as an empty
/// compose box. What the user typed into "Add context", the conversation on screen, and
/// their memories are the three sources; the draft comes back on the same card with a
/// copy button, and the context box stays for "shorter" / "more formal" refinements.
actor MessageDraftAssistant: ProactiveAssistant {
  nonisolated let identifier = "message-draft"
  nonisolated let displayName = "Message Draft"

  var isEnabled: Bool {
    get async { await MainActor.run { MessageDraftSettings.isEnabled } }
  }

  private let geminiClient: GeminiClient

  /// Conversations the user said ✗ to. Nothing re-offers them until relaunch.
  private var declined: Set<String> = []
  /// The last draft per conversation, so coming back re-shows it instead of a bare
  /// prompt that forgot the work it already did. Newest last, bounded.
  private var drafts: [(fingerprint: String, draft: MessageDraft)] = []
  private let maxRememberedDrafts = 40

  /// The window the card on screen belongs to; leaving it takes the card away.
  /// The context the card on screen belongs to. Not the window: a browser keeps one
  /// window across every tab, and a draft written for one conversation must not still be
  /// on screen over the next.
  private var cardContext: PanelContext?
  private var isEvaluating = false

  /// The last refusal logged, so a quiet screen writes one line, not one per sweep.
  private var lastRefusal: (key: FormWindowKey, reason: String)?

  /// Bounds the model calls, which here are all user-initiated ✓ clicks — generous by
  /// design, present only so a stuck retry loop cannot spend the day's tokens.
  private var draftsToday: [Date] = []
  private let dailyDraftBudget = 60
  /// Past this the model is writing a document, not a message.
  static let maxDraftLength = 4_000

  init() throws {
    geminiClient = try GeminiClient(
      model: ModelQoS.Gemini.proactive,
      fallbackModel: ModelQoS.Gemini.lightweight,
      workload: .extraction
    )
  }

  // MARK: - Trigger

  func startWatching() async {
    await MainActor.run {
      FormWatcher.shared.subscribe(identifier) { reason in
        Task { await self.evaluate(reason: reason) }
      }
      // Offering waits for the screen to settle; taking the card away does not.
      FormWatcher.shared.subscribeImmediate(identifier) {
        Task { await self.retireCardIfUserLeft() }
      }
    }
  }

  func onContextSwitch(departingFrame: CapturedFrame?, newApp: String, newWindowTitle: String?) async {
    await evaluate(reason: .appSwitch)
  }

  func shouldAnalyze(frameNumber: Int, timeSinceLastAnalysis: TimeInterval) -> Bool { false }

  func analyze(frame: CapturedFrame) async -> AssistantResult? { nil }

  func handleResult(_ result: AssistantResult, sendEvent: @escaping @Sendable (String, [String: Any]) -> Void) async {}

  private func evaluate(reason: FormScanReason) async {
    guard !isEvaluating else { return }
    isEvaluating = true
    defer { isEvaluating = false }
    guard await isEnabled else { return }

    guard let key = await MainActor.run(body: { FormFieldScanner.frontWindowKey() }) else { return }
    await retireCardIfUserLeft()

    let excluded = await MainActor.run {
      // The same list the user curated for live suggestions: "do not watch me in this
      // app" is one preference, not two.
      SuggestionAssistantSettings.shared.isAppExcluded(key.appName)
    }
    guard !excluded else {
      refuse(key, "excluded-app")
      return
    }

    let outcome = await MainActor.run { MessageComposeScanner.scanFocusedCompose() }
    guard let snapshot = outcome.snapshot else {
      refuse(key, outcome.refusal ?? "unknown")
      return
    }
    guard !declined.contains(snapshot.fingerprint) else {
      refuse(key, "declined")
      return
    }

    let alreadyMine = await MainActor.run {
      MessageDraftCardController.shared.isPresenting
        && MessageDraftCardController.shared.fingerprint == snapshot.fingerprint
    }
    guard !alreadyMine else {
      cardContext = await MainActor.run { PanelContext.front() }
      await MainActor.run { MessageDraftCardController.shared.ensureVisiblePlacement() }
      return
    }

    // One overlay at a time, whoever got there first.
    let blocked = await MainActor.run {
      CloudConnectorGuidanceOverlay.shared.isPresenting
        || MessageDraftCardController.shared.isPresenting
    }
    guard !blocked else {
      refuse(key, "another-card")
      return
    }

    // The card must never carry one account's drafts into another's session.
    guard RuntimeOwnerIdentity.currentOwnerId() != nil else {
      refuse(key, "no-signed-in-owner")
      return
    }

    log(
      "MessageDraft: offering in \(snapshot.context.appName) "
        + "surface=\(snapshot.surface.displayName) reason=\(reason.rawValue)")
    cardContext = await MainActor.run { PanelContext.front() }
    let restored = drafts.last(where: { $0.fingerprint == snapshot.fingerprint })?.draft
    await MainActor.run {
      MessageDraftCardController.shared.present(
        fingerprint: snapshot.fingerprint,
        appDisplayName: snapshot.surface.displayName,
        targetWindowFrame: snapshot.windowFrame,
        restore: restored,
        onGenerate: { [weak self] context, refining in
          guard let self else {
            return .failure(MessageDraftError.assistantGone)
          }
          return await self.generate(context: context, refining: refining, snapshot: snapshot)
        },
        onDecline: { [weak self] in
          guard let self else { return }
          Task { await self.recordDecline(snapshot.fingerprint) }
        }
      )
    }
  }

  /// One line per (window, reason), not per sweep. "not-messaging" is the whole quiet
  /// life of every non-messaging app, so it alone stays unlogged.
  private func refuse(_ key: FormWindowKey, _ reason: String) {
    guard reason != MessageComposeGate.Decision.notMessaging.rawValue else { return }
    guard lastRefusal?.key != key || lastRefusal?.reason != reason else { return }
    lastRefusal = (key, reason)
    log("MessageDraft: gate=\(reason) app=\(key.appName)")
  }

  private func retireCardIfUserLeft() async {
    guard let cardContext else { return }
    let stillThere = await MainActor.run {
      PanelContext.front().map { $0.matches(cardContext, grain: .context) } ?? true
    }
    guard !stillThere else { return }
    self.cardContext = nil
    await MainActor.run { MessageDraftCardController.shared.dismiss() }
  }

  private func recordDecline(_ fingerprint: String) {
    declined.insert(fingerprint)
    log("MessageDraft: declined")
  }

  // MARK: - On demand

  /// Draft the message because the user asked out loud, and put it on a voice panel.
  ///
  /// The offer card exists to ask permission; being asked *is* the permission, so this
  /// goes straight to the model, with the panel up and pending while it writes. When no
  /// compose box is focused there is still a request to answer — the window in front
  /// becomes the context and the draft lands on the panel, which is the only surface a
  /// spoken answer has to leave something behind on.
  func draftOnDemand(context: String) async -> String {
    guard RuntimeOwnerIdentity.currentOwnerId() != nil else { return "No signed-in Omi account." }
    let scanned = await MainActor.run { MessageComposeScanner.scanFocusedCompose() }.snapshot
    let fallback = scanned == nil ? await frontWindowSnapshot() : nil
    guard let snapshot = scanned ?? fallback else {
      return "No window in front to draft from."
    }

    let title = scanned == nil ? "Draft" : "Draft for \(snapshot.surface.displayName)"
    let work = CancellableWork()
    await MainActor.run {
      PanelSession.present(
        title: title,
        subtitle: "Writing your message\u{2026}",
        fields: [
          CloudConnectorCopyField(
            id: "draft-body", label: "", value: "", masksValue: false, wraps: true,
            isPending: true)
        ],
        // A draft is about the conversation in front of the user, so it leaves with it.
        // Its liveness is the context alone: re-running the compose gate would take the
        // panel away the moment they paste the draft into the box it was written for.
        grain: .context,
        origin: .requested,
        onCancel: { work.cancel() }
      )
    }

    log("MessageDraft: on-demand panel pending for \(snapshot.surface.displayName)")

    do {
      let result = try await work.run {
        await self.generate(context: context, refining: nil, snapshot: snapshot)
      }
      guard await !work.isCancelled else { return "Cancelled." }
      switch result {
      case .failure(let error):
        _ = await MainActor.run { PanelSession.dismiss() }
        if case MessageDraftError.budgetSpent = error {
          return "Message drafting has spent its budget for today."
        }
        return "Could not write the draft."
      case .success(let draft):
        var fields: [CloudConnectorCopyField] = []
        if let subject = draft.subject, !subject.isEmpty {
          fields.append(
            CloudConnectorCopyField(
              id: "draft-subject", label: "Subject", value: subject, masksValue: false))
        }
        fields.append(
          CloudConnectorCopyField(
            id: "draft-body", label: "", value: draft.body, masksValue: false, wraps: true))
        await MainActor.run {
          PanelSession.update(subtitle: "Copy it with the button.", fields: fields)
        }
        log("MessageDraft: on-demand draft on screen, \(draft.body.count) chars")
        return "Draft is on screen to copy."
      }
    } catch {
      return "Cancelled."
    }
  }

  /// The frontmost window described in compose terms, for a draft asked for somewhere
  /// with no compose box. Nothing is focused and nothing is typed — the window title and
  /// the screenshot taken at generate time are the whole context, which is exactly what
  /// the user can see while asking.
  private func frontWindowSnapshot() async -> MessageComposeSnapshot? {
    await MainActor.run {
      guard let app = NSWorkspace.shared.frontmostApplication,
        app.processIdentifier != ProcessInfo.processInfo.processIdentifier
      else { return nil }
      let info = ScreenCaptureService.getActiveWindowInfo()
      let appName = app.localizedName ?? ""
      return MessageComposeSnapshot(
        context: MessageComposeContext(
          appName: appName,
          windowTitle: info.windowTitle ?? "",
          focusedRole: "",
          focusedLabel: "",
          focusedValue: "",
          isSecure: false,
          pageURL: ""
        ),
        surface: .nativeApp(appName),
        windowFrame: nil,
        windowID: info.windowID
      )
    }
  }

  // MARK: - Drafting

  enum MessageDraftError: Error {
    case assistantGone
    case budgetSpent
    case emptyDraft
  }

  private func generate(
    context: String,
    refining: MessageDraft?,
    snapshot: MessageComposeSnapshot
  ) async -> Result<MessageDraft, Error> {
    let now = Date()
    draftsToday = draftsToday.filter { Calendar.current.isDate($0, inSameDayAs: now) }
    guard draftsToday.count < dailyDraftBudget else {
      log("MessageDraft: daily draft budget spent")
      return .failure(MessageDraftError.budgetSpent)
    }
    draftsToday.append(now)

    // The screenshot is taken at ✓, not at offer time: the conversation the draft
    // answers is whatever is on screen the moment the user says yes.
    let image = await windowImage(windowID: snapshot.windowID)
    let identity = await MainActor.run {
      (name: AuthService.shared.displayName, email: AuthState.shared.userEmail ?? "")
    }
    let memories = await recallMemories()
    let prompt = MessageDraftPromptBuilder.prompt(
      snapshot: snapshot,
      userContext: context,
      refining: refining,
      memories: memories,
      hasImage: image != nil,
      userName: identity.name,
      userEmail: identity.email
    )
    log(
      "MessageDraft: drafting for \(snapshot.surface.displayName) "
        + "context=\(context.isEmpty ? "none" : "\(context.count) chars") "
        + "refine=\(refining != nil) memories=\(memories.count) screenshot=\(image != nil)")

    do {
      let response = try await {
        if let image {
          return try await geminiClient.sendRequest(
            prompt: prompt,
            imageData: image,
            systemPrompt: Self.systemPrompt,
            responseSchema: Self.responseSchema
          )
        }
        return try await geminiClient.sendRequest(
          prompt: prompt,
          systemPrompt: Self.systemPrompt,
          responseSchema: Self.responseSchema
        )
      }()
      guard let data = response.data(using: .utf8) else {
        return .failure(MessageDraftError.emptyDraft)
      }
      let decoded = try JSONDecoder().decode(MessageDraftModelResponse.self, from: data)
      guard let draft = MessageDraftPolicy.accepted(subject: decoded.subject, body: decoded.body)
      else {
        log("MessageDraft: model returned nothing usable")
        return .failure(MessageDraftError.emptyDraft)
      }
      remember(draft, for: snapshot.fingerprint)
      log("MessageDraft: draft ready, \(draft.body.count) chars")
      return .success(draft)
    } catch {
      logError("MessageDraft: drafting failed", error: error)
      return .failure(error)
    }
  }

  private func remember(_ draft: MessageDraft, for fingerprint: String) {
    drafts.removeAll { $0.fingerprint == fingerprint }
    drafts.append((fingerprint, draft))
    if drafts.count > maxRememberedDrafts {
      drafts.removeFirst(drafts.count - maxRememberedDrafts)
    }
  }

  /// Best effort, exactly like form assist: a conversation is still draftable from the
  /// window title and the user's context when the shutter fails.
  private func windowImage(windowID: CGWindowID?) async -> Data? {
    guard let windowID else { return nil }
    let service = ScreenCaptureService()
    guard case .success(let image) = await service.captureWindowCGImage(windowID: windowID),
      let encoded = service.encodeJPEG(from: image)
    else { return nil }
    return SuggestionFramePreview.downscaledJPEG(from: encoded)
  }

  /// The synthesized profile plus recent memories — the same recall form assist uses,
  /// minus the field-label keyword pass, because a compose box has no labels to mine.
  private func recallMemories() async -> [String] {
    var profile: [String] = []
    if let latest = await AIUserProfileService.shared.getLatestProfile() {
      let text = latest.profileText.trimmingCharacters(in: .whitespacesAndNewlines)
      if !text.isEmpty { profile.append(text) }
    }
    var recent: [String] = []
    do {
      recent = try await MemoryStorage.shared.searchLocalMemories(
        query: "", limit: FormAssistRecall.recencyFetchLimit
      ).map(\.content)
    } catch {
      logError("MessageDraft: memory recall unavailable", error: error)
    }
    return FormAssistRecall.selected(matched: profile, recent: recent)
  }

  // MARK: - Prompts

  private static let systemPrompt = """
    You write the message a user is about to send, so they can paste it and hit send.

    Your sources, in order of authority:
    - The user's instruction, when there is one. It says what the message is for and it
      wins every conflict.
    - The screenshot: the conversation or email thread on screen. Reply to what was
      actually said. Match the language it is written in.
    - The facts stored about the user. Any concrete claim — what they do, what they
      built, when they are free — comes from here or from the thread, never from
      imagination.

    First work out which side of the conversation is the user. You are given their
    name and email. In chat apps the user's own messages are the ones aligned right
    (or highlighted); the other person's are on the left. In email threads, match
    sender names and addresses against the user's. The draft is ALWAYS the user's
    next message TO the other side — never the other person's voice, and never a
    reply to something the user themself said last unless they are following up.

    Write in the user's voice, matched to the medium:
    - A chat message is short, plain, and unsigned. No "I hope this finds you well."
    - An email gets a subject, a greeting if the thread uses one, and a sign-off with
      the user's first name if the facts give it. Skip the subject when you are given a
      chat app.

    NEVER:
    - Invent facts, commitments, dates, prices, or feelings the sources do not support.
    - Promise anything on the user's behalf that neither their instruction nor the
      thread establishes.
    - Pad. Say what the message needs to say and stop.

    When asked to revise a previous draft, keep everything the user did not ask to
    change.

    The draft goes on the user's clipboard and into a real conversation; a wrong claim
    costs them more than a shorter message would.
    """

  private static let responseSchema = GeminiRequest.GenerationConfig.ResponseSchema(
    type: "object",
    properties: [
      "subject": .init(
        type: "string",
        description: "Email subject line. Empty string for chat apps."),
      "body": .init(
        type: "string",
        description: "The message, exactly as the user should send it."),
    ],
    required: ["body"]
  )

  func clearPendingWork() async {}

  func stop() async {
    cardContext = nil
    await MainActor.run {
      FormWatcher.shared.unsubscribe(identifier)
      MessageDraftCardController.shared.dismiss()
    }
  }
}

/// Builds the user-turn prompt. Pure, so what the model is told is testable.
enum MessageDraftPromptBuilder {
  static func prompt(
    snapshot: MessageComposeSnapshot,
    userContext: String,
    refining: MessageDraft?,
    memories: [String],
    hasImage: Bool,
    userName: String = "",
    userEmail: String = ""
  ) -> String {
    var sections: [String] = []
    sections.append(
      """
      == WHERE THIS MESSAGE WILL BE SENT ==
      App: \(snapshot.surface.displayName)
      Window: \(snapshot.context.windowTitle.isEmpty ? "(no title)" : snapshot.context.windowTitle)
      \(hasImage
        ? "The attached screenshot is that window right now — the conversation to answer."
        : "No screenshot available; go by the window title and the instruction.")
      """
    )

    if !userName.isEmpty || !userEmail.isEmpty {
      sections.append(
        """
        == WHO THE USER IS ==
        \(userName.isEmpty ? "" : "Name: \(userName)\n")\(userEmail.isEmpty ? "" : "Email: \(userEmail)\n")\
        The draft is this person's next message. Messages from anyone else in the
        thread are the other side, to be replied to.
        """
      )
    }

    let instruction = userContext.trimmingCharacters(in: .whitespacesAndNewlines)
    sections.append(
      """
      == THE USER'S INSTRUCTION ==
      \(instruction.isEmpty
        ? "(none — draft the reply the conversation on screen is waiting for)"
        : instruction)
      """
    )

    if let refining {
      sections.append(
        """
        == THE DRAFT TO REVISE ==
        \(refining.subject.map { "Subject: \($0)\n" } ?? "")\(refining.body)

        Apply the instruction above to this draft. Keep what it does not ask to change.
        """
      )
    }

    if !memories.isEmpty {
      sections.append(
        """
        == WHAT OMI KNOWS ABOUT THIS USER ==
        \(memories.map { "- \($0)" }.joined(separator: "\n"))
        """
      )
    }

    return sections.joined(separator: "\n\n")
  }
}

/// The bar a model draft has to clear before it reaches the card.
enum MessageDraftPolicy {
  static func accepted(subject: String?, body: String) -> MessageDraft? {
    let body = body.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !body.isEmpty, body.count <= MessageDraftAssistant.maxDraftLength else { return nil }
    let subject = subject?.trimmingCharacters(in: .whitespacesAndNewlines)
    return MessageDraft(subject: subject.flatMap { $0.isEmpty ? nil : $0 }, body: body)
  }
}
