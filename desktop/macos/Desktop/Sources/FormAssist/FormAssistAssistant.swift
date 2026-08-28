import AppKit
import ApplicationServices
import Foundation

/// Settings for form assist. Small on purpose: the surface has one switch, and every
/// other bound (dwell, cooldown, daily budget) is a cost contract, not a preference.
@MainActor
enum FormAssistSettings {
  private static let enabledKey = "formAssistEnabled"

  static var isEnabled: Bool {
    get {
      guard UserDefaults.standard.object(forKey: enabledKey) != nil else { return true }
      return UserDefaults.standard.bool(forKey: enabledKey)
    }
    set { UserDefaults.standard.set(newValue, forKey: enabledKey) }
  }
}

/// One row Omi is offering to paste.
struct FormAssistFill: Sendable, Equatable, Decodable {
  /// What kind of answer this is. A fact is the user's own words, lifted out of a
  /// memory. A draft is written for them out of several memories, for the questions a
  /// form asks in prose — and it is theirs to edit, which is why the card says so.
  enum Kind: String, Sendable, Decodable {
    case fact
    case draft
  }

  let label: String
  let value: String
  let confidence: Double
  let kind: Kind

  private enum CodingKeys: String, CodingKey {
    case label, value, confidence, kind
  }

  init(label: String, value: String, confidence: Double, kind: Kind = .fact) {
    self.label = label
    self.value = value
    self.confidence = confidence
    self.kind = kind
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    label = try container.decode(String.self, forKey: .label)
    value = try container.decode(String.self, forKey: .value)
    confidence = try container.decode(Double.self, forKey: .confidence)
    kind = (try? container.decode(Kind.self, forKey: .kind)) ?? .fact
  }
}

struct FormAssistResult: AssistantResult {
  let fills: [FormAssistFill]
  let appName: String
  let windowFrame: CGRect?

  func toDictionary() -> [String: Any] {
    [
      "app": appName,
      "fillCount": fills.count,
      "labels": fills.map(\.label),
    ]
  }
}

private struct FormAssistModelResponse: Decodable {
  let fills: [FormAssistFill]
}

/// Owns the one form-assist card on screen, so leaving the form takes it away without
/// closing a card some other surface put up in the meantime.
@MainActor
private enum FormAssistCard {
  private static var showing: String?

  static var canPresent: Bool { showing != nil || !CloudConnectorGuidanceOverlay.shared.isPresenting }

  /// The form the card on screen is for, or nil when it is not ours / not up. Presenting
  /// rebuilds the panel, which throws away where the user dragged it — so the periodic
  /// sweep must be able to see that this exact form is already on screen.
  static func isShowing(_ fingerprint: String) -> Bool {
    showing == fingerprint && CloudConnectorGuidanceOverlay.shared.isPresenting
  }

  static func present(
    fingerprint: String,
    title: String,
    subtitle: String,
    fields: [CloudConnectorCopyField],
    near anchor: CGRect?
  ) {
    showing = fingerprint
    let overlay = CloudConnectorGuidanceOverlay.shared
    let size = overlay.fieldCopyCardSize(
      title: title, subtitle: subtitle, fieldCount: fields.count)
    let screen = NSScreen.screens.first { $0.frame.intersects(anchor ?? .zero) } ?? NSScreen.main
    let placement = screen.map {
      FormAssistCardPlacement.frame(cardSize: size, visibleFrame: $0.visibleFrame)
    }
    overlay.presentFieldCopyCard(
      title: title, subtitle: subtitle, fields: fields, near: anchor, at: placement)
  }

  static func dismissIfMine() {
    guard showing != nil else { return }
    showing = nil
    CloudConnectorGuidanceOverlay.shared.dismiss()
  }
}

/// Offers what Omi already knows about the user when they are filling in a form.
///
/// The expensive step is the model call that maps field labels to memories, and it is
/// the last thing that happens. Everything before it — is this even a form, is it a
/// login, has this exact form already been offered — is mechanical, local, and free,
/// which is what lets this run on every context switch without a cost story.
actor FormAssistAssistant: ProactiveAssistant {
  nonisolated let identifier = "form-assist"
  nonisolated let displayName = "Form Assist"

  var isEnabled: Bool {
    get async { await MainActor.run { FormAssistSettings.isEnabled } }
  }

  private let geminiClient: GeminiClient

  /// What was offered for each form already seen, newest last. Coming back to a form
  /// re-shows the card it had; it never buys a second model call for the same fields.
  private var offers: [(fingerprint: String, result: FormAssistResult)] = []
  private let maxRememberedForms = 40

  /// The window the last scan looked at, and how many times in a row it has turned out
  /// to hold no form. The periodic sweep uses this to stop re-walking a window it has
  /// already read — the walk is the only part of a quiet screen that costs anything.
  private var lastWindowKey: FormWindowKey?
  private var barrenScans = 0
  private static let barrenScanLimit = 2

  /// The window the card on screen belongs to, so leaving the form takes it away and
  /// staying on the form does not.
  private var cardWindowKey: FormWindowKey?

  /// A page load fires several triggers at once, and the model call outlives all of
  /// them. Without this the same form is answered two or three times in parallel.
  private var isEvaluating = false

  private var lastEvaluationAt: Date?
  private var evaluationsToday: [Date] = []

  /// Bounds on the model call, not on the scan. Someone applying to ten jobs in an hour
  /// is the case this exists for, so these are loose enough not to be in their way; the
  /// per-form cache is what actually keeps the call count near one per form.
  private let cooldown: TimeInterval = 15
  private let dailyEvaluationBudget = 50
  /// A drafted answer is held to a higher bar than a copied fact: the user can eyeball
  /// "Datasaur" in a heartbeat, and cannot eyeball a paragraph as fast.
  private let minConfidence = 0.6
  private let minDraftConfidence = 0.75
  private let maxRows = 12

  init() throws {
    geminiClient = try GeminiClient(
      model: ModelQoS.Gemini.proactive,
      fallbackModel: ModelQoS.Gemini.lightweight,
      workload: .extraction
    )
  }

  // MARK: - Trigger

  /// Subscribe to the moments a form can appear. Accessibility events carry them
  /// precisely; the watcher's periodic sweep is the net under apps that post none.
  func startWatching() async {
    await MainActor.run {
      FormWatcher.shared.start { reason in
        Task { await self.evaluate(reason: reason) }
      }
    }
  }

  /// Kept because it is free and it fires on app switches even where accessibility
  /// notifications are unavailable. Never the only trigger — see `FormWatcher`.
  func onContextSwitch(departingFrame: CapturedFrame?, newApp: String, newWindowTitle: String?) async {
    await evaluate(reason: .appSwitch)
  }

  func shouldAnalyze(frameNumber: Int, timeSinceLastAnalysis: TimeInterval) -> Bool { false }

  func analyze(frame: CapturedFrame) async -> AssistantResult? { nil }

  private func evaluate(reason: FormScanReason) async {
    guard !isEvaluating else { return }
    isEvaluating = true
    defer { isEvaluating = false }
    guard await isEnabled else { return }

    guard let key = await MainActor.run(body: { FormFieldScanner.frontWindowKey() }) else { return }
    await retireCardIfUserLeft(currentWindow: key)

    if key != lastWindowKey {
      lastWindowKey = key
      barrenScans = 0
    } else if reason == .periodic, barrenScans >= Self.barrenScanLimit {
      return
    }

    let excluded = await MainActor.run {
      // Deliberately the same exclusion list the user already curated for live
      // suggestions: "do not watch me in this app" is one preference, not two.
      SuggestionAssistantSettings.shared.isAppExcluded(key.appName)
    }
    guard !excluded else {
      barrenScans += 1
      return
    }

    guard let snapshot = await MainActor.run(body: { FormFieldScanner.scanFrontmostWindow() }) else {
      barrenScans += 1
      return
    }

    let decision = FormAssistGate.decide(
      fields: snapshot.fields, hasSubmitButton: snapshot.hasSubmitButton)
    guard decision == .eligible else {
      barrenScans += 1
      if barrenScans == 1 {
        log(
          "FormAssist: gate=\(decision.rawValue) app=\(snapshot.appName) "
            + "fields=\(snapshot.fields.count) fillable=\(snapshot.emptyFields.count) "
            + "submit=\(snapshot.hasSubmitButton) reason=\(reason.rawValue)")
      }
      return
    }
    barrenScans = 0
    guard await MainActor.run(body: { !FormAssistCard.isShowing(snapshot.fingerprint) }) else {
      return
    }

    if let previous = offers.last(where: { $0.fingerprint == snapshot.fingerprint }) {
      // Already answered. Re-show what it produced, or stay quiet if it produced nothing
      // — either way this form costs no more model calls and no more log noise.
      guard !previous.result.fills.isEmpty else { return }
      guard await MainActor.run(body: { FormAssistCard.canPresent }) else { return }
      await deliver(previous.result, fingerprint: snapshot.fingerprint, windowKey: key)
      return
    }

    log(
      "FormAssist: gate=eligible app=\(snapshot.appName) fields=\(snapshot.fields.count) "
        + "fillable=\(snapshot.emptyFields.count) submit=\(snapshot.hasSubmitButton) "
        + "reason=\(reason.rawValue)")

    guard await MainActor.run(body: { FormAssistCard.canPresent }) else {
      log("FormAssist: another card is on screen")
      return
    }

    let now = Date()
    if let lastEvaluationAt, now.timeIntervalSince(lastEvaluationAt) < cooldown { return }
    evaluationsToday = evaluationsToday.filter { Calendar.current.isDate($0, inSameDayAs: now) }
    guard evaluationsToday.count < dailyEvaluationBudget else {
      log("FormAssist: daily evaluation budget spent")
      return
    }

    let memories = await recallMemories(for: snapshot)
    guard !memories.isEmpty else {
      log("FormAssist: skipped (no memories) app=\(snapshot.appName)")
      return
    }

    lastEvaluationAt = now
    evaluationsToday.append(now)
    do {
      let image = await windowImage(windowID: snapshot.windowID)
      let fills = try await resolveFills(snapshot: snapshot, memories: memories, image: image)
      let result = FormAssistResult(
        fills: fills, appName: snapshot.appName, windowFrame: snapshot.windowFrame)
      remember(result, for: snapshot.fingerprint)
      guard !fills.isEmpty else {
        log("FormAssist: nothing to offer for \(snapshot.emptyFields.count) fields in \(snapshot.appName)")
        return
      }
      await deliver(result, fingerprint: snapshot.fingerprint, windowKey: key)
    } catch {
      logError("FormAssist: fill resolution failed", error: error)
    }
  }

  /// The card belongs to one window. Moving to a different one takes it away; staying on
  /// the form — even while typing, which changes nothing about the window — keeps it.
  private func retireCardIfUserLeft(currentWindow: FormWindowKey) async {
    guard let cardWindowKey, cardWindowKey != currentWindow else { return }
    self.cardWindowKey = nil
    await MainActor.run { FormAssistCard.dismissIfMine() }
  }

  /// The screenshot the model judges alongside the field labels. Best effort: a form is
  /// still worth answering from labels alone when the shutter fails.
  private func windowImage(windowID: CGWindowID?) async -> Data? {
    guard let windowID else { return nil }
    let service = ScreenCaptureService()
    guard case .success(let image) = await service.captureWindowCGImage(windowID: windowID),
      let encoded = service.encodeJPEG(from: image)
    else { return nil }
    return SuggestionFramePreview.downscaledJPEG(from: encoded)
  }

  private func remember(_ result: FormAssistResult, for fingerprint: String) {
    offers.append((fingerprint, result))
    if offers.count > maxRememberedForms {
      offers.removeFirst(offers.count - maxRememberedForms)
    }
  }

  // MARK: - Recall

  /// Everything Omi knows that could answer these fields, up to a size the model can
  /// read comfortably. Memories that match a field label are pinned first; the rest is
  /// recency. There is no local embedding index over memories — `EmbeddingService`
  /// covers tasks and screenshots — so volume plus keyword order is the honest best
  /// available without a network round trip on a path that must stay fast.
  private func recallMemories(for snapshot: FormSnapshot) async -> [String] {
    // The synthesized profile first: it is the user's own background written as prose,
    // which is where a form's open questions are answered from. A bare list of memories
    // is good at "what is their employer" and poor at "what have they been building".
    var profile: [String] = []
    if let latest = await AIUserProfileService.shared.getLatestProfile() {
      let text = latest.profileText.trimmingCharacters(in: .whitespacesAndNewlines)
      if !text.isEmpty { profile.append(text) }
    }

    var matched: [String] = []
    var recent: [String] = []

    do {
      for term in FormAssistRecall.searchTerms(for: snapshot.emptyFields.map(\.label)) {
        matched += try await MemoryStorage.shared.searchLocalMemories(query: term, limit: 10)
          .map(\.content)
      }
      recent = try await MemoryStorage.shared.searchLocalMemories(
        query: "", limit: FormAssistRecall.recencyFetchLimit
      ).map(\.content)
    } catch {
      logError("FormAssist: memory recall unavailable", error: error)
    }
    return FormAssistRecall.selected(matched: profile + matched, recent: recent)
  }

  // MARK: - Judgment

  private func resolveFills(
    snapshot: FormSnapshot,
    memories: [String],
    image: Data?
  ) async throws -> [FormAssistFill] {
    let labels = FormAssistSensitiveFields.answerable(snapshot.emptyFields.map(\.label))
    guard !labels.isEmpty else { return [] }
    log(
      "FormAssist: asking about \(labels.count) fields with \(memories.count) memories"
        + " — \(labels.joined(separator: " | "))")
    let prompt = """
      == THE FORM IN FRONT OF THE USER ==
      App: \(snapshot.appName)
      Window: \(snapshot.windowTitle.isEmpty ? "(no title)" : snapshot.windowTitle)
      \(image == nil ? "No screenshot available." : "The attached screenshot is that window right now.")

      == EMPTY FIELDS, AS THE ACCESSIBILITY TREE NAMES THEM ==
      \(labels.map { "- \($0)" }.joined(separator: "\n"))

      == WHAT OMI KNOWS ABOUT THIS USER ==
      \(memories.map { "- \($0)" }.joined(separator: "\n"))
      """

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
    guard let data = response.data(using: .utf8) else { return [] }
    let decoded = try JSONDecoder().decode(FormAssistModelResponse.self, from: data)
    // Labels, kinds and confidences only — never the values, which are the user's own
    // details and belong on the clipboard rather than in a log.
    log(
      "FormAssist: model returned "
        + decoded.fills.map { "\($0.label)[\($0.kind.rawValue) \(Int($0.confidence * 100))]" }
        .joined(separator: ", "))
    return FormAssistFillPolicy.accepted(
      decoded.fills,
      forLabels: labels,
      minConfidence: minConfidence,
      minDraftConfidence: minDraftConfidence,
      limit: maxRows)
  }

  private static let systemPrompt = """
    You help a user fill in a form using what is already known about them.

    You are given the labels of the empty fields, a screenshot of the window, and the
    facts Omi has stored about this user. Use the screenshot to see what a field is
    really asking — the heading above it, the hint beside it, how much room it gives —
    and answer under the label you were given, copied exactly as written.

    There are two kinds of answer.

    FACT — the field asks for something the user simply is or has: a name, a school, an
    employer, a link, a list of skills, a title, a location. Take the value out of the
    facts and give it in the form the field wants. Reformatting what is there is fine:
    splitting a full name into first and last, listing languages the user's own facts
    already list, giving a company name without the role around it. Set kind="fact".

    DRAFT — the field asks a question in prose, and the box is big: why this company,
    describe your experience with X, what are you looking for, tell us about a project,
    anything else we should know. Write the answer the user would write, in their voice.
    Two to five sentences unless the field clearly wants more. Set kind="draft".

    Draft generously. The card marks these as drafts and the user edits before sending,
    so a strong honest starting point is worth far more to them than a blank box — a
    form where only the name is filled in has barely helped at all. If the facts show
    relevant work, draft the answer.

    You have two sources for a draft, and both are legitimate:
    - The facts: the user's real projects, employers, technologies, results, studies.
      Every concrete claim in the draft comes from here.
    - The screenshot: the role, the company, and what this job is asking for are on the
      page in front of you. Connecting the user's real experience to what the page
      actually asks for is exactly the draft that helps — that is not inventing anything
      about the company, it is reading the page.

    So "Why <company>?" is answerable whenever the facts show work that genuinely bears
    on the role described on screen: say what the user has built and why that leads here.
    Do not claim to have used the company's product, admired it for years, or met anyone
    there unless a fact says so.

    NEVER, for either kind:
    - Invent an employer, a date, a degree, a metric, a tool, or an achievement. If the
      facts do not support the answer, leave the field out. Two right answers beat ten
      where six are guesses.
    - Answer a question the facts have nothing to bear on. If the question is about
      experience the user's facts do not show — a domain they have not worked in, a tool
      they have not used — leave it out rather than claiming it. Silence is the honest
      answer to "do you have experience selling to engineering teams" when every fact
      says they build the systems instead.
    - State enthusiasm, availability, salary, notice period, visa status, or a
      willingness to relocate that no fact establishes.
    - Assume anything about the user that the facts do not say — where they are from,
      how old they are, what languages they speak, what they identify as. The facts are
      the only source; nothing about a name or a school implies anything further.

    Values go on the user's clipboard and into a real submission, so a wrong one costs
    far more than a missing one. Confidence is how sure you are that the facts support
    this exact answer: below 0.6 for a fact and below 0.75 for a draft means leave it out.
    """

  private static let responseSchema = GeminiRequest.GenerationConfig.ResponseSchema(
    type: "object",
    properties: [
      "fills": .init(
        type: "array",
        description: "One entry per field you can answer from the stored facts. May be empty.",
        items: .init(
          type: "object",
          properties: [
            "label": .init(
              type: "string", description: "The field label, copied exactly as given."),
            "value": .init(type: "string", description: "The value to paste."),
            "confidence": .init(type: "number", description: "0.0-1.0 confidence in this value."),
            "kind": .init(
              type: "string",
              enum: ["fact", "draft"],
              description:
                "fact = the user's own detail, taken from a stored fact. draft = an answer written for them from several facts, for a question asked in prose."
            ),
          ],
          required: ["label", "value", "confidence", "kind"]
        )
      )
    ],
    required: ["fills"]
  )

  // MARK: - Delivery

  func handleResult(_ result: AssistantResult, sendEvent: @escaping @Sendable (String, [String: Any]) -> Void) async {
    guard let result = result as? FormAssistResult else { return }
    await deliver(result, fingerprint: result.appName)
  }

  private func deliver(
    _ result: FormAssistResult,
    fingerprint: String,
    windowKey: FormWindowKey? = nil
  ) async {
    guard !result.fills.isEmpty else { return }
    // An account switch between the model call and the card must not put one user's
    // details on another user's screen.
    guard RuntimeOwnerIdentity.currentOwnerId() != nil else {
      log("FormAssist: no signed-in owner, card withheld")
      return
    }

    let fields = result.fills.map {
      CloudConnectorCopyField(
        id: $0.label,
        label: $0.kind == .draft ? "\($0.label) (draft)" : $0.label,
        value: $0.value,
        masksValue: false
      )
    }
    log("FormAssist: offering \(fields.count) values in \(result.appName)")
    cardWindowKey = windowKey

    await MainActor.run {
      FormAssistCard.present(
        fingerprint: fingerprint,
        title: "Omi can fill this",
        subtitle: "From your memories. Copy each value into \(result.appName).",
        fields: fields,
        near: result.windowFrame
      )
    }
  }

  func clearPendingWork() async {
    barrenScans = 0
  }

  func stop() async {
    cardWindowKey = nil
    await MainActor.run {
      FormWatcher.shared.stop()
      FormAssistCard.dismissIfMine()
    }
  }
}

/// Turns field labels into memory search terms, and decides how much of the user's
/// memory the model gets to see.
enum FormAssistRecall {
  private static let stopWords: Set<String> = [
    "your", "name", "please", "enter", "field", "optional", "required", "address",
  ]

  /// How far back recency reaches. Far more than most people have; the character budget
  /// below is what actually bounds the prompt.
  static let recencyFetchLimit = 400

  /// Roughly 10k tokens of memory. Generous on purpose — a fact that never reaches the
  /// model is a field the user has to fill in themselves — while still leaving the call
  /// small enough to answer in a second.
  static let characterBudget = 40_000

  static func searchTerms(for labels: [String], limit: Int = 8) -> [String] {
    var terms: [String] = []
    var seen = Set<String>()
    for label in labels {
      let words = label.lowercased().split(whereSeparator: { !$0.isLetter })
      for word in words where word.count >= 4 {
        let term = String(word)
        guard !stopWords.contains(term), !seen.contains(term) else { continue }
        seen.insert(term)
        terms.append(term)
        if terms.count == limit { return terms }
      }
    }
    return terms
  }

  /// Keyword hits first — they are the ones a field label already pointed at — then
  /// recency, until the budget is spent. Order matters beyond truncation: a model reads
  /// what is at the top of a long list more reliably than what is buried in it.
  static func selected(
    matched: [String],
    recent: [String],
    budget: Int = characterBudget
  ) -> [String] {
    var output: [String] = []
    var seen = Set<String>()
    var used = 0
    for memory in matched + recent {
      let trimmed = memory.trimmingCharacters(in: .whitespacesAndNewlines)
      guard !trimmed.isEmpty, !seen.contains(trimmed) else { continue }
      guard used + trimmed.count <= budget else { continue }
      seen.insert(trimmed)
      output.append(trimmed)
      used += trimmed.count
    }
    return output
  }
}

/// Fields nothing in a memory should ever answer, whatever the memories happen to say.
///
/// These are the questions where a guess is not merely wrong but harmful: protected
/// characteristics an employer asks separately and voluntarily, and terms the user
/// negotiates rather than recalls. They are filtered before the model sees them, so a
/// wrong answer here is not something a prompt has to be trusted to avoid.
enum FormAssistSensitiveFields {
  private static let terms = [
    "gender", "sex", "race", "ethnic", "hispanic", "latino", "veteran", "disability",
    "sexual orientation", "pronoun", "date of birth", "birth date", "age",
    "marital", "religion", "salary", "compensation", "desired pay", "ssn",
    "social security", "national id",
  ]

  static func isSensitive(_ label: String) -> Bool {
    let lowered = label.lowercased()
    return terms.contains { lowered.contains($0) }
  }

  static func answerable(_ labels: [String]) -> [String] {
    labels.filter { !isSensitive($0) }
  }
}

/// The bar a model-proposed value has to clear to reach the clipboard.
enum FormAssistFillPolicy {
  /// A drafted paragraph the user has to read before sending. Beyond this it is not a
  /// form answer any more, and the card cannot show enough of it to be reviewed.
  static let maxDraftLength = 1_500

  static func accepted(
    _ fills: [FormAssistFill],
    forLabels labels: [String],
    minConfidence: Double,
    minDraftConfidence: Double = 0.75,
    limit: Int
  ) -> [FormAssistFill] {
    let known = Set(labels.map { $0.lowercased() })
    var seen = Set<String>()
    var output: [FormAssistFill] = []
    for fill in fills {
      let label = fill.label.trimmingCharacters(in: .whitespacesAndNewlines)
      let value = fill.value.trimmingCharacters(in: .whitespacesAndNewlines)
      guard !label.isEmpty, !value.isEmpty else { continue }
      // A label the scan never reported is a field the model invented.
      guard known.contains(label.lowercased()), !seen.contains(label.lowercased()) else { continue }
      guard !FormAssistSensitiveFields.isSensitive(label) else { continue }
      let bar = fill.kind == .draft ? minDraftConfidence : minConfidence
      guard fill.confidence >= bar else { continue }
      guard fill.kind != .draft || value.count <= maxDraftLength else { continue }
      seen.insert(label.lowercased())
      output.append(
        FormAssistFill(label: label, value: value, confidence: fill.confidence, kind: fill.kind))
      if output.count == limit { break }
    }
    return output
  }
}
