import Foundation

/// What to tell the reader about where a conversation's summary came from, and
/// what to say when there isn't one.
///
/// ## Why this exists
///
/// Free-tier conversations are summarized on the user's own Mac. Two gaps
/// followed from that and both are visible to a shipping user:
///
/// 1. **No attribution.** `ServerConversation.localSummary` carries the engine
///    that produced a summary, and until now nothing in the UI read it. A user
///    could not tell an on-device summary from a server one, which makes the
///    on-device claim unverifiable from inside the product.
/// 2. **A silent void.** `ConversationSummarySelection` already resolves to
///    `.empty`, and no view handled that case: `ConversationSummaryBody` fell
///    through to `OmiMarkdown(text: "")` and rendered nothing at all. A user
///    whose Mac could not summarize got a title followed by blank space, with
///    no statement that anything had happened or failed.
///
/// ## The claim this makes, and the claim it refuses to make
///
/// Attribution is **per conversation**, never per tier. "Processed on your
/// device" is not true as a blanket statement: `free_tier_processing_policy`
/// returns `process_normally` for every non-desktop source, so free mobile
/// conversations are summarized in the cloud today, and audio transcription is
/// a separate cloud path on every platform. A badge that reads the provenance
/// of the conversation in front of the reader is honest; a tier-level privacy
/// claim covering the same surface would not be.
///
/// Pure and view-free so the wording and the branching are testable without
/// mounting SwiftUI.
enum ConversationSummaryProvenanceState {
  /// Runtime values written by `ClientProcessingContract`. Compared as strings
  /// because the wire type is an open string, not an enum: an unrecognized
  /// runtime must read as "some engine" rather than crash or claim AFM.
  static let localRuntime = "local"
  static let deterministicRuntime = "deterministic"

  // MARK: - Attribution

  enum Attribution: Equatable {
    /// A model on this Mac wrote this summary.
    case onDevice
    /// No projection was selected; the server's own summary is being shown.
    case server

    /// Deliberately does not name the model. `provenance.model_id` is
    /// `"afm"` — an internal identifier, not a product name — and putting an
    /// unfamiliar acronym in front of a reader explains nothing. What a reader
    /// can act on is *where* it ran.
    var label: String {
      switch self {
      case .onDevice: return "Summarized on this Mac"
      case .server: return "Summarized by Omi"
      }
    }

    var systemImage: String {
      switch self {
      case .onDevice: return "laptopcomputer"
      case .server: return "cloud"
      }
    }

    /// Whether this attribution is worth the reader's attention.
    ///
    /// Server processing is what every user already assumes, so labelling it adds
    /// a row to every conversation in the product and tells nobody anything. The
    /// on-device case is the one that is both surprising and checkable, and it is
    /// the claim the free tier is making — so it is the one that gets shown.
    ///
    /// `attribution(…)` still reports the truth for both, because a policy that
    /// only models the case it displays cannot be asked about the other one.
    var isWorthDisplaying: Bool { self == .onDevice }
  }

  /// Attribution for a conversation that actually has a summary body.
  ///
  /// Returns `nil` when there is no body to attribute — an empty conversation
  /// gets an explanation instead, and badging emptiness as "summarized" anywhere
  /// would be the same dishonesty in a smaller font.
  static func attribution(
    localSummaryRuntime: String?,
    hasSummaryBody: Bool
  ) -> Attribution? {
    guard hasSummaryBody else { return nil }
    guard let runtime = localSummaryRuntime?.trimmingCharacters(in: .whitespacesAndNewlines),
      !runtime.isEmpty
    else { return .server }
    // The deterministic minimum is not a model's work and must not be badged as
    // on-device intelligence. It reaches here only if it somehow carried a body.
    return runtime == deterministicRuntime ? .server : .onDevice
  }

  // MARK: - Empty state

  enum Empty: Equatable {
    /// A capable client is expected to deliver a summary and has not yet.
    case pendingOnDevice
    /// The transcript is stored; enrichment happens when the conversation opens.
    case pendingServer
    /// A local engine ran or was asked to run and produced nothing usable.
    case localProducedNothing
    /// No local path was involved and there is still no summary.
    case unavailable

    var title: String {
      switch self {
      case .pendingOnDevice: return "Summarizing on this Mac"
      case .pendingServer: return "Summary not generated yet"
      case .localProducedNothing: return "No summary for this conversation"
      case .unavailable: return "No summary for this conversation"
      }
    }

    /// States what happened and what remains usable. Never apologises, never
    /// blames the user's hardware, and never implies a summary is coming when
    /// the state is terminal.
    var message: String {
      switch self {
      case .pendingOnDevice:
        return "This conversation is being summarized on your Mac. The transcript is already saved below."
      case .pendingServer:
        return "The transcript is saved. The summary is generated the first time you open this conversation."
      case .localProducedNothing:
        return
          "Your Mac finished without producing a summary for this one. The full transcript is saved below and is searchable."
      case .unavailable:
        return "This conversation has no summary. The full transcript is saved below and is searchable."
      }
    }
  }

  /// Which explanation to show in place of an empty summary body.
  ///
  /// `deferred` is the server's lazy-processing marker; `localSummaryRuntime` is
  /// the projection's own account of what ran. Order matters: a deferred
  /// conversation is pending regardless of what a previous local attempt did.
  static func empty(
    deferred: Bool,
    localSummaryRuntime: String?,
    isProcessing: Bool
  ) -> Empty {
    let runtime = localSummaryRuntime?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    if isProcessing {
      return runtime.isEmpty ? .pendingServer : .pendingOnDevice
    }
    if deferred { return .pendingServer }
    // Both local outcomes land here: an engine that could not run at all
    // (`deterministic`) and one that ran and returned nothing a reader would
    // call content (`local`, gated by `carriesContent`). The distinction matters
    // to us and not to the reader, who in both cases has a transcript and no summary.
    if !runtime.isEmpty { return .localProducedNothing }
    return .unavailable
  }
}
