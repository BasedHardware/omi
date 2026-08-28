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
  let label: String
  let value: String
  let confidence: Double
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
  private static var isMine = false

  static var canPresent: Bool { isMine || !CloudConnectorGuidanceOverlay.shared.isPresenting }

  static func present(title: String, subtitle: String, fields: [CloudConnectorCopyField], near anchor: CGRect?) {
    isMine = true
    CloudConnectorGuidanceOverlay.shared.presentFieldCopyCard(
      title: title, subtitle: subtitle, fields: fields, near: anchor)
  }

  static func dismissIfMine() {
    guard isMine else { return }
    isMine = false
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

  private var settleTask: Task<Void, Never>?
  private var lastEvaluationAt: Date?
  private var evaluationsToday: [Date] = []

  /// Long enough for the page to finish rendering its fields, short enough that the card
  /// is there before the user has typed the first answer themselves.
  private let settleInterval: Duration = .seconds(3)
  private let cooldown: TimeInterval = 45
  private let dailyEvaluationBudget = 20
  private let minConfidence = 0.6
  private let maxRows = 8

  init() throws {
    geminiClient = try GeminiClient(
      model: ModelQoS.Gemini.proactive,
      fallbackModel: ModelQoS.Gemini.lightweight,
      workload: .extraction
    )
  }

  // MARK: - Trigger

  /// Deliberately not driven by captured frames. A form on a static page produces exactly
  /// one distributed frame — at the instant of the switch, before the page has settled —
  /// and none after, so a frame-driven dwell never fires on the very screens this exists
  /// for. The accessibility tree is readable at any moment, so the settle is just a timer.
  func onContextSwitch(departingFrame: CapturedFrame?, newApp: String, newWindowTitle: String?) async {
    settleTask?.cancel()
    // The card described a form the user has just left.
    await MainActor.run { FormAssistCard.dismissIfMine() }

    settleTask = Task { [weak self, settleInterval] in
      try? await Task.sleep(for: settleInterval)
      guard !Task.isCancelled else { return }
      await self?.evaluate(appName: newApp)
    }
  }

  func shouldAnalyze(frameNumber: Int, timeSinceLastAnalysis: TimeInterval) -> Bool { false }

  func analyze(frame: CapturedFrame) async -> AssistantResult? { nil }

  private func evaluate(appName: String) async {
    guard await isEnabled else { return }

    let now = Date()
    if let lastEvaluationAt, now.timeIntervalSince(lastEvaluationAt) < cooldown { return }
    evaluationsToday = evaluationsToday.filter { Calendar.current.isDate($0, inSameDayAs: now) }
    guard evaluationsToday.count < dailyEvaluationBudget else { return }

    let excluded = await MainActor.run {
      // Deliberately the same exclusion list the user already curated for live
      // suggestions: "do not watch me in this app" is one preference, not two.
      SuggestionAssistantSettings.shared.isAppExcluded(appName)
    }
    guard !excluded else {
      log("FormAssist: skipped (app excluded) app=\(appName)")
      return
    }

    guard let snapshot = await MainActor.run(body: { FormFieldScanner.scanFrontmostWindow() }) else {
      log("FormAssist: no readable window (accessibility trusted=\(await MainActor.run { AXIsProcessTrusted() }))")
      return
    }

    let decision = FormAssistGate.decide(
      fields: snapshot.fields, hasSubmitButton: snapshot.hasSubmitButton)
    log(
      "FormAssist: gate=\(decision.rawValue) app=\(snapshot.appName) "
        + "fields=\(snapshot.fields.count) empty=\(snapshot.emptyFields.count) "
        + "submit=\(snapshot.hasSubmitButton)")
    guard decision == .eligible else { return }

    guard await MainActor.run(body: { FormAssistCard.canPresent }) else { return }

    if let previous = offers.last(where: { $0.fingerprint == snapshot.fingerprint }) {
      log("FormAssist: re-showing \(previous.result.fills.count) values for a form already seen")
      await deliver(previous.result)
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
      let fills = try await resolveFills(snapshot: snapshot, memories: memories)
      let result = FormAssistResult(
        fills: fills, appName: snapshot.appName, windowFrame: snapshot.windowFrame)
      remember(result, for: snapshot.fingerprint)
      guard !fills.isEmpty else {
        log("FormAssist: nothing to offer for \(snapshot.emptyFields.count) fields in \(snapshot.appName)")
        return
      }
      await deliver(result)
    } catch {
      logError("FormAssist: fill resolution failed", error: error)
    }
  }

  private func remember(_ result: FormAssistResult, for fingerprint: String) {
    offers.append((fingerprint, result))
    if offers.count > maxRememberedForms {
      offers.removeFirst(offers.count - maxRememberedForms)
    }
  }

  // MARK: - Recall

  /// What Omi knows that could plausibly answer these fields: the user's most recent
  /// memories (where profile facts live) plus a targeted search per field label.
  private func recallMemories(for snapshot: FormSnapshot) async -> [String] {
    var contents: [String] = []
    var seen = Set<String>()

    func absorb(_ memories: [ServerMemory]) {
      for memory in memories where !seen.contains(memory.content) {
        seen.insert(memory.content)
        contents.append(memory.content)
      }
    }

    do {
      absorb(try await MemoryStorage.shared.searchLocalMemories(query: "", limit: 40))
      for term in FormAssistRecall.searchTerms(for: snapshot.emptyFields.map(\.label)) {
        absorb(try await MemoryStorage.shared.searchLocalMemories(query: term, limit: 5))
      }
    } catch {
      logError("FormAssist: memory recall unavailable", error: error)
    }
    return Array(contents.prefix(80))
  }

  // MARK: - Judgment

  private func resolveFills(snapshot: FormSnapshot, memories: [String]) async throws -> [FormAssistFill] {
    let labels = snapshot.emptyFields.map(\.label)
    let prompt = """
      == THE FORM IN FRONT OF THE USER ==
      App: \(snapshot.appName)
      Window: \(snapshot.windowTitle.isEmpty ? "(no title)" : snapshot.windowTitle)

      == EMPTY FIELDS ==
      \(labels.map { "- \($0)" }.joined(separator: "\n"))

      == WHAT OMI KNOWS ABOUT THIS USER ==
      \(memories.map { "- \($0)" }.joined(separator: "\n"))
      """

    let response = try await geminiClient.sendRequest(
      prompt: prompt,
      systemPrompt: Self.systemPrompt,
      responseSchema: Self.responseSchema
    )
    guard let data = response.data(using: .utf8) else { return [] }
    let decoded = try JSONDecoder().decode(FormAssistModelResponse.self, from: data)
    return FormAssistFillPolicy.accepted(
      decoded.fills, forLabels: labels, minConfidence: minConfidence, limit: maxRows)
  }

  private static let systemPrompt = """
    You help a user fill in a form using only what is already known about them.

    You are given the labels of the empty fields on screen and a list of facts Omi has
    stored about this user. For each field, answer it ONLY if one of those facts answers
    it directly. Copy the value out of the fact; never infer, complete, format, or invent
    one. No placeholders, no examples, no "N/A".

    If nothing in the list answers a field, leave that field out entirely. Returning two
    correct values is a good answer; returning eight where six are guesses is a bad one.

    Values go straight onto the user's clipboard and into a real submission, so a wrong
    value costs far more than a missing one. Set confidence below 0.6 whenever you are
    working from something adjacent rather than the fact itself.
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
            "value": .init(type: "string", description: "The value to paste, taken from a stored fact."),
            "confidence": .init(type: "number", description: "0.0-1.0 confidence in this value."),
          ],
          required: ["label", "value", "confidence"]
        )
      )
    ],
    required: ["fills"]
  )

  // MARK: - Delivery

  func handleResult(_ result: AssistantResult, sendEvent: @escaping @Sendable (String, [String: Any]) -> Void) async {
    guard let result = result as? FormAssistResult else { return }
    await deliver(result)
  }

  private func deliver(_ result: FormAssistResult) async {
    guard !result.fills.isEmpty else { return }
    // An account switch between the model call and the card must not put one user's
    // details on another user's screen.
    guard RuntimeOwnerIdentity.currentOwnerId() != nil else { return }

    let fields = result.fills.map {
      CloudConnectorCopyField(id: $0.label, label: $0.label, value: $0.value, masksValue: false)
    }
    log("FormAssist: offering \(fields.count) values in \(result.appName)")

    await MainActor.run {
      FormAssistCard.present(
        title: "Omi can fill this",
        subtitle: "From your memories. Copy each value into \(result.appName).",
        fields: fields,
        near: result.windowFrame
      )
    }
  }

  func clearPendingWork() async {
    settleTask?.cancel()
  }

  func stop() async {
    settleTask?.cancel()
    await MainActor.run { FormAssistCard.dismissIfMine() }
  }
}

/// Turns field labels into memory search terms.
enum FormAssistRecall {
  private static let stopWords: Set<String> = [
    "your", "name", "please", "enter", "field", "optional", "required", "address",
  ]

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
}

/// The bar a model-proposed value has to clear to reach the clipboard.
enum FormAssistFillPolicy {
  static func accepted(
    _ fills: [FormAssistFill],
    forLabels labels: [String],
    minConfidence: Double,
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
      guard fill.confidence >= minConfidence else { continue }
      seen.insert(label.lowercased())
      output.append(FormAssistFill(label: label, value: value, confidence: fill.confidence))
      if output.count == limit { break }
    }
    return output
  }
}
