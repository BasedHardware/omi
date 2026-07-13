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

  private static func availableDirectedProviderRawValues() -> [String] {
    ["openclaw", "hermes"]
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

  static func systemInstruction(
    kernelContext: String = "", userLanguages: [String] = []
  ) -> String {
    let canonicalContext = kernelContext.trimmingCharacters(in: .whitespacesAndNewlines)

    return """
    You are Omi, a fast spoken-voice assistant on the user's Mac. You hear the user's \
    microphone; reply conversationally in one or two sentences by default. \
    \(userLanguagesLine(userLanguages))Reply in the same language the user is speaking.

    \(canonicalContext)

    \(DesktopCapabilityRegistry.realtimeSelfModelPrompt)

    The generated tool declarations below describe the capabilities available on this \
    surface. A tool call is only a proposal: the kernel makes the authoritative route and \
    permission decision. Never claim a physical action succeeded unless its tool result says \
    it succeeded.

    Using tools: when a request needs a tool, ALWAYS give a short spoken heads-up first so the \
    user knows you're on it and that it won't be instant — then call the tool and speak the \
    result when it returns. Never go silent during a tool call; the user can't see what you're \
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
    without calling a tool.

    Keep latency low: prefer answering directly when you can.
    """
  }

  /// OpenAI Realtime GA `session.tools` entries.
  static var openAITools: [[String: Any]] {
    openAITools(availableDirectedProviders: availableDirectedProviderRawValues())
  }

  static func openAITools(availableDirectedProviders: [String]) -> [[String: Any]] {
    let providerProperty: [String: Any]? = availableDirectedProviders.isEmpty ? nil : [
      "type": "string",
      "enum": availableDirectedProviders,
      "description": "Optional available local provider to run this background agent through.",
    ]
    return GeneratedRealtimeTools.baseOpenAITools(providerProperty: providerProperty)
  }

  /// Gemini Live `setup.tools[0].functionDeclarations` entries (same surface). Derived once
  /// from `openAITools`.
  static var geminiFunctionDeclarations: [[String: Any]] {
    geminiFunctionDeclarations(availableDirectedProviders: availableDirectedProviderRawValues())
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

  static func escalationBody(query: String, context: String) -> [String: Any] {
    let trimmedContext = context.trimmingCharacters(in: .whitespacesAndNewlines)
    let userContent =
      trimmedContext.isEmpty ? query : query + "\n\nContext I already have:\n" + trimmedContext
    let messages: [[String: String]] = [
      ["role": "system", "content": escalationSystemPrompt()],
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
