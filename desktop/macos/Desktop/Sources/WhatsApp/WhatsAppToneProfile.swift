import Foundation

struct WhatsAppToneProfileSnapshot: Codable, Equatable, Sendable {
  let generatedAt: Date
  let sampleCount: Int
  let averageLength: Int
  let usesExclamation: Bool
  let usesQuestions: Bool
  let commonOpeners: [String]
  let commonClosers: [String]

  var styleGuide: String {
    guard sampleCount > 0 else {
      return "Tone profile: no WhatsApp sent-message samples yet. Use a neutral, concise, polite style."
    }

    var parts = [
      "Tone profile from \(sampleCount) sent WhatsApp messages:",
      "Typical length is about \(averageLength) characters.",
      usesExclamation ? "Exclamation marks are normal for this user." : "Avoid extra exclamation marks.",
      usesQuestions ? "The user commonly asks short follow-up questions." : "Use questions only when needed.",
    ]
    if !commonOpeners.isEmpty {
      parts.append("Common openers: \(commonOpeners.joined(separator: ", ")).")
    }
    if !commonClosers.isEmpty {
      parts.append("Common closers: \(commonClosers.joined(separator: ", ")).")
    }
    return parts.joined(separator: " ")
  }
}

@MainActor
final class WhatsAppToneProfile: ObservableObject {
  static let shared = WhatsAppToneProfile()

  @Published private(set) var snapshot: WhatsAppToneProfileSnapshot?

  private let defaults = UserDefaults.standard
  private let snapshotKey = "whatsapp.toneProfile.snapshot"

  private init() {
    if let data = defaults.data(forKey: snapshotKey),
      let decoded = try? JSONDecoder().decode(WhatsAppToneProfileSnapshot.self, from: data)
    {
      snapshot = decoded
    }
  }

  func styleGuide() -> String {
    guard WhatsAppReplySettings.shared.toneMatchEnabled else {
      return "Tone profile: tone matching is disabled. Use a neutral, concise, polite style."
    }
    return snapshot?.styleGuide
      ?? "Tone profile: no WhatsApp sent-message samples yet. Use a neutral, concise, polite style."
  }

  func rebuild(limit: Int = 200) async {
    let result = await runWacli(["messages", "list", "--from-me", "--limit", String(max(1, min(limit, 500)))])
    guard result.exitCode == 0 else {
      log("WhatsAppToneProfile: failed to rebuild profile: \(result.output.prefix(300))")
      return
    }

    let texts = extractSentTexts(from: result.output)
    let nextSnapshot = buildSnapshot(from: texts)
    snapshot = nextSnapshot
    if let data = try? JSONEncoder().encode(nextSnapshot) {
      defaults.set(data, forKey: snapshotKey)
    }
  }

  private func buildSnapshot(from texts: [String]) -> WhatsAppToneProfileSnapshot {
    let cleaned = texts
      .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
      .filter { !$0.isEmpty }
    let averageLength = cleaned.isEmpty ? 0 : cleaned.map(\.count).reduce(0, +) / cleaned.count
    return WhatsAppToneProfileSnapshot(
      generatedAt: Date(),
      sampleCount: cleaned.count,
      averageLength: averageLength,
      usesExclamation: ratio(in: cleaned, containing: "!") >= 0.2,
      usesQuestions: ratio(in: cleaned, containing: "?") >= 0.2,
      commonOpeners: commonEdgePhrases(in: cleaned, first: true),
      commonClosers: commonEdgePhrases(in: cleaned, first: false)
    )
  }

  private func ratio(in texts: [String], containing token: Character) -> Double {
    guard !texts.isEmpty else { return 0 }
    let matches = texts.filter { $0.contains(token) }.count
    return Double(matches) / Double(texts.count)
  }

  private func commonEdgePhrases(in texts: [String], first: Bool) -> [String] {
    var counts: [String: Int] = [:]
    for text in texts {
      let words = text
        .lowercased()
        .split { !$0.isLetter && !$0.isNumber }
        .prefix(first ? 3 : Int.max)
      let selected = first ? Array(words.prefix(2)) : Array(words.suffix(2))
      guard !selected.isEmpty else { continue }
      let phrase = selected.joined(separator: " ")
      guard phrase.count >= 2 else { continue }
      counts[phrase, default: 0] += 1
    }
    return counts
      .filter { $0.value >= 2 }
      .sorted { lhs, rhs in
        lhs.value == rhs.value ? lhs.key < rhs.key : lhs.value > rhs.value
      }
      .prefix(3)
      .map(\.key)
  }

  private func extractSentTexts(from output: String) -> [String] {
    guard let data = output.data(using: .utf8),
      let json = try? JSONSerialization.jsonObject(with: data)
    else {
      return []
    }
    return collectTexts(from: json)
  }

  private func collectTexts(from value: Any) -> [String] {
    if let array = value as? [Any] {
      return array.flatMap { collectTexts(from: $0) }
    }
    guard let object = value as? [String: Any] else {
      return []
    }

    let fromMe = (object["fromMe"] as? Bool) ?? (object["from_me"] as? Bool) ?? true
    var texts: [String] = []
    if fromMe {
      for key in ["text", "body", "message", "caption"] {
        if let text = object[key] as? String, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
          texts.append(text)
        }
      }
    }
    for child in object.values {
      texts.append(contentsOf: collectTexts(from: child))
    }
    return texts
  }

  private func runWacli(_ arguments: [String]) async -> (output: String, exitCode: Int32) {
    guard let binary = WhatsAppService.findWacliBinary() else {
      return ("wacli not installed", 127)
    }
    let storeDir = WhatsAppService.defaultStoreDirectory()
    return await Task.detached(priority: .utility) {
      do {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: binary)
        process.arguments = ["--store", storeDir, "--json", "--read-only"] + arguments

        var env = ProcessInfo.processInfo.environment
        env["WACLI_READONLY"] = "1"
        let binaryDir = (binary as NSString).deletingLastPathComponent
        let existingPath = env["PATH"] ?? "/usr/bin:/bin"
        if !existingPath.components(separatedBy: ":").contains(binaryDir) {
          env["PATH"] = "\(binaryDir):\(existingPath)"
        }
        process.environment = env

        let outputPipe = Pipe()
        process.standardOutput = outputPipe
        process.standardError = outputPipe
        try process.run()
        let data = outputPipe.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        let output = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return (output, process.terminationStatus)
      } catch {
        return ("\(error)", 1)
      }
    }.value
  }
}
