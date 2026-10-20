import Foundation

/// Read-only presentation repair for historical notes. The JSON contract is hand-authored.
/// Notes have segment provenance; numeric chat citations use their separate message-local list.
enum NoteCitationContract {
  static func repair(_ input: String, valid: Set<String>) -> (text: String, sourceIDs: [String]) {
    var text = input
    var recovered: [String] = []
    var seen = Set<String>()
    while true {
      let result = repairPass(text, valid: valid)
      recovered.append(contentsOf: result.sourceIDs.filter { seen.insert($0).inserted })
      if result.text == text { return (text, recovered) }
      text = result.text
    }
  }

  /// Read-time repair of a conversation title (web `presentableNoteTitle`). Titles keep ordinary
  /// bracketed words ("Project [Q3]"): only bracket units made of known IDs, citation-shaped IDs (a
  /// segment UUID, `s01234`, a `^1` footnote) or a speaker label are debris. Everything else the
  /// note repair does applies as for any note text.
  static func repairTitle(_ input: String, valid: Set<String>) -> String {
    let mask = "\u{E012}"
    if input.contains(mask) { return repair(input, valid: valid).text }
    var kept: [String] = []
    let masked = replace(input, pattern: #"[\[［【][^\[\]［］【】\n]*[\]］】]"#) { unit in
      let bare = String(unit.dropFirst().dropLast())
        .replacingOccurrences(of: "[\u{200B}\u{200C}\u{200D}\u{2060}\u{FEFF}]", with: "", options: .regularExpression)
        .trimmingCharacters(in: .whitespacesAndNewlines)
      let tokens = bare.split(whereSeparator: { $0.isWhitespace || $0 == "," || $0 == ";" }).map(String.init)
      let citation =
        matches(bare, #"(?i)^(?:spk|speaker)[ _]\p{Nd}+:?$"#)
        || tokens.allSatisfy { token in
          valid.contains(token)
            || matches(
              token,
              #"(?i)^(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|s[0-9]{4,}|\^[0-9]+)$"#)
        }
      if citation || kept.count >= 0x0F00 { return unit }
      kept.append(unit)
      return mask + String(Unicode.Scalar(UInt32(0xE100 + kept.count - 1))!)
    }
    return replace(repair(masked, valid: valid).text, pattern: "\u{E012}[\u{E100}-\u{EFFF}]") { slot in
      kept[Int(slot.unicodeScalars.last!.value) - 0xE100]
    }
  }

  /// Protected-unit keys: a prefix the input does not contain, the unit's index in base 254 over
  /// U+E002..U+E0FF, then U+E001. Private-use characters match no repair pattern, and the keys
  /// stay short however many units a note holds.
  private static func keyDigits(_ index: Int) -> String {
    var index = index
    var scalars: [Unicode.Scalar] = []
    repeat {
      scalars.insert(Unicode.Scalar(UInt32(0xE002 + index % 254))!, at: 0)
      index /= 254
    } while index > 0
    return String(String.UnicodeScalarView(scalars))
  }

  private static func repairPass(_ input: String, valid: Set<String>) -> (text: String, sourceIDs: [String]) {
    var protected: [String: String] = [:]
    var prefix = "\u{E000}"
    while input.contains(prefix) { prefix += "\u{E000}" }
    let marker = "\u{0000}"
    func protect(_ value: String) -> String {
      let key = prefix + keyDigits(protected.count) + "\u{E001}"
      protected[key] = value
      return key
    }
    var text = replace(
      input,
      pattern:
        #"(?m)^[ \t]{0,3}(`{3,}|~{3,})[^\n]*\n[\s\S]*?(?:^[ \t]{0,3}\1[`~]*[ \t]*(?:\n|$)|\z)|(`+)(?!`)[\s\S]*?(?<!`)\2(?!`)"#
    ) { protect($0) }
    var recovered: [String] = []
    func remove(_ ids: [String]) -> String {
      recovered.append(contentsOf: ids)
      return marker
    }
    func cleanSeparators(_ value: String) -> String {
      var content = value.replacingOccurrences(of: marker, with: "").replacingOccurrences(of: "\u{0001}", with: "")
      content = replace(content, pattern: #"^[\s,;]+|[\s,;]+$"#) { _ in "" }
      return replace(content, pattern: #"([,;])(?:\s*[,;])+"#) { String($0.prefix(1)) }
    }
    let linkPattern = #"^\[([^\]\n]*)\]\(([^)\n]*)\)$"#
    func unit(_ value: String) -> String {
      if let groups = groups(value, pattern: linkPattern) {
        let label = groups[0].trimmingCharacters(in: .whitespacesAndNewlines)
        if label.isEmpty { return remove([]) }
        if valid.contains(label) { return remove([label]) }
        let destination = groups[1].trimmingCharacters(in: .whitespacesAndNewlines)
        let scheme =
          destination.contains(":") ? String(destination.split(separator: ":", maxSplits: 1)[0]).lowercased() : ""
        return ["http", "https", "mailto"].contains(scheme) ? protect(value) : label
      }
      if value.hasPrefix("(") {
        let tokens = value.dropFirst().dropLast().split(whereSeparator: { $0 == ";" || $0 == "," })
        let ids = tokens.map { token -> String in
          let trimmed = token.trimmingCharacters(in: .whitespacesAndNewlines)
          return groups(trimmed, pattern: linkPattern)?.first?.trimmingCharacters(in: .whitespacesAndNewlines)
            ?? trimmed
        }.filter { !$0.isEmpty }
        return !ids.isEmpty && ids.allSatisfy { valid.contains($0) }
          ? remove(ids)
          : replace(value, pattern: #"\[[^\[\]\n]*\]\([^\n)]*\)|[\[［【][^\[\]［］【】\n]*[\]］】]"#, transform: unit)
      }
      let content = replace(String(value.dropFirst().dropLast()), pattern: #"[\u200b\u200c\u200d\u2060\ufeff]"#) { _ in
        ""
      }
      .trimmingCharacters(in: .whitespacesAndNewlines)
      let tokens = content.components(
        separatedBy: CharacterSet.whitespacesAndNewlines.union(CharacterSet(charactersIn: ",;"))
      )
      .filter { !$0.isEmpty }
      if !tokens.isEmpty && tokens.allSatisfy({ valid.contains($0) }) { return remove(tokens) }
      let header = content.components(separatedBy: .whitespacesAndNewlines).filter { !$0.isEmpty }
      if header.count == 2, valid.contains(header[0]), matches(header[1], #"^[?]?[0-9A-Za-z]{1,3}$"#) {
        return remove([header[0]])
      }
      let mixedIDs = tokens.filter { valid.contains($0) }
      if !mixedIDs.isEmpty {
        recovered.append(contentsOf: mixedIDs)
        return cleanSeparators(replace(content, pattern: #"[^\s,;]+"#) { valid.contains($0) ? "" : $0 })
      }
      if tokens.isEmpty || matches(content, #"(?i)^(?:spk|speaker)[ _]\d+:?$"#)
        || matches(content, #"^(?:[A-Za-z0-9][A-Za-z0-9._:-]{0,95}|\^\d+)$"#)
      {
        return marker
      }
      return protect(value)
    }
    text = replace(
      text, pattern: #"\[[^\[\]\n]*\]\([^\n)]*\)|(?<!\])\(((?:[^()\n]|\([^()\n]*\))+)\)|[\[［【][^\[\]［］【】\n]*[\]］】]"#,
      transform: unit)
    for sourceID in valid.sorted(by: { $0.count == $1.count ? $0 < $1 : $0.count > $1.count }) {
      text = replace(text, pattern: #"(?<![\w-])"# + NSRegularExpression.escapedPattern(for: sourceID) + #"(?![\w-])"#)
      { _ in marker }
    }
    text = replace(text, pattern: #"(?i)\b(?:spk|speaker)[ _]\d+\b:?[ \t]*"#) { _ in marker }
    while true {
      let cleaned = replace(text, pattern: #"\([^()\n]*\)"#) { value in
        guard value.contains(marker) || value.contains("\u{0001}") else { return value }
        let content = cleanSeparators(String(value.dropFirst().dropLast()))
        return content.isEmpty ? "\u{0001}" : "(\(content))"
      }
      if cleaned == text { break }
      text = cleaned
    }
    if text.contains(marker) {
      let escaped = NSRegularExpression.escapedPattern(for: marker)
      text = replace(text, pattern: escaped + "(?:[ \\t]*" + escaped + ")+") { _ in marker }
      text = replace(text, pattern: "[ \\t]+" + escaped + "[ \\t]+") { _ in " " }
      text = replace(text, pattern: "[ \\t]+" + escaped + #"(?=[,.;:]|\n|$)"#) { _ in "" }
      text = replace(text, pattern: escaped + "[ \\t]+") { _ in "" }
      text = text.replacingOccurrences(of: marker, with: "").trimmingCharacters(in: .whitespacesAndNewlines)
    }
    if text.contains("\u{0001}") {
      text = text.replacingOccurrences(of: "\u{0001}", with: "").trimmingCharacters(in: .whitespacesAndNewlines)
    }
    // One pass, restoring nested units (a link label that held a code span) recursively.
    let keyPattern = NSRegularExpression.escapedPattern(for: prefix) + "[\u{E002}-\u{E0FF}]+\u{E001}"
    func restore(_ value: String) -> String {
      replace(value, pattern: keyPattern) { key in protected[key].map(restore) ?? key }
    }
    text = restore(text)
    var seen = Set<String>()
    return (text, recovered.filter { seen.insert($0).inserted })
  }

  private static func replace(_ text: String, pattern: String, transform: (String) -> String) -> String {
    guard let regex = try? NSRegularExpression(pattern: pattern) else { return text }
    var output = ""
    var start = text.startIndex
    for match in regex.matches(in: text, range: NSRange(text.startIndex..., in: text)) {
      guard let range = Range(match.range, in: text) else { continue }
      output += text[start..<range.lowerBound] + transform(String(text[range]))
      start = range.upperBound
    }
    return output + text[start...]
  }

  private static func matches(_ text: String, _ pattern: String) -> Bool {
    text.range(of: pattern, options: .regularExpression) != nil
  }

  private static func groups(_ text: String, pattern: String) -> [String]? {
    guard let regex = try? NSRegularExpression(pattern: pattern),
      let match = regex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text))
    else { return nil }
    return (1..<match.numberOfRanges).compactMap { index in
      Range(match.range(at: index), in: text).map { String(text[$0]) }
    }
  }
}
