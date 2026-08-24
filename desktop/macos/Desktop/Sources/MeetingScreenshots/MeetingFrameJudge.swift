//
//  MeetingFrameJudge.swift — the adjudication call, and the enforcement the model does not do.
//
//  **This is a prototype stand-in, and the shape of it matters more than the transport.** In the
//  shipping design the adjudicator is a backend route that canonicalises the bytes, judges those
//  exact bytes, and mints a signed one-use approval; the client never decides what may be stored.
//  Here it is a loopback sidecar and nothing is stored anywhere, so the trust question does not
//  arise — but the *contract* is kept identical so the client half does not have to be rewritten
//  when the server half lands: the client sends candidates, the adjudicator returns verdicts, and
//  the client cannot manufacture a publish decision.
//
//  Four enforcement rules live here rather than in the prompt, because each of them was measured
//  being violated by the model on real frames:
//
//  1. **A publish cap in a prompt is advice.** Told "at most six", the model published 8 of 8,
//     14 of 16 and 23 of 25. The cap is applied to its output.
//  2. **Sensitivity is a veto, not a field.** The model returned `sensitive` and `publish` on the
//     same frame, twice. Anything not explicitly clean is dropped, whatever it decided.
//  3. **The banner must be something that survived.** Once the cap was enforced, the model's
//     chosen banner turned out to have been trimmed out of the published set.
//  4. **Order is not trust.** A verdict naming an id that was never sent is discarded.
//

import Foundation

// MARK: - Wire types

struct MeetingFrameVerdict: Sendable, Equatable {
  enum Decision: String, Sendable { case publish, reject }
  enum Sensitivity: String, Sendable { case clean, sensitive }

  let frameID: Int64
  let decision: Decision
  let sensitivity: Sensitivity
  let caption: String
  let labels: [String]
  let reason: String
}

struct MeetingFrameAdjudication: Sendable, Equatable {
  var published: [MeetingFrameVerdict] = []
  var bannerFrameID: Int64?
  /// What enforcement had to correct after the model answered. Surfaced in the diagnostics panel
  /// because a gate whose corrections are invisible is a gate that looks like it is not needed.
  var corrections: [String] = []
  var modelPublishedCount = 0
}

enum MeetingFrameJudgeError: Error, LocalizedError {
  case sidecarUnavailable
  case badResponse(String)

  var errorDescription: String? {
    switch self {
    case .sidecarUnavailable:
      return "The screenshot judge is not running. Start it with tools/meeting-shots-sidecar.py."
    case .badResponse(let detail):
      return "The screenshot judge returned something unusable: \(detail)"
    }
  }
}

// MARK: - Client

actor MeetingFrameJudge {
  static let shared = MeetingFrameJudge()

  /// The loopback adjudicator. Overridable so a build can point at a real backend route without a
  /// code change once one exists.
  private var endpoint: URL {
    if let raw = ProcessInfo.processInfo.environment["OMI_MEETING_SHOTS_JUDGE_URL"],
      let url = URL(string: raw)
    {
      return url
    }
    return URL(string: "http://127.0.0.1:10247/v1/screen-frame-egress/adjudications")!
  }

  /// At most one banner plus six strip frames.
  static let publishCap = 6

  /// Rewind's Videos directory, once storage has finished opening.
  ///
  /// `RewindStorage.videosDirectory` is nil until `initialize()` runs, so reading it once races
  /// app launch: open a note early enough and the adjudicator is handed no path, decodes nothing,
  /// and returns an empty verdict list that reads as "the judge rejected everything". This is the
  /// same failure `SpineScreenIndex.poolWhenReady` exists to prevent for the database, and it is
  /// answered the same way -- poll briefly rather than cache a wrong answer for the session.
  static func videosDirectoryWhenReady(
    timeout: Duration = .seconds(20),
    pollInterval: Duration = .milliseconds(400)
  ) async -> URL? {
    var waited = Duration.zero
    while waited < timeout {
      if let directory = await RewindStorage.shared.getVideosDirectory() { return directory }
      try? await Task.sleep(for: pollInterval)
      waited += pollInterval
    }
    return nil
  }

  func adjudicate(
    candidates: [MeetingFrameCandidate],
    meetingTitle: String
  ) async throws -> MeetingFrameAdjudication {
    guard !candidates.isEmpty else { return MeetingFrameAdjudication() }

    var request = URLRequest(url: endpoint)
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    request.timeoutInterval = 120

    // The sidecar decodes the pixels itself from the local store, exactly as the shipping design
    // has the server canonicalise them: the client does not get to choose the bytes that are
    // judged. Here it names frames; there it uploads canonical bytes for judging.
    // Built element by element with explicit types. As one nested literal the type-checker takes
    // pathological time on it — the compiler says so out loud.
    let stamp = ISO8601DateFormatter()
    var wire: [[String: Any]] = []
    wire.reserveCapacity(candidates.count)
    for candidate in candidates {
      var entry: [String: Any] = [:]
      entry["id"] = NSNumber(value: candidate.id)
      entry["timestamp"] = stamp.string(from: candidate.timestamp)
      entry["app_name"] = candidate.appName
      entry["window_title"] = candidate.windowTitle ?? ""
      entry["video_chunk_path"] = candidate.videoChunkPath ?? ""
      entry["frame_offset"] = NSNumber(value: candidate.frameOffset ?? 0)
      entry["image_path"] = candidate.imagePath ?? ""
      wire.append(entry)
    }

    var payload: [String: Any] = [:]
    // Where the pixels actually are. The adjudicator must not have to guess a store location:
    // a named dev bundle keeps its capture under its own profile root, not under the stable or
    // beta app's, and a sidecar guessing from a hardcoded list silently decodes nothing and
    // reports "0 published" — indistinguishable from a judge that rejected everything.
    if let videos = await Self.videosDirectoryWhenReady() {
      payload["video_root"] = videos.path
    }
    payload["purpose"] = "meeting_note_v1"
    payload["meeting_title"] = meetingTitle
    payload["max_publish"] = NSNumber(value: Self.publishCap)
    payload["candidates"] = wire
    request.httpBody = try JSONSerialization.data(withJSONObject: payload)

    let data: Data
    do {
      let (body, response) = try await URLSession.shared.data(for: request)
      guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
        throw MeetingFrameJudgeError.badResponse(
          "status \((response as? HTTPURLResponse)?.statusCode ?? -1)")
      }
      data = body
    } catch let error as MeetingFrameJudgeError {
      throw error
    } catch {
      throw MeetingFrameJudgeError.sidecarUnavailable
    }

    guard let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      let rawVerdicts = root["verdicts"] as? [[String: Any]]
    else {
      throw MeetingFrameJudgeError.badResponse("not an adjudication document")
    }

    return Self.enforce(
      rawVerdicts: rawVerdicts,
      rawBanner: root["banner_id"] as? Int64 ?? (root["banner_id"] as? NSNumber)?.int64Value,
      sentIDs: Set(candidates.map(\.id)),
      order: candidates.map(\.id))
  }

  /// Everything the model is not trusted to have got right.
  static func enforce(
    rawVerdicts: [[String: Any]],
    rawBanner: Int64?,
    sentIDs: Set<Int64>,
    order: [Int64]
  ) -> MeetingFrameAdjudication {
    var result = MeetingFrameAdjudication()
    var parsed: [MeetingFrameVerdict] = []

    for raw in rawVerdicts {
      guard
        let id = (raw["id"] as? NSNumber)?.int64Value ?? raw["id"] as? Int64,
        sentIDs.contains(id)
      else {
        result.corrections.append("discarded a verdict for a frame that was never sent")
        continue
      }
      let decision = MeetingFrameVerdict.Decision(rawValue: raw["decision"] as? String ?? "") ?? .reject
      let sensitivity =
        MeetingFrameVerdict.Sensitivity(rawValue: raw["sensitivity"] as? String ?? "") ?? .sensitive
      parsed.append(
        MeetingFrameVerdict(
          frameID: id,
          decision: decision,
          sensitivity: sensitivity,
          caption: raw["caption"] as? String ?? "",
          labels: raw["labels"] as? [String] ?? [],
          reason: raw["reason"] as? String ?? ""))
    }

    let modelPublished = parsed.filter { $0.decision == .publish }
    result.modelPublishedCount = modelPublished.count

    // Rule 2 — sensitivity vetoes publication, whatever the decision said.
    let clean = modelPublished.filter { $0.sensitivity == .clean }
    if clean.count != modelPublished.count {
      result.corrections.append(
        "vetoed \(modelPublished.count - clean.count) frame(s) the judge marked sensitive but chose to publish")
    }

    // A model may name one frame more than once. Identity is authoritative: one captured frame can
    // occupy at most one publication slot.
    var seen = Set<Int64>()
    let unique = clean.filter { seen.insert($0.frameID).inserted }
    if unique.count != clean.count {
      result.corrections.append("discarded \(clean.count - unique.count) duplicate frame verdict(s)")
    }

    // Keep capture order so the strip reads as a timeline rather than as a ranking. Build the map
    // without a trapping unique-key initializer because `order` is an enforcement input too.
    var position: [Int64: Int] = [:]
    for (index, id) in order.enumerated() where position[id] == nil {
      position[id] = index
    }
    var ordered = unique.sorted {
      let left = position[$0.frameID] ?? .max
      let right = position[$1.frameID] ?? .max
      return left == right ? $0.frameID < $1.frameID : left < right
    }

    // Rule 1 — the cap is applied, not requested.
    if ordered.count > publishCap {
      result.corrections.append(
        "trimmed \(ordered.count - publishCap) frame(s) over the cap of \(publishCap)")
      ordered = Array(ordered.prefix(publishCap))
    }
    result.published = ordered

    // Rule 3 — a banner must be a frame that actually survived all of the above.
    if let rawBanner, ordered.contains(where: { $0.frameID == rawBanner }) {
      result.bannerFrameID = rawBanner
    } else if rawBanner != nil {
      result.corrections.append("dropped a banner the judge chose that is not in the published set")
      result.bannerFrameID = nil
    }

    return result
  }
}
