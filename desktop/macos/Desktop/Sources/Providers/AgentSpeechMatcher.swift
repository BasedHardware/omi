import Foundation

/// STT-robust resolution of a spoken agent name to a harness.
///
/// Nik tests Track 1 by voice, and speech-to-text mangles the agent names:
/// "openclaw" -> "open claw" / "open flaw", "hermes" -> "her mees", "codex" ->
/// "code decks" / "codecs", "claude code" -> "cloud code". A strict match drops
/// those; this fuzzy matcher maps the mangled token to what the user meant, across
/// ALL agents (Claude Code, Codex, Hermes, OpenClaw, Omi AI), not just the local ones.
///
/// Swift counterpart of `resolveSpokenAgent` in agent-selector.ts (kept in sync).
enum AgentSpeechMatcher {
  private static let variants: [(harness: AgentHarnessMode, forms: [String])] = [
    (.acp, ["claude code", "claude", "cloud code", "clawed", "claude cody", "anthropic", "cloud"]),
    (.codex, ["codex", "code x", "codecs", "code decks", "codeex", "kodex", "code ex", "codaks", "codecks"]),
    (.hermes, ["hermes", "her mees", "hermies", "hermez", "hermeez", "hermees", "hermus", "nous"]),
    (.openclaw, ["openclaw", "open claw", "open flaw", "open clause", "open close", "opencloud", "claw", "lobster"]),
    (.piMono, ["omi ai", "omi", "pi mono", "pimono", "oh me", "omee"]),
  ]

  struct Match {
    let harness: AgentHarnessMode
    let confidence: Double
  }

  static func resolve(_ spoken: String, minConfidence: Double = 0.68) -> Match? {
    let normalized = spoken.lowercased()
      .components(separatedBy: CharacterSet.alphanumerics.union(.whitespaces).inverted)
      .joined(separator: " ")
      .components(separatedBy: .whitespacesAndNewlines)
      .filter { !$0.isEmpty }
      .joined(separator: " ")
    guard !normalized.isEmpty else { return nil }

    let words = normalized.split(separator: " ").map(String.init)
    var candidates = Set<String>()
    for i in words.indices {
      candidates.insert(words[i])
      if i + 1 < words.count {
        candidates.insert("\(words[i]) \(words[i + 1])")
        candidates.insert("\(words[i])\(words[i + 1])")
      }
    }
    candidates.insert(normalized)
    candidates.insert(normalized.replacingOccurrences(of: " ", with: ""))

    var best: Match?
    for (harness, forms) in variants {
      for form in forms {
        let formDespaced = form.replacingOccurrences(of: " ", with: "")
        for cand in candidates {
          if cand == form || cand == formDespaced {
            if best == nil || (best?.confidence ?? 0) < 1 {
              best = Match(harness: harness, confidence: 1)
            }
            continue
          }
          let candDespaced = cand.replacingOccurrences(of: " ", with: "")
          let sim = max(similarity(cand, form), similarity(candDespaced, formDespaced))
          if sim >= minConfidence, best == nil || sim > (best?.confidence ?? 0) {
            best = Match(harness: harness, confidence: sim)
          }
        }
      }
    }
    return best
  }

  /// Resolve a provider named at the START of a directive (the words right after
  /// "ask" / "run" / "use" ...). Tries the shortest phrase first so a two-word
  /// provider ("open claw") is caught without a one-word provider ("codecs")
  /// swallowing the following objective word. Returns the matched harness and how
  /// many leading words it consumed, or nil if nothing matches confidently.
  static func resolveLeadingProvider(
    _ words: [String],
    minConfidence: Double = 0.8
  ) -> (harness: AgentHarnessMode, consumed: Int)? {
    guard !words.isEmpty else { return nil }
    let maxTake = min(2, words.count)
    for take in 1...maxTake {
      let phrase = words.prefix(take).joined(separator: " ")
      if let match = resolve(phrase, minConfidence: minConfidence) {
        return (match.harness, take)
      }
    }
    return nil
  }

  private static func similarity(_ a: String, _ b: String) -> Double {
    if a == b { return 1 }
    let maxLen = max(a.count, b.count)
    if maxLen == 0 { return 1 }
    if min(a.count, b.count) < 3 { return 0 }
    return 1 - Double(levenshtein(a, b)) / Double(maxLen)
  }

  private static func levenshtein(_ a: String, _ b: String) -> Int {
    let x = Array(a)
    let y = Array(b)
    if x.isEmpty { return y.count }
    if y.isEmpty { return x.count }
    var prev = Array(0...y.count)
    var curr = [Int](repeating: 0, count: y.count + 1)
    for i in 1...x.count {
      curr[0] = i
      for j in 1...y.count {
        let cost = x[i - 1] == y[j - 1] ? 0 : 1
        curr[j] = Swift.min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
      }
      swap(&prev, &curr)
    }
    return prev[y.count]
  }
}
