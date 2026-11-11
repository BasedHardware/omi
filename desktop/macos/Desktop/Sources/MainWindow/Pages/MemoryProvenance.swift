import Foundation

/// One glanceable fact about where a memory came from.
struct MemoryProvenanceFact: Equatable, Identifiable {
  let icon: String
  let label: String

  var id: String { "\(icon)|\(label)" }
}

/// Resolves "where this came from" from the fields the memories API actually
/// sends.
///
/// The detail panel used to read `source`, `sourceApp`, `inputDeviceName` and
/// `confidence`. None of those exist on the server's memory model — they are
/// desktop-local fields on `ServerMemory` that decode to nil for every synced
/// memory — so the section rendered as a bare timestamp even for memories whose
/// origin was well known. What the server does send is the capture device and
/// an `app:<name>` tag, which is what this resolves first. The local-only
/// fields stay as fallbacks so a memory captured on this Mac before its first
/// round-trip still describes itself.
enum MemoryProvenance {
  static let appTagPrefix = "app:"

  static func facts(for memory: ServerMemory, deviceLabel: String?) -> [MemoryProvenanceFact] {
    var facts: [MemoryProvenanceFact] = []

    if let deviceLabel, !deviceLabel.isEmpty {
      facts.append(MemoryProvenanceFact(icon: deviceIcon(for: deviceLabel), label: deviceLabel))
    } else if let sourceName = memory.sourceName {
      facts.append(MemoryProvenanceFact(icon: memory.sourceIcon, label: sourceName))
    }

    if let app = appName(for: memory) {
      facts.append(MemoryProvenanceFact(icon: "app.dashed", label: app))
    }

    if memory.manuallyAdded {
      facts.append(MemoryProvenanceFact(icon: "hand.point.up.left", label: "Added by you"))
    }

    if let micName = memory.inputDeviceName, !micName.isEmpty {
      facts.append(MemoryProvenanceFact(icon: "mic", label: micName))
    }

    if let confidence = memory.confidenceString {
      facts.append(MemoryProvenanceFact(icon: "gauge.medium", label: "\(confidence) confidence"))
    }

    return facts
  }

  /// The capturing app, carried as an `app:<name>` tag rather than a field.
  ///
  /// "Unknown" and "Unknown Application/Browser" are values the extractor emits
  /// when it could not tell; naming them tells the user nothing and reads as a
  /// worse answer than the honest absence of one.
  static func appName(for memory: ServerMemory) -> String? {
    if let sourceApp = memory.sourceApp, !sourceApp.isEmpty { return sourceApp }
    for tag in memory.tags where tag.hasPrefix(appTagPrefix) {
      let name = String(tag.dropFirst(appTagPrefix.count))
        .trimmingCharacters(in: .whitespacesAndNewlines)
      guard !name.isEmpty, !name.lowercased().hasPrefix("unknown") else { continue }
      return name
    }
    return nil
  }

  private static func deviceIcon(for label: String) -> String {
    switch label {
    case "This Mac", "Mac": return "laptopcomputer"
    case "iPhone": return "iphone"
    case "Android": return "candybarphone"
    default: return "desktopcomputer"
    }
  }
}
