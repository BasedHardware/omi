import Foundation

/// Captures bounded text evidence for files the user selected for a typed chat
/// turn. The local path is used only while reading the selected file; it is
/// never copied into the evidence sent to the kernel or backend.
enum ChatAttachmentEvidence {
  private struct AttachmentSnapshot: Sendable {
    let id: String
    let fileName: String
    let mimeType: String
    let serverId: String?
    let localPath: String?
  }

  private struct ReadResult: Sendable {
    let data: Data
    let wasTruncated: Bool
  }

  /// Reads each selected attachment away from the main actor. The caller
  /// awaits this before admitting the journal exchange, so the resulting
  /// evidence is part of the initial user row rather than a later patch.
  static func capture(
    attachments: [ChatAttachment],
    capturedAt: Date = Date()
  ) async -> [ConversationEvidence] {
    guard !attachments.isEmpty else { return [] }

    let snapshots = attachments.map { attachment in
      AttachmentSnapshot(
        id: attachment.id,
        fileName: attachment.fileName,
        mimeType: attachment.mimeType,
        serverId: attachment.serverId,
        localPath: attachment.localFileURL?.isFileURL == true
          ? attachment.localFileURL?.path
          : nil
      )
    }
    let capturedAtMs = max(0, Int(capturedAt.timeIntervalSince1970 * 1_000))

    return await Task.detached(priority: .utility) {
      snapshots.map {
        Self.evidence(for: $0, capturedAtMs: capturedAtMs)
      }
    }.value
  }

  private static func evidence(
    for attachment: AttachmentSnapshot,
    capturedAtMs: Int
  ) -> ConversationEvidence {
    var provenance = [
      "source": "typed_attachment",
      "attachment_id": attachment.id,
      "filename": attachment.fileName,
      "mime_type": attachment.mimeType,
    ]
    if let serverId = attachment.serverId, !serverId.isEmpty {
      provenance["server_id"] = serverId
    }
    let base = ConversationEvidenceBase(
      id: "attachment:\(attachment.id)",
      title: attachment.fileName,
      capturedAtMs: capturedAtMs,
      provenance: provenance
    )

    guard isSupportedTextMIME(attachment.mimeType), let localPath = attachment.localPath else {
      return base.make(
        availability: .unavailable,
        extractionCompleteness: .none
      )
    }

    guard let readResult = read(localPath: localPath),
      let bodyText = decodeUTF8(readResult.data, wasTruncated: readResult.wasTruncated),
      !bodyText.isEmpty
    else {
      return base.make(
        availability: .unavailable,
        extractionCompleteness: .none
      )
    }

    return base.make(
      availability: readResult.wasTruncated ? .partial : .available,
      extractionCompleteness: readResult.wasTruncated ? .partial : .complete,
      bodyText: bodyText
    )
  }

  private struct ConversationEvidenceBase: Sendable {
    let id: String
    let title: String
    let capturedAtMs: Int
    let provenance: [String: String]

    func make(
      availability: ConversationEvidenceAvailability,
      extractionCompleteness: ConversationEvidenceExtractionCompleteness,
      bodyText: String? = nil
    ) -> ConversationEvidence {
      ConversationEvidence(
        id: id,
        kind: .attachment,
        title: title,
        capturedAtMs: capturedAtMs,
        availability: availability,
        extractionCompleteness: extractionCompleteness,
        bodyText: bodyText,
        provenance: provenance
      )
    }
  }

  private static func isSupportedTextMIME(_ mimeType: String) -> Bool {
    let normalized =
      mimeType
      .split(separator: ";", maxSplits: 1, omittingEmptySubsequences: true)
      .first
      .map(String.init)?
      .trimmingCharacters(in: .whitespacesAndNewlines)
      .lowercased()
    return ["text/plain", "application/json", "text/csv", "text/html"].contains(normalized)
  }

  private static func read(localPath: String) -> ReadResult? {
    do {
      let attributes = try FileManager.default.attributesOfItem(atPath: localPath)
      guard attributes[.type] as? FileAttributeType == .typeRegular else { return nil }
      let handle = try FileHandle(forReadingFrom: URL(fileURLWithPath: localPath, isDirectory: false))
      defer { try? handle.close() }
      let data = try handle.read(upToCount: ConversationEvidence.maxBodyBytes + 1) ?? Data()
      return ReadResult(
        data: Data(data.prefix(ConversationEvidence.maxBodyBytes)),
        wasTruncated: data.count > ConversationEvidence.maxBodyBytes
      )
    } catch {
      return nil
    }
  }

  /// Trimming only occurs for a long file whose bound cuts through a UTF-8
  /// scalar. Files within the byte bound are returned byte-for-byte losslessly.
  private static func decodeUTF8(_ data: Data, wasTruncated: Bool) -> String? {
    if let text = String(data: data, encoding: .utf8) {
      return text
    }
    guard wasTruncated else { return nil }
    let maximumRepairBytes = min(3, data.count)
    guard maximumRepairBytes > 0 else { return nil }
    for repairBytes in 1...maximumRepairBytes {
      let candidate = data.dropLast(repairBytes)
      if let text = String(data: Data(candidate), encoding: .utf8) {
        return text
      }
    }
    return nil
  }
}
