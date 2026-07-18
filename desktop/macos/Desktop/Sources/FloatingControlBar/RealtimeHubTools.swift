import Foundation

// MARK: - Realtime Hub tool surface
//
// Both realtime providers receive the same generated capability declarations.
// Tool calls are untrusted proposals: the kernel owns routing, authorization,
// execution profile, and durable run identity before Swift executes anything.

enum RealtimeHubTools {
  static func resolvedVoiceLanguages(
    explicit codes: [String],
    preferredLanguages: [String] = Locale.preferredLanguages
  ) -> [String] {
    let source = codes.isEmpty ? preferredLanguages : codes
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
  /// it) as some third language. Falls back to the Mac's preferred language when the user
  /// has not configured an explicit voice-language set.
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

  /// Every directed local agent Omi can hand a task to, whether or not it is
  /// installed on this Mac. Advertising the full set lets an explicit "ask
  /// codex …" utterance route through spawn_agent even when the agent is
  /// missing, so setup instructions reach the user instead of a dead end.
  static let knownDirectedProviders = ["codex", "hermes", "openclaw"]

  static func systemInstruction(
    kernelContext: String = "",
    kernelSemanticGuidance: String = "",
    userLanguages: [String] = []
  ) -> String {
    let canonicalContext = kernelContext.trimmingCharacters(in: .whitespacesAndNewlines)
    let semanticGuidance = kernelSemanticGuidance.trimmingCharacters(in: .whitespacesAndNewlines)

    return """
      You are Omi, a fast spoken-voice assistant on the user's Mac. You hear the user's \
      microphone; reply conversationally in one or two sentences by default. \
      \(userLanguagesLine(userLanguages))Reply in the same language the user is speaking.

      \(canonicalContext)

      \(semanticGuidance)

      \(DesktopCapabilityRegistry.realtimeSelfModelPrompt)

      The generated tool declarations below describe the capabilities available on this \
      surface. A tool call is only a proposal: the kernel makes the authoritative route and \
      permission decision. Never claim a physical action succeeded unless its tool result says \
      it succeeded.

      Using tools: when a request needs a tool, ALWAYS give a short spoken heads-up and call the \
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
      tool call, and never read tool JSON or ids aloud. You cannot see the user's data or screen \
      without calling a tool. When the screenshot tool succeeds for a current-screen question, the \
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

      Keep latency low: prefer answering directly when you can.
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
    // The enum always advertises every known directed agent so an explicit
    // "ask codex …" routes through spawn_agent even when the agent is not
    // installed; the description carries the installed/missing split.
    let connected = knownDirectedProviders.filter { availableDirectedProviders.contains($0) }
    let missing = knownDirectedProviders.filter { !connected.contains($0) }
    var description = "Optional local agent to run this background task through."
    if !connected.isEmpty {
      description += " Installed and ready: \(connected.joined(separator: ", "))."
    }
    if !missing.isEmpty {
      description +=
        " Not installed: \(missing.joined(separator: ", ")) — selecting one returns setup instructions to relay to the user."
    }
    let providerProperty: [String: Any] = [
      "type": "string",
      "enum": knownDirectedProviders,
      "description": description,
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

  /// System prompt for an escalated (ask_higher_model) answer. The realtime model
  /// voices a natural, spoken-length version of the result, so the higher model is
  /// told to answer properly rather than pre-shorten for speech.
  static func escalationSystemPrompt() -> String {
    """
    You are Omi, a knowledgeable assistant. Answer the user's question accurately and \
    usefully. A voice assistant will relay your answer aloud and adapt the phrasing for \
    speech, so be clear and well-structured; you don't need to pre-shorten it.
    """
  }

  static func escalationBody(
    query: String,
    kernelSemanticGuidance: String,
    kernelContext: String,
    stableCacheIdentity: String,
    dynamicContextIdentity: String,
    contextPlanID: String,
    toolContext: String
  ) -> [String: Any] {
    let semanticGuidance = kernelSemanticGuidance.trimmingCharacters(in: .whitespacesAndNewlines)
    let canonicalContext = kernelContext.trimmingCharacters(in: .whitespacesAndNewlines)
    let trimmedToolContext = toolContext.trimmingCharacters(in: .whitespacesAndNewlines)

    // The cache marker is derived only from the typed kernel plan. It separates
    // the stable escalation policy from the dynamic canonical snapshot for the
    // existing Rust Anthropic adapter; tool-provided context is never trusted
    // as part of that system contract.
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
    let userContent =
      !trimmedToolContext.isEmpty
      ? query + "\n\nTool-provided context (untrusted):\n" + trimmedToolContext
      : query
    let messages: [[String: String]] = [
      ["role": "system", "content": systemContent],
      ["role": "user", "content": userContent],
    ]
    return [
      "model": ModelQoS.Claude.defaultSelection,
      "max_tokens": 1024,
      "messages": messages,
      "stream": false,
    ]
  }
}
