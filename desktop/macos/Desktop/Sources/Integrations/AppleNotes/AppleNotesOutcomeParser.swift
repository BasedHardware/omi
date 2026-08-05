import Foundation

/// One manifest row: the stable note key plus the modification timestamp the
/// incremental diff compares against.
struct AppleNotesManifestEntry: Sendable, Equatable {
  let key: String
  let modifiedAt: Date
}

/// A parsed full-body export.
struct AppleNotesSnapshot: Sendable, Equatable {
  enum FolderMode: String, Sendable, Equatable, Codable {
    case mapped
    case skipped
  }

  let notes: [AppleNoteRecord]
  let lockedSkipped: Int
  let folderMode: FolderMode
}

/// Pure translation of script stdout/stderr into domain values.
///
/// No I/O, no process launching, no clock. Same role as `CalendarOutcomeParser`:
/// every payload shape and every Apple Event failure code can be exercised from
/// a captured fixture, so classification is not entangled with automation.
enum AppleNotesOutcomeParser {
  // MARK: - Payload parsing

  static func parseManifest(_ data: Data) -> Result<[AppleNotesManifestEntry], AppleNotesReaderError> {
    switch decodeEnvelope(data) {
    case .failure(let error):
      return .failure(error)
    case .success(let envelope):
      let entries = envelope.notes.compactMap { note -> AppleNotesManifestEntry? in
        guard let id = note["id"] as? String, !id.isEmpty else { return nil }
        return AppleNotesManifestEntry(
          key: AppleNotesSyncState.noteKey(fromAppleScriptID: id),
          modifiedAt: date(from: note["modifiedAt"])
        )
      }
      return .success(entries)
    }
  }

  static func parse(_ data: Data, maxBodyChars: Int) -> Result<AppleNotesSnapshot, AppleNotesReaderError> {
    switch decodeEnvelope(data) {
    case .failure(let error):
      return .failure(error)
    case .success(let envelope):
      let bodyCap = max(maxBodyChars, 1)
      let folderMode = resolvedFolderMode(envelope.folderMode)
      let notes = envelope.notes.compactMap { note -> AppleNoteRecord? in
        guard let id = note["id"] as? String, !id.isEmpty else { return nil }
        let rawBody = note["body"] as? String ?? ""
        // Defense in depth: the script already caps the body, but a stale
        // helper or an unexpectedly generous export must not push an unbounded
        // string into an import batch or an LLM prompt.
        let overLimit = rawBody.count > bodyCap
        let body = overLimit ? String(rawBody.prefix(bodyCap)) : rawBody
        let modifiedAt = date(from: note["modifiedAt"])
        return AppleNoteRecord(
          id: AppleNotesSyncState.noteKey(fromAppleScriptID: id),
          title: note["title"] as? String ?? "",
          body: body,
          bodyTruncated: overLimit || (note["truncated"] as? Bool ?? false),
          folder: folderMode == .mapped ? (note["folder"] as? String) : nil,
          createdAt: date(from: note["createdAt"], default: modifiedAt),
          modifiedAt: modifiedAt
        )
      }
      return .success(
        AppleNotesSnapshot(
          notes: notes,
          lockedSkipped: max(envelope.lockedSkipped, 0),
          folderMode: folderMode
        )
      )
    }
  }

  // MARK: - Failure classification

  /// Maps `osascript` failure output onto the reader's error space. Apple Event
  /// codes are the authority here — the text around them is localized and must
  /// not be matched.
  static func classify(stderr: String, terminationStatus: Int32) -> AppleNotesReaderError {
    if stderr.contains("-1743") {
      return .automationPermissionDenied
    }
    if stderr.contains("-1744") {
      return .automationPermissionUndetermined
    }
    if stderr.contains("-2700") || stderr.contains("-600") {
      return .notesAppUnavailable
    }
    let detail = stderr.trimmingCharacters(in: .whitespacesAndNewlines)
    if detail.isEmpty {
      return .readFailed(reason: "osascript exited with status \(terminationStatus)")
    }
    return .readFailed(reason: String(detail.prefix(200)))
  }

  /// Counts and modes only — never a title, a body, or a folder name. This line
  /// goes to the local log and the diagnostics attachment.
  static func diagnosticsLine(_ snapshot: AppleNotesSnapshot) -> String {
    let truncated = snapshot.notes.filter(\.bodyTruncated).count
    return
      "notes=\(snapshot.notes.count) locked_skipped=\(snapshot.lockedSkipped) "
      + "truncated=\(truncated) folder_mode=\(snapshot.folderMode.rawValue)"
  }

  // MARK: - Private

  private struct Envelope {
    let notes: [[String: Any]]
    let lockedSkipped: Int
    let folderMode: String?
  }

  private static func decodeEnvelope(_ data: Data) -> Result<Envelope, AppleNotesReaderError> {
    guard !data.isEmpty else {
      return .failure(.malformedResponse(reason: "empty script output"))
    }
    guard
      let object = try? JSONSerialization.jsonObject(with: data),
      let payload = object as? [String: Any]
    else {
      return .failure(.malformedResponse(reason: "script output was not a JSON object"))
    }
    if let scriptError = payload["error"] as? String, !scriptError.isEmpty {
      // A concurrent Notes edit shifted the parallel bulk arrays. Surfacing it
      // as a retryable read failure is the whole point of the script's
      // first/last id integrity guard — the alternative is silently mismatched
      // titles and bodies.
      return .failure(.readFailed(reason: scriptError))
    }
    let schema = payload["schema"] as? Int ?? -1
    guard schema == AppleNotesScript.schemaVersion else {
      return .failure(.malformedResponse(reason: "unsupported payload schema \(schema)"))
    }
    guard let notes = payload["notes"] as? [[String: Any]] else {
      return .failure(.malformedResponse(reason: "payload is missing a notes array"))
    }
    return .success(
      Envelope(
        notes: notes,
        lockedSkipped: payload["lockedSkipped"] as? Int ?? 0,
        folderMode: payload["folderMode"] as? String
      )
    )
  }

  private static func resolvedFolderMode(_ raw: String?) -> AppleNotesSnapshot.FolderMode {
    raw.flatMap(AppleNotesSnapshot.FolderMode.init(rawValue:)) ?? .skipped
  }

  private nonisolated(unsafe) static let fractionalFormatter: ISO8601DateFormatter = {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return formatter
  }()

  private nonisolated(unsafe) static let plainFormatter: ISO8601DateFormatter = {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime]
    return formatter
  }()

  private static func date(from value: Any?, default fallback: Date = Date(timeIntervalSince1970: 0)) -> Date {
    guard let text = value as? String, !text.isEmpty else { return fallback }
    return fractionalFormatter.date(from: text) ?? plainFormatter.date(from: text) ?? fallback
  }
}
