import Foundation
import VoiceTurnDomain

enum RealtimePublicWebSearchScope: String {
  case narrowCurrent = "narrow_current"
  case historicalResearch = "historical_research"

  init(toolValue: Any?) {
    self = (toolValue as? String).flatMap(Self.init(rawValue:)) ?? .narrowCurrent
  }
}

struct RealtimePublicWebEvidenceReceipt: Equatable {
  let turnID: VoiceTurnID
  let evidence: String

  func evidence(for expectedTurnID: VoiceTurnID) -> String? {
    turnID == expectedTurnID ? evidence : nil
  }
}

// MARK: - Realtime Hub tool surface
//
// Both realtime providers receive the same generated capability declarations.
// Tool calls are untrusted proposals: the kernel owns routing, authorization,
// execution profile, and durable run identity before Swift executes anything.

enum RealtimeHubTools {
  /// Only what the user actually configured. There is deliberately no fallback to
  /// `Locale.preferredLanguages`: the macOS UI language is a claim about the
  /// interface, not about the person, and the line built from this asserts the user
  /// speaks ONLY these languages and that anything else "was misheard". Pinning an
  /// unconfigured bilingual user to their menu-bar language told the model to
  /// reinterpret their real speech as a mishearing. The Windows port already omits
  /// the line for an unconfigured user; this brings macOS to parity.
  static func resolvedVoiceLanguages(explicit codes: [String]) -> [String] {
    let source = codes
    var seen = Set<String>()
    var resolved: [String] = []
    for code in source {
      let base = AssistantSettings.baseLanguageCode(code)
      guard !base.isEmpty, !seen.contains(base) else { continue }
      seen.insert(base)
      resolved.append(base)
    }
    return resolved
  }

  /// One line telling the model which languages the user actually speaks, so a short or
  /// ambiguous utterance is never interpreted (or transcribed, where the provider allows
  /// it) as some third language. Empty when the user has configured no voice languages —
  /// a user who has claimed nothing must not have a claim made for them.
  private static func userLanguagesLine(_ codes: [String]) -> String {
    let resolved = resolvedVoiceLanguages(explicit: codes)
    guard !resolved.isEmpty else { return "" }
    let names = resolved.map { code in
      Locale(identifier: "en").localizedString(forLanguageCode: code) ?? code
    }
    let primary = names[0]
    let list = names.joined(separator: ", ")
    return
      "The user speaks ONLY these languages: \(list) (primary: \(primary)). Their speech "
      + "is always in one of them — if an utterance seems to be in any other language, it "
      + "was misheard; interpret it as \(primary). "
  }

  /// The onboarding demo note while the three-doors step is active, else nil (logged once per session build).
  @MainActor static func activeOnboardingDemoContext() -> String? {
    guard let note = ThreeDoorsDemoPage.activeModelNote, !note.isEmpty else { return nil }
    log("RealtimeHub: onboarding demo note included in voice instructions (\(note.count) chars)")
    return note
  }

  /// Only a Gemini session receives the PTT-down frame as in-turn video. Telling every session
  /// that "every turn arrives with an image of the user's screen" made a provider that never
  /// receives one answer current-screen questions from memory instead of calling the screenshot
  /// tool, so the claim is stated only where it is true.
  static func screenRule(turnFrameAttached: Bool) -> String {
    let opening =
      turnFrameAttached
      ? """
      every turn arrives with an image of the user's screen captured the instant \
      they pressed the key. That image IS the current screen. Answer anything that could refer \
      to it — "this", "that", "here", "it", "the page", "the answer", "the riddle", "the error", \
      "what am I looking at" — directly from that image, before reaching for any other tool or \
      for memory of earlier turns. Images from earlier turns are stale: the screen changes \
      between turns, so never answer a current-screen question from an older image or an \
      earlier answer. Call the screenshot tool only when no image arrived with this turn or \
      the user says the screen changed since they pressed the key. When in doubt, look at \
      this turn's image.
      """
      : """
      no image of the user's screen arrives with a turn on this session. Anything that could \
      refer to the screen — "this", "that", "here", "it", "the page", "the answer", "the \
      riddle", "the error", "what am I looking at" — needs the screenshot tool first. Never \
      answer a current-screen question from memory of an earlier turn or an earlier answer.
      """
    return """
      Screen rule: \(opening) When the screenshot tool succeeds for a current-screen question, the \
      attached image and, when present, its locally captured foreground-application context are \
      the only current visual source of truth. The foreground-application context is trustworthy \
      only for identifying the app active at capture time; it never replaces visual reasoning. \
      Disregard conflicting kernel context, OCR, work summaries, and earlier screen descriptions. \
      You MUST then call \
      report_screen_observation with a concise grounding observation. That report is internal \
      verification, not your user-facing reply. Once it succeeds, answer the user's original \
      current-screen question naturally and conversationally from the attached image. Do not let \
      the report replace the answer or fall back to a generic screen description when the user \
      asked a specific question. Omi's own floating bar, chat bubble, or window may also be \
      visible in the image: treat that as assistant chrome, not as the subject of the user's \
      screen question, unless the user specifically asks about Omi. Answer about the user's \
      visible work and intent, not the assistant UI.
      """
  }

  static func systemInstruction(
    kernelContext: String = "",
    kernelSemanticGuidance: String = "",
    userLanguages: [String] = [],
    onboardingDemoContext: String? = nil,
    turnScreenFrameAttached: Bool = false
  ) -> String {
    let canonicalContext = kernelContext.trimmingCharacters(in: .whitespacesAndNewlines)
    let semanticGuidance = kernelSemanticGuidance.trimmingCharacters(in: .whitespacesAndNewlines)
    let demoNote = onboardingDemoContext?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    let demoBlock =
      demoNote.isEmpty ? "" : "\n## Onboarding demo (authoritative for questions about the doors)\n\(demoNote)\n"

    return """
      You are Omi, a fast spoken-voice assistant on the user's Mac. You hear the user's \
      microphone; reply conversationally in one or two sentences by default. \
      \(userLanguagesLine(userLanguages))Reply in the same language the user is speaking.

      \(canonicalContext)
      \(demoBlock)
      \(semanticGuidance)

      \(DesktopCapabilityRegistry.realtimeSelfModelPrompt)

      The generated tool declarations below describe the capabilities available on this \
      surface. A tool call is only a proposal: the kernel makes the authoritative route and \
      permission decision. Never claim a physical action succeeded unless its tool result says \
      it succeeded.

      Using tools: when a request needs a tool, ordinarily give a short spoken heads-up and call the \
      tool in the same turn so the user knows you're on it and that it won't be instant. A heads-up \
      is a status, not a question or confirmation. Speak the result when it returns. Never go \
      silent during a tool call; the user can't see what you're \
      doing, so a quiet gap feels broken. The catch is variety: that heads-up must be SPECIFIC to \
      what they actually asked and DIFFERENT every time. Name the real thing you're fetching — \
      "Pulling up yesterday's activity…", "Scanning your task list…", "Digging through your notes \
      on the launch…", "Checking your memories for that…", "Getting the latest on that, one \
      sec…". The thing to avoid is repetition: do NOT reach for the same generic opener ("let me \
      check", "let me look that up") turn after turn — it's what makes you sound robotic. Keep it \
      to a few words, vary the wording each turn, and don't include any answer or data you don't \
      have yet. For a slower step, it's fine to signal it'll take a moment. NEVER speak an answer — \
      real or guessed — before the tool returns, NEVER skip the \
      tool call, and never read tool JSON or ids aloud. The think_deeper and web_search tool cards \
      are exceptions: call either one silently and immediately because the app speaks an instant \
      acknowledgement after the kernel accepts it. Do not repeat that acknowledgement when its \
      result arrives. record_interject_feedback is also silent and immediate: call it without a \
      spoken heads-up; the app does not play a canned acknowledgement for that tool, unlike \
      think_deeper, so go straight to the user-facing reply. You cannot see the user's data without calling a tool. \
      \(screenRule(turnFrameAttached: turnScreenFrameAttached))

      Keep latency low for simple requests. Never skip a tool call required by its declaration \
      just to answer faster. The user's latest spoken words are always the request; the attached \
      screen is supporting context only. Never replace the spoken request with a different \
      question inferred from the screen. If the user repeats a request, answer that request again \
      and repeat any required tool sequence instead of switching to an unrelated screen detail. \
      Use earlier turns only to resolve a genuine follow-up or reference in the latest request; \
      when the latest request stands alone, do not continue or append an older topic. The language \
      of the latest spoken request controls the response language.
      """
  }

  /// The result is delivered immediately after the live image. Keep the freshness contract in
  /// the tool result as well as the session instruction so a warm session cannot prefer an older
  /// context summary over the pixels it just received.
  static func screenshotToolResult(
    capturedBytes: Int?,
    frontmostApplication: String? = nil,
    captureFailure: RealtimeScreenEvidenceCaptureFailure? = nil
  ) -> String {
    guard capturedBytes != nil else {
      if captureFailure == .screenRecordingNeedsRelaunch {
        return jsonToolResult([
          "ok": false,
          "error": [
            "code": "screen_recording_needs_relaunch",
            "permission": "screen_recording",
            "message":
              "Screen Recording was granted after Omi launched, so this process still cannot see the screen. Tell the user Screen Recording was granted after Omi started and that they should quit Omi and open it again. Then answer what you can without the screen.",
          ],
        ])
      }
      if captureFailure == .screenRecordingPermissionRequired {
        return jsonToolResult([
          "ok": false,
          "error": [
            "code": "permission_required",
            "permission": "screen_recording",
            "next_tool": "request_permission",
            "next_tool_arguments": ["type": "screen_recording"],
            "message":
              "Screen Recording permission is not granted. Tell the user Omi cannot see their current screen yet and ask whether they want to grant access. Call request_permission with type=screen_recording only after they explicitly request or affirm it.",
          ],
        ])
      }
      return jsonToolResult([
        "ok": false,
        "error": ["code": "screen_evidence_unavailable"],
      ])
    }
    var result: [String: Any] = [
      "ok": true,
      "instruction":
        "Use the attached image and any locally captured foreground-application context as the only current visual source. Call report_screen_observation with a concise grounding observation, then answer the user's original request naturally from this evidence.",
    ]
    if let frontmostApplication = frontmostApplication?.trimmingCharacters(in: .whitespacesAndNewlines),
      !frontmostApplication.isEmpty
    {
      // This is sampled with the frozen screenshot and sent only through the matching
      // provider tool result. It is not persisted, logged, or reused as ambient context.
      result["capture_context"] = ["foreground_application": frontmostApplication]
    }
    return jsonToolResult(result)
  }

  static func screenObservationResult(accepted: Bool) -> String {
    jsonToolResult(
      accepted
        ? [
          "ok": true,
          "status": "screen_observation_accepted",
          "instruction":
            "Grounding verified. Now answer the user's original request naturally using the attached image; the observation was not the user-facing answer.",
        ]
        : ["ok": false, "error": ["code": "screen_observation_rejected"]])
  }

  private static func jsonToolResult(_ value: [String: Any]) -> String {
    guard let data = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]),
      let result = String(data: data, encoding: .utf8)
    else { return #"{\"ok\":false,\"error\":{\"code\":\"screen_evidence_encoding_failed\"}}"# }
    return result
  }

  /// OpenAI Realtime GA `session.tools` entries.
  static var openAITools: [[String: Any]] {
    // Standalone callers fail closed. A physical RealtimeHubSession receives
    // the exact Node registry projection at construction time.
    openAITools(availableDirectedProviders: [])
  }

  static func openAITools(availableDirectedProviders: [String]) -> [[String: Any]] {
    let providerProperty: [String: Any]? =
      availableDirectedProviders.isEmpty
      ? nil
      : [
        "type": "string",
        "enum": availableDirectedProviders,
        "description":
          "Optional local provider override only when the current user explicitly names it; omit for a regular Omi agent.",
      ]
    return GeneratedRealtimeTools.baseOpenAITools(providerProperty: providerProperty)
  }

  /// Gemini Live `setup.tools[0].functionDeclarations` entries (same surface). Derived once
  /// from `openAITools`.
  static var geminiFunctionDeclarations: [[String: Any]] {
    geminiFunctionDeclarations(availableDirectedProviders: [])
  }

  static func geminiFunctionDeclarations(availableDirectedProviders: [String]) -> [[String: Any]] {
    openAITools(availableDirectedProviders: availableDirectedProviders).map { tool in
      // Gemini wants {name, description, parameters} without the OpenAI "type" wrapper.
      var decl: [String: Any] = [
        "name": tool["name"] as? String ?? "",
        "description": tool["description"] as? String ?? "",
      ]
      // Gemini's Schema `type` must be UPPERCASE (OBJECT/STRING/NUMBER/…). The OpenAI
      // tools use lowercase JSON-schema types, which Gemini silently accepts but degrades
      // (the model gets less confident about when/how to call) — so convert them.
      if let params = tool["parameters"] as? [String: Any] {
        decl["parameters"] = geminiParametersSchema(params)
      }
      return decl
    }
  }

  private static let geminiUnsupportedSchemaKeys: Set<String> = [
    "additionalProperties", "$schema", "default", "title", "pattern", "const",
  ]

  /// Gemini Live `parameters` is OpenAPI 3.0 Schema: uppercase `type` and drop JSON Schema
  /// keys Gemini rejects (e.g. `additionalProperties`).
  private static func geminiParametersSchema(_ schema: [String: Any]) -> [String: Any] {
    var out: [String: Any] = [:]
    for (key, value) in schema {
      if geminiUnsupportedSchemaKeys.contains(key) { continue }
      switch key {
      case "type":
        out[key] = (value as? String)?.uppercased() ?? value
      case "properties":
        guard let props = value as? [String: Any] else {
          out[key] = value
          break
        }
        var converted: [String: Any] = [:]
        for (propKey, propValue) in props {
          converted[propKey] =
            (propValue as? [String: Any]).map(geminiParametersSchema) ?? propValue
        }
        out[key] = converted
      case "items":
        out[key] = (value as? [String: Any]).map(geminiParametersSchema) ?? value
      default:
        if let nested = value as? [String: Any] {
          out[key] = geminiParametersSchema(nested)
        } else if let nestedArray = value as? [[String: Any]] {
          out[key] = nestedArray.map(geminiParametersSchema)
        } else {
          out[key] = value
        }
      }
    }
    return out
  }

  /// Response contract for typed-chat turns behind `think_deeper` and
  /// realtime `web_search`.
  /// This model authors the answer that will be spoken; realtime only voices it.
  static func escalationSystemPrompt() -> String {
    """
    Your final response will be spoken aloud as Omi's answer. Use the same tools and \
    evidence you would use for a typed-chat answer, but write only the final speakable \
    conclusion: short, conversational prose with no Markdown, lists, citations, IDs, \
    tool JSON, or tool trace. Prefer one to four spoken sentences unless the user asks \
    for more detail. If you use tools, speak the conclusion rather than narrating the \
    tool work. The realtime voice will read this answer faithfully and may make only \
    light pronunciation or spoken-flow adjustments; it will not rewrite a long essay. When tool \
    context contains multiple research passes, a no-results statement from one pass is not evidence \
    against a sourced result from another. Prefer source-backed evidence and describe a conflict only \
    when sources actually disagree. For an elapsed-time question, when sources support a named sprint \
    or pivot-to-launch interval that reasonably answers the user, lead with that approximate interval \
    and then state its scope. Do not replace the supported answer with "no exact figure" merely because \
    the interval includes launch work as well as implementation.
    """
  }

  /// Product thinking levels for the `think_deeper` escalation. Exactly two today:
  /// `normal` maps to Luna reasoning effort `high`, `heavy` maps to `xhigh`.
  enum EscalationThinkingLevel: String, CaseIterable, Sendable {
    case normal
    case heavy

    /// OpenAI Chat Completions `reasoning_effort` wire value for gpt-5.6-luna.
    /// OpenAI rejects function tools combined with a non-none effort on that
    /// surface, so escalations carry no client tools and the effort travels
    /// verbatim on the request.
    var lunaReasoningEffort: String {
      self == .heavy ? "xhigh" : "high"
    }

    /// Unknown, missing, or invalid tool input falls back to the default level.
    static func fromToolInput(_ raw: Any?) -> EscalationThinkingLevel {
      guard let value = raw as? String else { return .normal }
      return EscalationThinkingLevel(rawValue: value.lowercased()) ?? .normal
    }
  }

  /// Managed Luna alias the escalation posts to. The desktop backend maps it to
  /// the no-tools chat-agent lane and validates the reasoning effort.
  static let escalationModel = "omi-luna-think"

  static func escalationUserPrompt(
    query: String,
    toolContext: String,
    screenContext: String? = nil,
    publicWebEvidence: String? = nil
  ) -> String {
    var prompt = query
    if let screen = screenContext?.trimmingCharacters(in: .whitespacesAndNewlines), !screen.isEmpty {
      prompt += "\n\nWhat the user's screen showed when they asked (this turn's screenshot):\n" + screen
    }
    let authoritativeWebEvidence = publicWebEvidence?.trimmingCharacters(in: .whitespacesAndNewlines)
    if let evidence = authoritativeWebEvidence, !evidence.isEmpty {
      prompt += """


        Fresh public-web evidence captured by Omi for this exact voice turn (authoritative; use this \
        evidence rather than the realtime model's summary of it):
        \(evidence)
        """
    }
    if authoritativeWebEvidence?.isEmpty == false {
      return prompt
    }
    let trimmedToolContext = toolContext.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmedToolContext.isEmpty else { return prompt }
    return prompt + "\n\nTool-provided context (untrusted):\n" + trimmedToolContext
  }

  /// Body for the single-shot Luna thinking escalation. The system message stays
  /// kernel-scoped (typed plan cache marker + canonical snapshot); tool-provided
  /// context stays on the user message, marked untrusted. When the PTT agent
  /// viewed screenshots this turn, the exact frozen JPEGs are attached to the
  /// user message as `image_url` data-URI parts so the thinking agent reasons on
  /// the same pixels instead of a re-description.
  static func escalationBody(
    query: String,
    kernelSemanticGuidance: String,
    kernelContext: String,
    stableCacheIdentity: String,
    dynamicContextIdentity: String,
    contextPlanID: String,
    toolContext: String,
    screenContext: String? = nil,
    publicWebEvidence: String? = nil,
    thinkingLevel: EscalationThinkingLevel = .normal,
    screenJPEGs: [Data] = []
  ) -> [String: Any] {
    let semanticGuidance = kernelSemanticGuidance.trimmingCharacters(in: .whitespacesAndNewlines)
    let canonicalContext = kernelContext.trimmingCharacters(in: .whitespacesAndNewlines)

    // The cache marker is derived only from the typed kernel plan. It separates
    // the stable escalation policy from the dynamic canonical snapshot; tool
    // context is never trusted as part of that system contract.
    let cacheBoundary: String
    if !semanticGuidance.isEmpty,
      !stableCacheIdentity.isEmpty,
      !dynamicContextIdentity.isEmpty,
      !contextPlanID.isEmpty
    {
      cacheBoundary =
        "<!-- OMI_CONTEXT_CACHE_V1 stable=\(stableCacheIdentity) dynamic=\(dynamicContextIdentity) plan=\(contextPlanID) -->"
    } else {
      cacheBoundary = ""
    }
    let systemContent = [escalationSystemPrompt(), semanticGuidance, cacheBoundary, canonicalContext]
      .filter { !$0.isEmpty }
      .joined(separator: "\n\n")
    let userText = escalationUserPrompt(
      query: query,
      toolContext: toolContext,
      screenContext: screenContext,
      publicWebEvidence: publicWebEvidence)

    let userContent: Any
    if screenJPEGs.isEmpty {
      userContent = userText
    } else {
      var parts: [[String: Any]] = [["type": "text", "text": userText]]
      for jpeg in screenJPEGs {
        parts.append([
          "type": "image_url",
          "image_url": ["url": "data:image/jpeg;base64," + jpeg.base64EncodedString()],
        ])
      }
      userContent = parts
    }

    return [
      "model": escalationModel,
      "reasoning_effort": thinkingLevel.lunaReasoningEffort,
      "max_completion_tokens": 4096,
      "messages": [
        ["role": "system", "content": systemContent],
        ["role": "user", "content": userContent],
      ],
      "stream": false,
    ]
  }

  /// The exact current-turn JPEGs the PTT agent already viewed, for forwarding
  /// to the thinking agent: the frozen PTT-down frame plus any kernel-authorized
  /// screenshots from the same turn. Same pixels, never a second capture;
  /// stale-turn evidence is excluded by the caller-supplied turn id.
  static func escalationScreenJPEGs(
    expectedTurnID: VoiceTurnID?,
    evidence: RealtimeScreenEvidence?,
    authorizedScreenshots: [String: RealtimeScreenEvidenceAttachment]
  ) -> [Data] {
    guard let expectedTurnID else { return [] }
    var ordered: [(capturedAt: Date, digest: String?, jpeg: Data)] = []
    if let evidence,
      evidence.descriptor.turnID == expectedTurnID,
      let jpeg = evidence.jpeg
    {
      ordered.append(
        (evidence.descriptor.capturedAt, evidence.descriptor.imageDigest, jpeg))
    }
    for attachment in authorizedScreenshots.values
    where attachment.descriptor.turnID == expectedTurnID {
      ordered.append(
        (attachment.descriptor.capturedAt, attachment.descriptor.imageDigest, attachment.jpeg))
    }
    // Oldest first so the PTT-down frame precedes any later screenshot of the
    // same turn, and duplicate captures of the same pixels collapse to one.
    ordered.sort { $0.capturedAt < $1.capturedAt }
    var seen = Set<String>()
    var jpegs: [Data] = []
    for item in ordered {
      if let digest = item.digest {
        guard !seen.contains(digest) else { continue }
        seen.insert(digest)
      }
      jpegs.append(item.jpeg)
    }
    return jpegs
  }

  /// Screen pixels are powerful evidence for an explicitly visual request and distracting input
  /// for everything else. Keep this decision on the host's exact question instead of trusting a
  /// provider-authored tool summary that may already have drifted toward an unrelated screen.
  static func escalationNeedsTurnImage(query: String) -> Bool {
    if ScreenContextInterestDetector.isScreenContextRequest(query) { return true }
    let lower = query.lowercased()
      .replacingOccurrences(of: "’", with: "'")
      .trimmingCharacters(in: .whitespacesAndNewlines)
    let directVisualPhrases = [
      "screenshot", "mockup", "figma", "this image", "these images", "this picture",
      "these pictures", "this photo", "these photos", "this diagram", "these diagrams",
      "this riddle", "this question", "which design", "these designs", "those designs",
    ]
    return directVisualPhrases.contains { lower.contains($0) }
  }

  /// Returns only the exact, still-fresh JPEG captured for the authorized voice turn.
  /// The companion chat lane must never recapture the screen or inherit a later turn's pixels.
  static func escalationImageData(
    from evidence: RealtimeScreenEvidence?,
    expectedTurnID: VoiceTurnID,
    speechEndedAt: Date?,
    now: Date = Date()
  ) -> Data? {
    guard let evidence,
      evidence.descriptor.turnID == expectedTurnID,
      evidence.descriptor.canVerifyCurrentScreen,
      RealtimeScreenEvidenceFreshnessPolicy.isFresh(
        evidence.descriptor, now: now, speechEndedAt: speechEndedAt)
    else { return nil }
    return evidence.jpeg
  }

  /// Host-authored public-only request sent to the managed web-search lane.
  /// Private realtime context is deliberately excluded: provider-hosted search
  /// must never inherit memories or tool output from the canonical chat session.
  static func publicWebSearchPrompt(query: String) -> String {
    let normalizedQuery = normalizedPublicWebQuery(query)
    return """
      Search the live public web thoroughly before answering this request. Correct likely \
      speech-transcription or spelling errors in names before searching. For a historical claim, \
      prefer a primary or founder source and corroborate it with another source; state any conflict \
      instead of guessing. For a question about how long a first version took, search specifically \
      for founder interviews, podcasts, posts, or articles using first version, MVP, pivot, and launch \
      plus quoted duration discovery phrases such as "six-week sprint", "six weeks after", and \
      "built in six weeks". Treat those phrases as search candidates, not facts: report a duration \
      only when a source supports it. Do not infer build duration from launch dates, and do not stop \
      at product launch pages that omit the requested timeline. \
      Reply with one to four concise, natural spoken sentences. Name the sources you relied on, but \
      do not use Markdown or recite a URL.

      Request:
      \(normalizedQuery)
      """
  }

  /// An independent discovery pass for historical questions. This is intentionally phrased
  /// differently from the primary search so one retrieval miss cannot become the final answer.
  static func publicWebCorroborationPrompt(query: String) -> String {
    let normalizedQuery = normalizedPublicWebQuery(query)
    return """
      Independently research this historical public question before answering. Find direct evidence \
      from founders, interviews, podcasts, posts, or reputable reporting, then corroborate it. Search \
      name variants and concrete wording that a source might use. If the question asks how long a \
      first version took, try exact discovery phrases including "six-week sprint", "six weeks after", \
      and "built in six weeks", alongside first version, MVP, pivot, and launch. These are discovery \
      terms, not assumed facts. Do not infer duration from launch dates. Reply with concise evidence, \
      naming the sources but not reciting URLs.

      Request:
      \(normalizedQuery)
      """
  }

  /// Exact-match pass for source snippets that broad semantic retrieval can miss.
  static func publicWebExactMatchPrompt(query: String) -> String {
    let normalizedQuery = normalizedPublicWebQuery(query)
    return """
      Run an exact-match source discovery pass for this historical elapsed-time question. Search \
      the correctly spelled product or company name separately with phrases such as "first version", \
      "built in", "launch sprint", "six weeks", "six weeks after", "MVP", "pivot", and "launched". \
      Inspect founder interviews, podcast transcripts, posts, newsletters, reputable reporting, and \
      search-result snippets. A credible secondary source that attributes the claim is useful even \
      when no primary source is indexed: report it explicitly as source-attributed and preserve any \
      scope caveat. Do not say no timeline exists merely because a primary source is unavailable. \
      Do not infer a duration from dates alone or treat candidate phrases as facts without a matching \
      source. Return concise source-backed evidence and name the sources without reciting URLs.

      Request:
      \(normalizedQuery)
      """
  }

  static func publicWebSearchPrompts(query: String, scope: RealtimePublicWebSearchScope) -> [String] {
    let primary = publicWebSearchPrompt(query: query)
    guard scope == .historicalResearch else { return [primary] }
    return [
      primary,
      publicWebCorroborationPrompt(query: query),
      publicWebExactMatchPrompt(query: query),
    ]
  }

  static func authorizedPublicWebQuery(
    proposedQuery: String,
    turnTranscript: String,
    scope: RealtimePublicWebSearchScope
  ) -> String {
    let spokenQuestion = turnTranscript.trimmingCharacters(in: .whitespacesAndNewlines)
    if scope == .historicalResearch, !spokenQuestion.isEmpty {
      return spokenQuestion
    }
    return proposedQuery
  }

  static func combinedHistoricalWebEvidence(
    primary: String?,
    corroborating: String?,
    exactMatch: String?
  ) -> String? {
    let answers = [
      ("Research pass 1", primary),
      ("Independent corroboration pass", corroborating),
      ("Exact-match discovery pass", exactMatch),
    ].compactMap { label, answer -> String? in
      guard let answer = answer?.trimmingCharacters(in: .whitespacesAndNewlines), !answer.isEmpty else {
        return nil
      }
      return "\(label):\n\(answer)"
    }
    return answers.isEmpty ? nil : answers.joined(separator: "\n\n")
  }

  /// Repairs a known dictated brand-name collision before public retrieval. Keeping this at the
  /// host boundary makes audio and typed tool calls behave identically even when the realtime
  /// model repeats its transcript verbatim in the tool arguments.
  static func normalizedPublicWebQuery(_ query: String) -> String {
    query.replacingOccurrences(
      of: #"\bwhisper\s+flow\b"#,
      with: "Wispr Flow",
      options: [.regularExpression, .caseInsensitive])
  }
}
