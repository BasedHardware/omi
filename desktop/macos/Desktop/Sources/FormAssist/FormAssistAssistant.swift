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

/// One field of the form as the card shows it. Every empty field the user can act on
/// becomes a row, because a field Omi silently dropped is indistinguishable from one it
/// never saw — and the difference is the whole reason the card is worth reading.
struct FormAssistRow: Sendable, Equatable {
  enum Outcome: Sendable, Equatable {
    case filled(FormAssistFill)
    /// Asked, and nothing the user has stored answers it.
    case noMemory
    /// Answered, but not confidently enough to put on the clipboard.
    case notSure
    /// Never asked: a protected characteristic or a term the user negotiates.
    case skipped
  }

  let label: String
  let outcome: Outcome

  var fill: FormAssistFill? {
    guard case .filled(let fill) = outcome else { return nil }
    return fill
  }

  /// What the card says in place of a value. Phrased as what Omi did, not as an error:
  /// "no memory" tells the user what to store next, which "unavailable" does not.
  var hint: String? {
    switch outcome {
    case .filled: return nil
    case .noMemory: return "no memory"
    case .notSure: return "not sure"
    case .skipped: return "skipped"
    }
  }
}

struct FormAssistResult: AssistantResult {
  let rows: [FormAssistRow]
  let appName: String
  let windowFrame: CGRect?

  var fills: [FormAssistFill] { rows.compactMap(\.fill) }

  func toDictionary() -> [String: Any] {
    [
      "app": appName,
      "fieldCount": rows.count,
      "fillCount": fills.count,
      "labels": rows.map(\.label),
    ]
  }
}

private struct FormAssistModelResponse: Decodable {
  let fills: [FormAssistFill]
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
  /// The form whose offer is on screen, so stopping this surface takes its own card away
  /// and nobody else's.
  private var lastOfferedFingerprint: String?
  private var lastWindowKey: FormWindowKey?
  private var barrenScans = 0
  private static let barrenScanLimit = 2

  /// Forms the user said no to. An offer declined and then re-offered on the next scan is
  /// the spam the ✓ exists to prevent, so no is remembered for as long as the app runs.
  private var declined: Set<String> = []

  /// When each form's offer ran out with neither the ✓ nor the ✗, and how long that
  /// keeps it quiet.
  ///
  /// Not a decline. The ✗ is the user saying no and is remembered for the whole run; a
  /// countdown running out is the much weaker claim that they did not act on a card for
  /// four minutes, which is equally what stepping away looks like. Long enough that
  /// ignoring it once is not answered with another card; short enough that coming back
  /// to the form an hour later still gets help.
  private var expiredOffers: [String: Date] = [:]
  static let expiredOfferBackoff: TimeInterval = 30 * 60

  /// Whether a form whose offer ran out may be offered again yet.
  nonisolated static func offerIsQuiet(expiredAt: Date?, now: Date) -> Bool {
    guard let expiredAt else { return false }
    return now.timeIntervalSince(expiredAt) < expiredOfferBackoff
  }

  /// A page load fires several triggers at once, and the model call outlives all of
  /// them. Without this the same form is answered two or three times in parallel.
  private var isEvaluating = false

  private var lastOfferAt: Date?
  private var evaluationsToday: [Date] = []

  /// The cooldown bounds how often an offer may appear; the daily budget bounds the model
  /// calls behind the ✓. Someone applying to ten jobs in an hour is the case this exists
  /// for, so both are loose enough not to be in their way, and the per-form cache is what
  /// actually keeps the call count near one per form.
  private let cooldown: TimeInterval = 15
  private let dailyEvaluationBudget = 50
  /// A drafted answer is held to a higher bar than a copied fact: the user can eyeball
  /// "Datasaur" in a heartbeat, and cannot eyeball a paragraph as fast.
  private let minConfidence = 0.6
  private let minDraftConfidence = 0.75

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
      FormWatcher.shared.subscribe(identifier) { reason in
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

    // Messaging windows belong to message-draft assist. A Mail compose window is To,
    // Cc and Subject — exactly form-shaped — and two cards racing for the same window
    // would each be right by their own gate.
    guard MessageComposeGate.surface(appName: key.appName, windowTitle: key.windowTitle) == nil
    else {
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
    guard await MainActor.run(body: { !PanelSession.isShowingForm(snapshot.fingerprint) }) else {
      return
    }
    guard !declined.contains(snapshot.fingerprint) else { return }
    guard !Self.offerIsQuiet(expiredAt: expiredOffers[snapshot.fingerprint], now: Date())
    else { return }
    expiredOffers[snapshot.fingerprint] = nil

    if let previous = offers.last(where: { $0.fingerprint == snapshot.fingerprint }) {
      // Already answered. Re-show what it produced, or stay quiet if it produced nothing
      // — either way this form costs no more model calls and no more log noise.
      guard !previous.result.fills.isEmpty else { return }
      guard await MainActor.run(body: { PanelSession.canPresentAmbient }) else { return }
      await deliver(previous.result, fingerprint: snapshot.fingerprint)
      return
    }

    log(
      "FormAssist: gate=eligible app=\(snapshot.appName) fields=\(snapshot.fields.count) "
        + "fillable=\(snapshot.emptyFields.count) submit=\(snapshot.hasSubmitButton) "
        + "reason=\(reason.rawValue)")

    guard await MainActor.run(body: { PanelSession.canPresentAmbient }) else {
      log("FormAssist: another card is on screen")
      return
    }

    let now = Date()
    if let lastOfferAt, now.timeIntervalSince(lastOfferAt) < cooldown { return }
    lastOfferAt = now
    await offer(snapshot: snapshot)
  }

  // MARK: - The offer

  /// Ask before spending anything.
  ///
  /// Reading the form was free — an accessibility walk on the user's own machine.
  /// Answering it is not: it sends their memories and a picture of their screen off the
  /// machine for a form they may only have scrolled past. The ✓ is what buys that, so
  /// nothing above this line happens until the user gives it, and a ✗ means this form is
  /// never offered again.
  private func offer(snapshot: FormSnapshot) async {
    guard RuntimeOwnerIdentity.currentOwnerId() != nil else {
      log("FormAssist: no signed-in owner, offer withheld")
      return
    }
    let answerable = snapshot.emptyFields.filter { !FormAssistSensitiveFields.isSensitive($0.label) }
    guard !answerable.isEmpty else { return }

    let fingerprint = snapshot.fingerprint
    lastOfferedFingerprint = fingerprint
    log(
      "FormAssist: offering to fill \(answerable.count) of \(snapshot.emptyFields.count) fields "
        + "in \(snapshot.appName)")

    // Created here rather than on the ✓ so the panel owns one cancel token for its whole
    // life: closing the card mid-answer has to reach work that started after the tick.
    let work = CancellableWork()
    _ = await MainActor.run {
      PanelSession.present(
        title: "Fill this form?",
        subtitle: Self.offerSubtitle(answerable: answerable),
        fields: [],
        grain: .context,
        origin: .ambient,
        formFingerprint: fingerprint,
        // An offer nobody answers should not sit there all day. Accepting it clears the
        // countdown, because waiting for an answer is not the same as ignoring one.
        autoDismissAfter: CloudConnectorGuidanceOverlay.fieldCopyCardLifetime,
        ask: CopyCardAsk(
          placeholder: "Add context\u{2026}",
          confirmLabel: "Fill it",
          onConfirm: { context in
            Task { await self.fillOffer(snapshot: snapshot, context: context, work: work) }
          }),
        onCancel: { work.cancel() },
        onUserDismiss: { Task { await self.declineOffer(fingerprint) } },
        // Four minutes with neither the ✓ nor the ✗ is an answer too. Without this the
        // next scan offers the same form again, and again, so ignoring it teaches Omi
        // nothing — the user can still ask for it out loud, which skips every gate.
        onExpire: { Task { await self.retireOffer(fingerprint) } }
      )
    }
  }

  /// What the offer says it read. The counts come from the accessibility scan that is
  /// already done and free, and naming them is what separates a proposal from a nag: the
  /// user can tell at a glance whether Omi is looking at the form they think it is.
  static func offerSubtitle(answerable: [FormField]) -> String {
    let prose = answerable.filter(\.wantsProse).count
    let fields = "\(answerable.count) field\(answerable.count == 1 ? "" : "s")"
    guard prose > 0 else { return "\(fields) Omi can try from your memories." }
    return "\(fields) Omi can try, including \(prose) to write."
  }

  private func declineOffer(_ fingerprint: String) {
    declined.insert(fingerprint)
    log("FormAssist: offer declined, this form will not be offered again")
  }

  private func retireOffer(_ fingerprint: String) {
    expiredOffers[fingerprint] = Date()
    log(
      "FormAssist: offer expired unanswered, this form is quiet for "
        + "\(Int(Self.expiredOfferBackoff / 60))m")
  }

  /// The user said yes. From here it is the same work the asked-for path does, and the
  /// panel it fills is the one the offer was already showing in.
  private func fillOffer(snapshot: FormSnapshot, context: String, work: CancellableWork) async {
    let now = Date()
    evaluationsToday = evaluationsToday.filter { Calendar.current.isDate($0, inSameDayAs: now) }
    guard evaluationsToday.count < dailyEvaluationBudget else {
      log("FormAssist: daily evaluation budget spent")
      await MainActor.run {
        PanelSession.update(
          subtitle: "Form assist has spent its budget for today.", forForm: snapshot.fingerprint)
      }
      return
    }
    evaluationsToday.append(now)

    let roster = snapshot.emptyFields
    await MainActor.run {
      PanelSession.update(
        subtitle: "Reading your memories\u{2026}",
        fields: Self.panelFields(roster: roster, fills: [:], answered: []),
        forForm: snapshot.fingerprint)
    }

    do {
      switch try await fill(snapshot: snapshot, roster: roster, context: context, work: work) {
      case .cancelled:
        refundEvaluation()
      case .noEvidence:
        refundEvaluation()
        await MainActor.run {
          PanelSession.update(
            subtitle: "Nothing Omi has stored could answer this form.", fields: [],
            forForm: snapshot.fingerprint)
        }
      case .rows(let rows):
        let result = FormAssistResult(
          rows: rows, appName: snapshot.appName, windowFrame: snapshot.windowFrame)
        remember(result, for: snapshot.fingerprint)
        let filled = result.fills.count
        log("FormAssist: filled \(filled) of \(rows.count) fields in \(snapshot.appName)")
        await MainActor.run {
          PanelSession.update(
            title: filled > 0 ? "Omi can fill this" : "Fill this form?",
            subtitle: filled > 0
              ? "\(filled) of \(rows.count) fields from your memories. "
                + "Copy each into \(snapshot.appName)."
              : "Nothing Omi has stored answers these \(rows.count) fields.",
            fields: Self.finalFields(rows: rows),
            forForm: snapshot.fingerprint)
        }
      }
    } catch is CancellationError {
      refundEvaluation()
    } catch {
      refundEvaluation()
      logError("FormAssist: fill resolution failed", error: error)
      await MainActor.run {
        PanelSession.update(subtitle: "Could not read the form.", forForm: snapshot.fingerprint)
      }
    }
  }

  /// Hand the budget back when the answer never arrived. The budget bounds work that was
  /// actually done; a cancelled or failed call is not work the user got anything from.
  private func refundEvaluation() {
    if !evaluationsToday.isEmpty { evaluationsToday.removeLast() }
  }

  // MARK: - On demand

  /// Answer the form on screen because the user asked out loud, and fill the panel in as
  /// the answers arrive.
  ///
  /// The gate, the cooldown, the barren-scan memory and the already-offered cache are all
  /// there to decide whether to *interrupt* someone. None of them applies once the user
  /// has asked: a form that failed the eligibility bar is still the form they mean. The
  /// daily budget stays, because it exists to bound a stuck retry loop, not the user —
  /// and it is handed back if they close the card before the answers land.
  ///
  /// The panel goes up before the model call, not after it. Answering a form takes
  /// several seconds; without the pending rows on screen that is several seconds of
  /// nothing happening, which reads as broken rather than busy.
  func assistOnDemand(context: String) async -> OnDemandOutcome {
    guard RuntimeOwnerIdentity.currentOwnerId() != nil else {
      return .handled("No signed-in Omi account.")
    }
    guard await MainActor.run(body: { AXIsProcessTrusted() }) else {
      return .handled("Omi needs Accessibility permission to read the form.")
    }
    guard let snapshot = await MainActor.run(body: { FormFieldScanner.scanFrontmostWindow() }),
      !snapshot.emptyFields.isEmpty
    else { return .noForm }

    let now = Date()
    evaluationsToday = evaluationsToday.filter { Calendar.current.isDate($0, inSameDayAs: now) }
    guard evaluationsToday.count < dailyEvaluationBudget else {
      return .handled("Form assist has spent its budget for today.")
    }
    evaluationsToday.append(now)

    let roster = snapshot.emptyFields
    let work = CancellableWork()
    let panel = await MainActor.run {
      PanelSession.present(
        title: "\(snapshot.appName) form",
        subtitle: "Reading your memories\u{2026}",
        fields: Self.panelFields(roster: roster, fills: [:], answered: []),
        grain: .context,
        origin: .requested,
        formFingerprint: snapshot.fingerprint,
        onCancel: { work.cancel() }
      )
    }

    func abandon(_ message: String) -> OnDemandOutcome {
      refundEvaluation()
      return .handled(message)
    }

    log(
      "FormAssist: on-demand panel pending with \(roster.count) fields in \(snapshot.appName)"
        + (context.isEmpty ? "" : " context=\(context.count) chars"))

    do {
      switch try await fill(snapshot: snapshot, roster: roster, context: context, work: work) {
      case .cancelled:
        return abandon("Cancelled.")
      case .noEvidence:
        DesktopDiagnosticsManager.shared.recordFallback(
          area: "panel_lookup", from: "form_assist", to: "none",
          reason: "no_evidence", outcome: .exhausted)
        _ = await MainActor.run { PanelSession.dismiss(token: panel) }
        return abandon("Omi has nothing stored that could answer this form.")
      case .rows(let rows):
        guard rows.contains(where: { $0.fill != nil }) else {
          _ = await MainActor.run { PanelSession.dismiss(token: panel) }
          return .handled("Nothing Omi knows answers the \(roster.count) fields on this form.")
        }
        let filled = rows.filter { $0.fill != nil }.count
        await MainActor.run {
          PanelSession.update(
            subtitle: "\(filled) of \(rows.count) fields from your memories. "
              + "Copy each into \(snapshot.appName).",
            fields: Self.finalFields(rows: rows),
            forForm: snapshot.fingerprint)
        }
        log(
          "FormAssist: on-demand panel with \(filled) of \(rows.count) fields in "
            + "\(snapshot.appName)")
        return .handled("Put \(filled) field\(filled == 1 ? "" : "s") on screen to copy.")
      }
    } catch is CancellationError {
      return abandon("Cancelled.")
    } catch {
      logError("FormAssist: on-demand fill resolution failed", error: error)
      _ = await MainActor.run { PanelSession.dismiss(token: panel) }
      return .handled("Could not read the form.")
    }
  }

  /// How far a fill got. The caller owns the panel, so it also owns what an empty answer
  /// looks like: spoken back on the asked-for path, written into the card on the offered
  /// one, where there is nobody listening.
  private enum FillOutcome {
    case rows([FormAssistRow])
    case noEvidence
    case cancelled
  }

  /// Everything that happens once the panel is already on screen: read what Omi knows,
  /// answer the form, and fill the rows in as the answers land.
  ///
  /// Both paths run this. The offer and the spoken request differ in what buys the model
  /// call, not in the work it does.
  private func fill(
    snapshot: FormSnapshot, roster: [FormField], context: String, work: CancellableWork
  ) async throws -> FillOutcome {
    let fingerprint = snapshot.fingerprint
    // Memories are one source, not the only one: recent work is where the links and
    // documents a form asks about actually live, and the sweep reaches the four stores
    // neither of those touches. Same seam the spoken lookup uses, so a question answers
    // the same way whether or not a form happens to be focused.
    var collected = await recallMemories(for: snapshot)
    if let recent = await recentWorkEvidence() { collected.append(recent) }
    let sweep = await OmiSweep.run(query: Self.sweepQuery(roster: roster, context: context))
    if !sweep.hits.isEmpty { collected.append(OmiSweep.promptSection(sweep)) }
    let evidence = collected
    guard await !work.isCancelled else { return .cancelled }
    guard !evidence.isEmpty else { return .noEvidence }
    await MainActor.run {
      PanelSession.update(subtitle: "Writing your answers\u{2026}", forForm: snapshot.fingerprint)
    }

    let image = await windowImage(windowID: snapshot.windowID)
    guard await !work.isCancelled else { return .cancelled }
    let rows = try await work.run {
      try await self.resolveRows(
        snapshot: snapshot, memories: evidence, image: image, userContext: context,
        onFacts: { facts in
          let byLabel = Dictionary(
            facts.map { ($0.label, $0) }, uniquingKeysWith: { first, _ in first })
          await MainActor.run {
            PanelSession.update(
              fields: Self.panelFields(roster: roster, fills: byLabel, answered: Set(byLabel.keys)),
              forForm: fingerprint)
          }
        })
    }
    guard await !work.isCancelled else { return .cancelled }
    return .rows(rows)
  }

  /// How the asked-for path ended. `.noForm` belongs to the caller, who still owes the
  /// user an answer from their data.
  enum OnDemandOutcome: Sendable {
    case handled(String)
    case noForm
  }

  /// What to sweep the user's stores for: the field labels are the question the form is
  /// asking, and anything the user said when they asked narrows it.
  nonisolated static func sweepQuery(roster: [FormField], context: String) -> String {
    (roster.map(\.label) + [context]).joined(separator: " ")
  }

  /// The user's recent work as one evidence line for the model call. Local and fast;
  /// best effort, because a form is still answerable from memories alone.
  private func recentWorkEvidence() async -> String? {
    let result = await ChatToolExecutor.execute(
      ToolCall(name: "get_work_context", arguments: [:], thoughtSignature: nil))
    let trimmed = result.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty, !trimmed.contains("\"ok\":false") else { return nil }
    return "Recent work context (JSON): \(String(trimmed.prefix(4_000)))"
  }

  /// Every field the user can act on, in tab order: answered ones show their value,
  /// unanswered ones show a spinner, and the ones Omi will not touch say so straight
  /// away rather than pretending to work on them.
  private static func panelFields(
    roster: [FormField],
    fills: [String: FormAssistFill],
    answered: Set<String>
  ) -> [CloudConnectorCopyField] {
    roster.enumerated().map { index, field in
      let sensitive = FormAssistSensitiveFields.isSensitive(field.label)
      let fill = fills[field.label]
      return CloudConnectorCopyField(
        id: "form-\(index)",
        label: fill?.kind == .draft ? "\(field.label) (draft)" : field.label,
        value: fill?.value ?? "",
        hint: sensitive ? "skipped" : nil,
        masksValue: false,
        wraps: fill?.kind == .draft,
        isPending: !sensitive && fill == nil && !answered.contains(field.label)
      )
    }
  }

  private static func finalFields(rows: [FormAssistRow]) -> [CloudConnectorCopyField] {
    rows.enumerated().map { index, row in
      CloudConnectorCopyField(
        id: "form-\(index)",
        label: row.fill?.kind == .draft ? "\(row.label) (draft)" : row.label,
        value: row.fill?.value ?? "",
        hint: row.hint,
        masksValue: false,
        wraps: row.fill?.kind == .draft
      )
    }
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

  private func resolveRows(
    snapshot: FormSnapshot,
    memories: [String],
    image: Data?,
    userContext: String = "",
    onFacts: (@Sendable ([FormAssistFill]) async -> Void)? = nil
  ) async throws -> [FormAssistRow] {
    // The roster the card shows is every empty field, in the order the user tabs
    // through them. Only the answerable subset is worth a model call.
    let roster = snapshot.emptyFields
    let answerable = roster.filter { !FormAssistSensitiveFields.isSensitive($0.label) }
    guard !answerable.isEmpty else { return [] }

    // Copying a stored detail and composing an answer are opposite jobs, and one call
    // asked to do both across twenty fields does neither well — it returns the two
    // trivial names and abandons the prose. Splitting them gives each call one job and
    // a short list, which is the condition under which drafts actually come back.
    let prose = answerable.filter(\.wantsProse).map(\.label)
    let facts = answerable.filter { !$0.wantsProse }.map(\.label)

    async let factFills = ask(
      .fact, labels: facts, snapshot: snapshot, memories: memories, image: image,
      userContext: userContext)
    async let draftFills = ask(
      .draft, labels: prose, snapshot: snapshot, memories: memories, image: image,
      userContext: userContext)

    // Facts come back first and prose is the slow half. Reporting them as they land is
    // what lets the card fill in row by row instead of sitting blank until both finish.
    let resolvedFacts = try await factFills
    await onFacts?(resolvedFacts)

    return FormAssistFillPolicy.rows(
      resolvedFacts + (try await draftFills),
      forFields: roster.map(\.label),
      minConfidence: minConfidence,
      minDraftConfidence: minDraftConfidence)
  }

  /// One model call, for one kind of answer. The kind is imposed here rather than asked
  /// for: the call already knows which fields it was given, so a mislabelled response
  /// cannot slip a paragraph past the bar a copied fact has to clear.
  private func ask(
    _ kind: FormAssistFill.Kind,
    labels: [String],
    snapshot: FormSnapshot,
    memories: [String],
    image: Data?,
    userContext: String = ""
  ) async throws -> [FormAssistFill] {
    guard !labels.isEmpty else { return [] }
    log(
      "FormAssist: asking for \(labels.count) \(kind.rawValue)s with \(memories.count) memories"
        + " — \(labels.joined(separator: " | "))")

    let prompt = """
      == THE FORM IN FRONT OF THE USER ==
      App: \(snapshot.appName)
      Window: \(snapshot.windowTitle.isEmpty ? "(no title)" : snapshot.windowTitle)
      \(image == nil
        ? "No screenshot available."
        : "The attached screenshot is that window right now. It shows only the part of the page that is scrolled into view; fields listed below may sit far outside it, and that is normal.")

      == FIELDS TO ANSWER, AS THE ACCESSIBILITY TREE NAMES THEM ==
      \(labels.map { "- \($0)" }.joined(separator: "\n"))

      == WHAT OMI KNOWS ABOUT THIS USER ==
      \(memories.map { "- \($0)" }.joined(separator: "\n"))
      \(userContext.isEmpty
        ? ""
        : """

          == WHAT THE USER JUST ASKED FOR ==
          \(userContext)
          This is the user's own instruction about this form, said out loud just now. It
          outranks anything above it, including a value you would otherwise have chosen.
          """)
      """

    let systemPrompt = kind == .draft ? Self.draftPrompt : Self.factPrompt
    let response = try await {
      if let image {
        return try await geminiClient.sendRequest(
          prompt: prompt,
          imageData: image,
          systemPrompt: systemPrompt,
          responseSchema: Self.responseSchema
        )
      }
      return try await geminiClient.sendRequest(
        prompt: prompt,
        systemPrompt: systemPrompt,
        responseSchema: Self.responseSchema
      )
    }()
    guard let data = response.data(using: .utf8) else { return [] }
    let decoded = try JSONDecoder().decode(FormAssistModelResponse.self, from: data)
    // Labels and confidences only — never the values, which are the user's own details
    // and belong on the clipboard rather than in a log.
    log(
      "FormAssist: \(kind.rawValue) call returned "
        + decoded.fills.map { "\($0.label)[\(Int($0.confidence * 100))]" }.joined(separator: ", "))
    return decoded.fills.map {
      FormAssistFill(label: $0.label, value: $0.value, confidence: $0.confidence, kind: kind)
    }
  }

  /// Shared by both calls. Everything here is about what must never reach the
  /// clipboard, and it does not change with the kind of answer being asked for.
  private static let groundRules = """
    NEVER:
    - Invent an employer, a date, a degree, a metric, a tool, or an achievement. If the
      facts do not support the answer, leave the field out. Two right answers beat ten
      where six are guesses.
    - State enthusiasm, availability, salary, notice period, visa status, or a
      willingness to relocate that no fact establishes.
    - Assume anything about the user that the facts do not say — where they are from,
      how old they are, what languages they speak, what they identify as. The facts are
      the only source; nothing about a name or a school implies anything further.

    Values go on the user's clipboard and into a real submission, so a wrong one costs
    far more than a missing one.
    """

  private static let factPrompt = """
    You are given the labels of some fields on a form the user is filling in, and the
    facts Omi has stored about them. For each field the facts can answer, give the value
    to paste.

    These fields ask for something the user simply is or has: a name, a school, an
    employer, a link, a list of skills, a title, a location, a phone number. Take the
    value out of the facts and give it in the form the field wants. Reformatting what is
    there is fine: splitting a full name into first and last, listing languages the
    user's own facts already list, giving a company name without the role around it.

    Answer every field the facts cover. A field whose answer is not in the facts is left
    out — say nothing rather than guess.

    \(groundRules)

    Confidence is how sure you are that the facts support this exact answer. Below 0.6,
    leave the field out.
    """

  private static let draftPrompt = """
    You write the answers to the open questions on a form, using what is already known
    about the user. Every field you are given is a question asked in prose with a box
    big enough to answer it in: why this company, describe your experience with X, what
    are you looking for, tell us about a project, anything else we should know.

    Write the answer the user would write, in their own voice. Match the length the
    question implies — a couple of sentences for a short one, two to five for an open
    one, a line for a question that only wants a yes or no with a reason.

    Draft generously. The card marks these as drafts and the user edits before sending,
    so a strong honest starting point is worth far more to them than a blank box — a
    form where only the name is filled in has barely helped at all. If the facts show
    relevant work, draft the answer. Answering three of four questions and leaving the
    fourth is a good outcome; leaving all four is a failure.

    You have two sources, and both are legitimate:
    - The facts: the user's real projects, employers, technologies, results, studies.
      Every concrete claim in the draft comes from here.
    - The page: the role, the company, and what the job asks for. Connecting the user's
      real experience to what the page asks for is exactly the draft that helps — that
      is not inventing anything about the company, it is reading the page. The
      screenshot may not have scrolled to a given field; answer it from its label
      anyway.

    So "Why <company>?" is answerable whenever the facts show work that genuinely bears
    on the role: say what the user has built and why that leads here. Do not claim to
    have used the company's product, admired it for years, or met anyone there unless a
    fact says so.

    Leave a question out when the facts have nothing to bear on it — a domain the user
    has not worked in, a tool they have not used. Silence is the honest answer to "do
    you have experience selling to engineering teams" when every fact says they build
    the systems instead.

    \(groundRules)

    Confidence is how sure you are that the facts support this answer. Below 0.75, leave
    the question out.
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
    await deliver(result, fingerprint: result.appName)
  }

  private func deliver(_ result: FormAssistResult, fingerprint: String) async {
    guard !result.fills.isEmpty else { return }
    // An account switch between the model call and the card must not put one user's
    // details on another user's screen.
    guard RuntimeOwnerIdentity.currentOwnerId() != nil else {
      log("FormAssist: no signed-in owner, card withheld")
      return
    }
    // The model call outlives the eligibility check that started it, and a panel the
    // user asked for out loud can go up while it runs. Ownership is decided here, at the
    // last moment before the card would replace it.
    guard await MainActor.run(body: { PanelSession.canPresentAmbient }) else {
      log("FormAssist: card withheld, a requested panel is on screen")
      return
    }

    let fields = Self.finalFields(rows: result.rows)
    let filled = result.fills.count
    log("FormAssist: offering \(filled) of \(fields.count) fields in \(result.appName)")
    lastOfferedFingerprint = fingerprint

    _ = await MainActor.run {
      PanelSession.present(
        title: "Omi can fill this",
        subtitle: "\(filled) of \(fields.count) fields from your memories. "
          + "Copy each into \(result.appName).",
        fields: fields,
        grain: .context,
        origin: .ambient,
        formFingerprint: fingerprint,
        // An offer the user never asked for should not sit there all day.
        autoDismissAfter: CloudConnectorGuidanceOverlay.fieldCopyCardLifetime
      )
    }
  }

  func clearPendingWork() async {
    barrenScans = 0
  }

  func stop() async {
    let offered = lastOfferedFingerprint
    lastOfferedFingerprint = nil
    await MainActor.run {
      FormWatcher.shared.unsubscribe(identifier)
      // Only this surface's own offer goes; a panel the user asked for is not ours to
      // close because monitoring stopped.
      if let offered { PanelSession.dismissForm(offered) }
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

  /// Fields that ask the user to agree to something rather than to state something.
  /// No stored fact can consent on their behalf, so these are refused for the same
  /// reason as the terms above — and keeping them out of the prompt matters twice
  /// over: a list padded with questions nothing can answer pulls the whole response
  /// conservative, which is how a real application lost its drafts to boilerplate.
  private static let consentTerms = [
    "arbitration", "agreement to", "terms and conditions", "privacy policy",
    "ai policy", "acknowledge", "i certify", "e-signature", "electronic signature",
  ]

  static func isSensitive(_ label: String) -> Bool {
    let lowered = label.lowercased()
    return (terms + consentTerms).contains { lowered.contains($0) }
  }

  static func answerable(_ labels: [String]) -> [String] {
    labels.filter { !isSensitive($0) }
  }
}

/// The bar a model-proposed value has to clear to reach the clipboard, and the account
/// of every field that did not clear it.
enum FormAssistFillPolicy {
  /// A drafted paragraph the user has to read before sending. Beyond this it is not a
  /// form answer any more, and the card cannot show enough of it to be reviewed.
  static let maxDraftLength = 1_500

  /// One row per field the user still has to fill in, in the order they meet them.
  ///
  /// `fields` is the whole empty-field roster, not the answerable subset: a field
  /// filtered out for being a protected characteristic is still a field the user is
  /// looking at, and saying Omi skipped it is more honest than leaving it off the card
  /// as though it were never there.
  static func rows(
    _ fills: [FormAssistFill],
    forFields fields: [String],
    minConfidence: Double,
    minDraftConfidence: Double = 0.75
  ) -> [FormAssistRow] {
    var proposed: [String: FormAssistFill] = [:]
    for fill in fills {
      let label = fill.label.trimmingCharacters(in: .whitespacesAndNewlines)
      let value = fill.value.trimmingCharacters(in: .whitespacesAndNewlines)
      guard !label.isEmpty, !value.isEmpty else { continue }
      // The model may answer the same field twice; the first answer is the one it
      // committed to, and a second is a reconsideration the user cannot adjudicate.
      guard proposed[label.lowercased()] == nil else { continue }
      proposed[label.lowercased()] = FormAssistFill(
        label: label, value: value, confidence: fill.confidence, kind: fill.kind)
    }

    var seen = Set<String>()
    var output: [FormAssistRow] = []
    for field in fields {
      let label = field.trimmingCharacters(in: .whitespacesAndNewlines)
      // Two fields captioned the same are one row: the answer is keyed by label, so a
      // second row would repeat it — and duplicate ids crash the card's `ForEach`.
      guard !label.isEmpty, seen.insert(label.lowercased()).inserted else { continue }
      output.append(
        FormAssistRow(
          label: label,
          outcome: outcome(
            for: label,
            proposal: proposed[label.lowercased()],
            minConfidence: minConfidence,
            minDraftConfidence: minDraftConfidence)))
    }
    return output
  }

  private static func outcome(
    for label: String,
    proposal: FormAssistFill?,
    minConfidence: Double,
    minDraftConfidence: Double
  ) -> FormAssistRow.Outcome {
    guard !FormAssistSensitiveFields.isSensitive(label) else { return .skipped }
    guard let proposal else { return .noMemory }
    let bar = proposal.kind == .draft ? minDraftConfidence : minConfidence
    guard proposal.confidence >= bar else { return .notSure }
    // A draft past the length the card can show is one the user cannot review here.
    guard proposal.kind != .draft || proposal.value.count <= maxDraftLength else { return .notSure }
    return .filled(proposal)
  }
}
