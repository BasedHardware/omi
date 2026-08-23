import Foundation

/// Pure adapters from local Rewind metadata into the shared trigger observation contract.
///
/// This boundary deliberately reads only metadata already present on ``Screenshot``. It does
/// not inspect image/video storage and has no scheduling, persistence, network, or activation
/// responsibility; a future caller may decide when (or whether) to evaluate the observation.
enum KnowledgeLedgerTriggerObservationAdapter {
  static let maxSelectorCharacters = 120

  static func fromRewindScreenshot(_ screenshot: Screenshot) -> KnowledgeLedgerTriggerObservation {
    KnowledgeLedgerTriggerObservation(
      eventID: screenshot.id.map(String.init),
      text: String((screenshot.ocrText ?? "").prefix(KnowledgeLedgerTriggerObservation.maxTextCharacters)),
      appName: boundedSelector(screenshot.appName),
      windowTitle: boundedSelector(screenshot.windowTitle),
      occurredAt: screenshot.timestamp
    )
  }

  private static func boundedSelector(_ value: String?) -> String? {
    guard let value else { return nil }
    let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !normalized.isEmpty else { return nil }
    return String(normalized.prefix(maxSelectorCharacters))
  }
}
