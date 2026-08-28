//
//  ScreenFrameEgressWireTypes.swift — the shapes both sides of the network agreed on.
//
//  Mirrors `data/reports/meeting-screenshots/CONTRACT.md` §2 field for field, including its
//  snake_case wire names. **This file has no logic in it on purpose.** Any judgement about what
//  is safe to store belongs to the server (§0); the client's only job with these types is to
//  describe a candidate honestly and decode whatever the server decided to persist.
//

import Foundation

// MARK: - Request (client -> server)

/// What is being adjudicated for. Only `"conversation"` exists today.
struct ScreenFrameSubjectWire: Encodable, Sendable, Equatable {
  let kind: String
  let id: String
}

/// One candidate frame, canonical bytes and all. `sha256Base64` is a transport check only —
/// the contract is explicit that the server re-derives its own digest over the decoded bytes
/// and that digest, not this one, is what any later approval is bound to.
struct ScreenFrameCandidateWire: Encodable, Sendable, Equatable {
  let clientFrameID: String
  let capturedAt: Date
  let mimeType: String
  let declaredWidth: Int
  let declaredHeight: Int
  let sha256Base64: String
  let bytesBase64: String

  enum CodingKeys: String, CodingKey {
    case clientFrameID = "client_frame_id"
    case capturedAt = "captured_at"
    case mimeType = "mime_type"
    case declaredWidth = "declared_width"
    case declaredHeight = "declared_height"
    case sha256Base64 = "sha256_base64"
    case bytesBase64 = "bytes_base64"
  }
}

/// The body of `POST /v1/screen-frame-egress/adjudications`. `schemaVersion` is fixed at 1 —
/// pinned in code, not derived, so a future breaking wire change is a deliberate edit here.
struct ScreenFrameAdjudicationRequestWire: Encodable, Sendable, Equatable {
  static let schemaVersion = 1
  static let purpose = "meeting_note_v1"

  let schemaVersion: Int
  let attemptID: UUID
  let purpose: String
  let subject: ScreenFrameSubjectWire
  let candidates: [ScreenFrameCandidateWire]

  enum CodingKeys: String, CodingKey {
    case schemaVersion = "schema_version"
    case attemptID = "attempt_id"
    case purpose, subject, candidates
  }

  init(
    attemptID: UUID = UUID(),
    subjectID: String,
    candidates: [ScreenFrameCandidateWire]
  ) {
    self.schemaVersion = Self.schemaVersion
    self.attemptID = attemptID
    self.purpose = Self.purpose
    self.subject = ScreenFrameSubjectWire(kind: "conversation", id: subjectID)
    self.candidates = candidates
  }
}

/// The body of both `GET` and `PATCH /v1/screen-frame-egress/settings` — the account-level gate
/// admission checks read (contract §6). Desktop mirrors this into `UserDefaults`
/// (`DefaultsKey.meetingNoteScreenshotsEnabled`) as an offline cache so the feature gate and the
/// Settings toggle are never blocked on the network, but this is the value that is actually true,
/// shared across every device.
struct ScreenFrameSettingsWire: Codable, Sendable, Equatable {
  let meetingNoteScreenshotsEnabled: Bool

  enum CodingKeys: String, CodingKey {
    case meetingNoteScreenshotsEnabled = "meeting_note_screenshots_enabled"
  }
}

// MARK: - Response (server -> client)

/// A focal region, normalised 0...1 so it survives being drawn at any size.
struct NormalizedRect: Codable, Sendable, Equatable {
  let x: Double
  let y: Double
  let width: Double
  let height: Double
}

/// The banner gradient's two stops, computed once server-side over the canonical bytes at
/// approval time — see `models/screen_frame.py::ScreenFrameGround` and
/// `utils/screen_frames/palette.py` (a port of `MeetingBannerPalette.swift`). Both this client and
/// web render their banner gradient from this value rather than each re-deriving it from pixels,
/// so the two surfaces can never drift apart.
struct ScreenFrameGroundWire: Codable, Sendable, Equatable {
  /// Exactly two "#RRGGBB" strings, top-leading and bottom-trailing.
  let stops: [String]
  /// True when the frame carried no usable colour and `stops` is the server's neutral fallback.
  let isNeutral: Bool

  enum CodingKeys: String, CodingKey {
    case stops
    case isNeutral = "is_neutral"
  }
}

/// One persisted frame. Its pixels are not here — `contentURL`/`thumbnailURL` are signed GCS
/// URLs, good for `urlExpiresAt` (60 minutes per the contract), after which a caller must
/// re-fetch the set rather than retry the same URL.
struct ConversationScreenFrame: Codable, Sendable, Equatable, Identifiable {
  let id: String
  let capturedAt: Date
  let role: String
  let rank: Int
  let caption: String
  let labels: [String]
  let sourceBadge: String?
  let focalRegion: NormalizedRect?
  let width: Int
  let height: Int
  let contentURL: String
  let thumbnailURL: String
  let urlExpiresAt: Date
  /// Optional purely as defensive decoding — the backend model declares this required, and every
  /// frame the server persists carries one (falling back to its own neutral ground rather than
  /// omitting the field on a decode failure; see `compute_ground` in `palette.py`). Absent only if
  /// a client ever decodes a response from a server build that predates this field.
  let ground: ScreenFrameGroundWire?

  enum CodingKeys: String, CodingKey {
    case id
    case capturedAt = "captured_at"
    case role, rank, caption, labels
    case sourceBadge = "source_badge"
    case focalRegion = "focal_region"
    case width, height
    case contentURL = "content_url"
    case thumbnailURL = "thumbnail_url"
    case urlExpiresAt = "url_expires_at"
    case ground
  }
}

/// Everything a conversation currently has to show — at most one banner plus up to six strip
/// frames, already capped, already ordered, already the only survivors of the server's own
/// enforcement (contract §7). The client draws exactly this; it does not re-derive any of it.
struct ConversationScreenFrameSet: Codable, Sendable, Equatable {
  let revision: Int
  let banner: ConversationScreenFrame?
  let strip: [ConversationScreenFrame]
  /// When an adjudication pass last ran for this conversation, whatever it decided.
  ///
  /// This — not `revision` — is how a caller knows whether to offer candidates at all. `revision`
  /// only moves when something was approved, so an all-rejected pass leaves it at 0 and is
  /// indistinguishable from never having tried. Optional because a record written before the
  /// server carried this field has none.
  let adjudicatedAt: Date?

  enum CodingKeys: String, CodingKey {
    case revision
    case banner
    case strip
    case adjudicatedAt = "adjudicated_at"
  }

  static let empty = ConversationScreenFrameSet(
    revision: 0, banner: nil, strip: [], adjudicatedAt: nil)

  var isEmpty: Bool { banner == nil && strip.isEmpty }
}

/// The body of `POST /v1/screen-frame-egress/adjudications`'s response. `outcome` is informational
/// only — a `"no_approved_frames"` outcome and a `"committed"` outcome with an empty `frameSet`
/// render identically (nothing), so callers do not need to branch on it.
struct ScreenFrameAdjudicationResponseWire: Decodable, Sendable, Equatable {
  let attemptID: UUID
  let outcome: String
  let frameSet: ConversationScreenFrameSet

  enum CodingKeys: String, CodingKey {
    case attemptID = "attempt_id"
    case outcome
    case frameSet = "frame_set"
  }
}
