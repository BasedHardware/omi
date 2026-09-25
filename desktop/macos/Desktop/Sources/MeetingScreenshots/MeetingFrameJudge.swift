//
//  MeetingFrameJudge.swift — hands candidate bytes to the real adjudicator, and nothing else.
//
//  **The client never decides what may be stored (contract §0).** This type uploads canonical
//  candidate bytes to `POST /v1/screen-frame-egress/adjudications` and returns whatever
//  `ConversationScreenFrameSet` the server hands back. There is exactly one method,
//  `adjudicateAndCommit`, and it returns DTOs — never a verdict, never anything shaped like an
//  approval. The four enforcement rules that used to live in this file (publish cap, sensitivity
//  veto, survivor-only banner, capture-order sort) are gone: they are the server's job now
//  (contract §7), because they were measured being violated on the *server's* copy of the model's
//  raw output, not the client's, and the client was never the place to re-check server work.
//
//  What is still this file's job: reading the candidate's local pixels (never AppKit — `Data`
//  and `ImageIO` only, so nothing non-`Sendable` has to cross the actor boundary to
//  `RewindStorage`), computing the transport-check digest, and staying under the wire's
//  `max_candidates` of 8 even if a selection tuning change ever drifts from the purpose registry.
//

import CryptoKit
import Foundation
import ImageIO

actor MeetingFrameJudge {
  static let shared = MeetingFrameJudge()

  /// Contract §3: `max_candidates=8` for `meeting_note_v1`. `MeetingFrameSelector.candidateCeiling`
  /// is kept equal to this so nothing is normally trimmed here — this is a defensive floor, not
  /// the primary enforcement point.
  static let maxCandidatesPerRequest = 8

  enum MeetingFrameJudgeError: Error, LocalizedError, Equatable {
    /// None of the selected candidates had pixels this process could still read (a chunk aged
    /// out between selection and upload, or a zero-byte abandoned chunk). Normal, not a bug.
    case noReadablePixels

    var errorDescription: String? {
      switch self {
      case .noReadablePixels:
        return "None of this meeting's candidate frames still had readable pixels."
      }
    }
  }

  /// Upload every candidate's canonical bytes and commit whatever the server approves.
  ///
  /// - Parameters:
  ///   - candidates: On-device-selected frames (`MeetingFrameSelector`). Privacy denylisting and
  ///     dedup have already run; this only decides which of *those* survivors can still be read.
  ///   - subjectID: The conversation these frames belong to.
  func adjudicateAndCommit(
    candidates: [MeetingFrameCandidate],
    subjectID: String
  ) async throws -> ConversationScreenFrameSet {
    guard !candidates.isEmpty else { return .empty }
    let bounded =
      candidates.count > Self.maxCandidatesPerRequest
      ? Array(candidates.prefix(Self.maxCandidatesPerRequest))
      : candidates

    var wire: [ScreenFrameCandidateWire] = []
    wire.reserveCapacity(bounded.count)
    for candidate in bounded {
      guard
        let bytes = try? await RewindStorage.shared.loadScreenshotData(for: candidate.moment.screenshot),
        let entry = Self.makeCandidateWire(
          id: candidate.id, timestamp: candidate.timestamp, bytes: bytes)
      else { continue }
      wire.append(entry)
    }
    guard !wire.isEmpty else { throw MeetingFrameJudgeError.noReadablePixels }

    let request = ScreenFrameAdjudicationRequestWire(subjectID: subjectID, candidates: wire)
    let response = try await APIClient.shared.adjudicateScreenFrames(request)
    return response.frameSet
  }

  // MARK: - Pure helpers (testable without a network or an actor hop)

  /// Build one wire candidate from a frame's raw bytes, or `nil` when the bytes cannot even be
  /// sniffed for a size — malformed data is dropped here rather than sent to fail server-side.
  static func makeCandidateWire(id: Int64, timestamp: Date, bytes: Data) -> ScreenFrameCandidateWire? {
    guard !bytes.isEmpty, let size = pixelSize(of: bytes) else { return nil }
    let digest = SHA256.hash(data: bytes)
    return ScreenFrameCandidateWire(
      clientFrameID: String(id),
      capturedAt: timestamp,
      mimeType: mimeType(of: bytes),
      declaredWidth: size.width,
      declaredHeight: size.height,
      sha256Base64: Data(digest).base64EncodedString(),
      bytesBase64: bytes.base64EncodedString())
  }

  /// Sniff by magic bytes rather than trust the storage path's extension — `loadScreenshotData`
  /// re-encodes video-backed frames to JPEG but passes legacy on-disk images through unchanged,
  /// and the wire type only accepts the two MIME types Pillow's canonicaliser reads.
  static func mimeType(of bytes: Data) -> String {
    let pngSignature: [UInt8] = [0x89, 0x50, 0x4E, 0x47]
    if bytes.count >= pngSignature.count, bytes.prefix(pngSignature.count).elementsEqual(pngSignature) {
      return "image/png"
    }
    return "image/jpeg"
  }

  /// Pixel dimensions via ImageIO's header parse — never decodes the image, so nothing here
  /// touches AppKit or crosses an isolation boundary as anything richer than `Data`.
  static func pixelSize(of bytes: Data) -> (width: Int, height: Int)? {
    guard let source = CGImageSourceCreateWithData(bytes as CFData, nil),
      let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
      let width = properties[kCGImagePropertyPixelWidth] as? Int,
      let height = properties[kCGImagePropertyPixelHeight] as? Int,
      width > 0, height > 0
    else { return nil }
    return (width, height)
  }
}
