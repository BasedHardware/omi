import Foundation
@preconcurrency import GRDB

/// PostHog selects the serving cohort; absent/non-boolean values keep the old path.
enum ClientRefactorFlags {
  static let clientsFlag = "clients_refactor"
  static let chunksFlag = "clients_from_segments_chunks"
  static let boundaryFlag = "clients_boundary_evidence"
  @MainActor static var serving: Bool { enabled(clientsFlag) }
  @MainActor static var chunks: Bool { enabled(chunksFlag) }
  @MainActor static var boundaryEvidence: Bool { enabled(boundaryFlag) }
  @MainActor static func enabled(_ key: String) -> Bool {
    PostHogManager.shared.getFeatureFlag(key) as? Bool == true
  }
}

struct ResolvedSpeakerLabel: Equatable, Sendable {
  let isUser: Bool
  let personID: String?
  let retracted: Bool

  init(personID: String?, isUser: Bool?, retracted: Bool) {
    self.retracted = retracted
    self.isUser = !retracted && (isUser ?? (personID == "user"))
    self.personID = retracted || self.isUser || personID?.isEmpty != false ? nil : personID
  }

  var liveMapValue: String? { retracted ? nil : isUser ? "user" : personID }
  func apply(to segment: SpeakerSegment) -> SpeakerSegment {
    var result = segment
    result.isUser = isUser
    result.personId = personID
    return result
  }
}

/// Backend identity is the only safe join key after re-segmentation.
enum ServerSegmentLabelMerge {
  static func merge(_ incoming: TranscriptionSegmentRecord, existing: TranscriptionSegmentRecord?)
    -> TranscriptionSegmentRecord
  {
    guard let existing, let id = incoming.segmentId, id == existing.segmentId,
      existing.hasSpeakerAssignment,
      existing.speakerLabelSource == "manual" || !incoming.hasSpeakerAssignment
    else { return incoming }
    var record = incoming
    record.isUser = existing.isUser
    record.personId = existing.personId
    record.speakerLabelSource = existing.speakerLabelSource
    return record
  }
}

func addingSpeakerLabelSourceMigration(_ original: DatabaseMigrator) -> DatabaseMigrator {
  var migrator = original
  migrator.registerMigration("v20261022_speaker_label_source") { db in
    try db.alter(table: "transcription_segments") { t in t.add(column: "speakerLabelSource", .text) }
  }
  return migrator
}
