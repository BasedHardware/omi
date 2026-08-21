import Foundation

enum ContextBucketsFeature {
  static let flagName = "context_buckets"
  /// Remote stop for the beta channel. Inverted on purpose: absent, unresolved, and false
  /// all mean "run the pipeline", so only an explicit true switches it off.
  static let killSwitchFlagName = "context_buckets_kill"
  private static let localQAOverrideName = "OMI_FORCE_CONTEXT_BUCKETS"

  /// PostHog feature flags fail closed while unavailable or uninitialized, so the
  /// production default is exactly today's behavior.
  ///
  /// Non-production bundles do not consult PostHog at all. They used to require
  /// `OMI_FORCE_CONTEXT_BUCKETS=1` in the launch environment, but that is read from
  /// `ProcessInfo` at runtime, so any relaunch that does not go through `run.sh` —
  /// opening the bundle from Finder, or macOS restoring it after a permission grant —
  /// silently dropped it. Capture kept running with the bucket pipeline disabled, which
  /// is indistinguishable from the feature simply never firing. Dev bundles exist to
  /// exercise this pipeline, so they default to on and the variable now only turns it off.
  @MainActor static var isEnabled: Bool {
    if AppBuild.isNonProduction {
      return ProcessInfo.processInfo.environment[localQAOverrideName] != "0"
    }
    // The bucket pipeline is a beta-channel surface; stable stays on the fallback
    // assistants. That split is enforced here, on bundle identity, rather than through
    // a PostHog release condition on `update_channel`. The channel reaches PostHog as a
    // super property via `register(...)`, so it rides events but only lands on the person
    // record when `identify` runs — measured across 14 days of macOS clients, 215 of ~260
    // beta installs had a null person-side channel and 11 reported `stable`, so
    // person-property targeting resolved for roughly a sixth of the channel. Bundle
    // identity is exact and available before any network call.
    //
    // Enablement does not consult `context_buckets` either, because that flag inherits the
    // same problem from the other side: its audience can only be described with a static
    // cohort or the unreliable person property, so a *newly installed* beta client matches
    // neither and would silently get nothing. PostHog rejects behavioral cohorts in flag
    // targeting, so there is no server-side expression of "is running the beta build" that
    // stays correct as users arrive. Bundle identity already answers that question exactly.
    //
    // What remains useful remotely is the ability to stop the pipeline, so beta reads only
    // the kill switch, and reads it fail-open: an unreachable or uninitialized PostHog must
    // not switch the dogfood channel off by accident. Stable is gated out above, so this
    // default cannot reach it.
    guard AppBuild.isBetaProductionBundle else { return false }
    return !PostHogManager.shared.isFeatureEnabled(killSwitchFlagName)
  }

  /// Groups browser tabs of one website into a single bucket instead of one bucket
  /// per tab title.
  ///
  /// Separate from `isEnabled` and separately stoppable: this is the only path that
  /// can make two different reference hashes share a bucket, so it needs its own
  /// remote stop that does not take the whole pipeline down with it. Same inverted
  /// fail-open semantics as the pipeline kill switch.
  @MainActor static var isDestinationRoutingEnabled: Bool {
    guard isEnabled else { return false }
    if AppBuild.isNonProduction {
      return ProcessInfo.processInfo.environment[localDestinationOverrideName] != "0"
    }
    return !PostHogManager.shared.isFeatureEnabled(destinationKillSwitchFlagName)
  }

  static let destinationKillSwitchFlagName = "context_buckets_destination_kill"
  private static let localDestinationOverrideName = "OMI_FORCE_BUCKET_DESTINATIONS"

  /// Lets the director spend one bounded retrieval hop (a second model call over
  /// conversation/memory search results) when its first response asks for one.
  ///
  /// Separate from `isEnabled` and separately stoppable: this is the only path
  /// that doubles the per-visit director cost and the only one that quotes
  /// cross-bucket history into a director prompt, so it needs a remote stop that
  /// does not take the whole pipeline down with it. Same inverted fail-open
  /// semantics as the other kill switches. With the flag off, the director's
  /// schema, prompt, and single-call flow are byte-identical to today.
  @MainActor static var isRetrievalHopEnabled: Bool {
    guard isEnabled else { return false }
    if AppBuild.isNonProduction {
      return ProcessInfo.processInfo.environment[localRetrievalOverrideName] != "0"
    }
    return !PostHogManager.shared.isFeatureEnabled(retrievalKillSwitchFlagName)
  }

  static let retrievalKillSwitchFlagName = "context_buckets_retrieval_kill"
  private static let localRetrievalOverrideName = "OMI_FORCE_BUCKET_RETRIEVAL"

  /// Evaluates a departed bucket immediately when its departure extraction just
  /// validated a notify-worthy fact, grounded on the departing frame, instead
  /// of waiting for the next revisit's dwell.
  ///
  /// Non-production dogfood defaults to on with the same inverted env override
  /// as the pipeline flag (`OMI_FORCE_DEPARTURE_EVALUATION=0` turns it off).
  /// Beta reads only a kill switch, fail-open, matching the retrieval hop:
  /// the departure path is the only evaluation that sees content the user
  /// created during the visit (a content-refresh transition hands the typed
  /// question to extraction, and this is what acts on it), so leaving it dark
  /// on beta left answer-delivery structurally unreachable there. Stable is
  /// gated out by `isEnabled`.
  @MainActor static var isDepartureEvaluationEnabled: Bool {
    guard isEnabled else { return false }
    if AppBuild.isNonProduction {
      return ProcessInfo.processInfo.environment[localDepartureEvaluationOverrideName] != "0"
    }
    return !PostHogManager.shared.isFeatureEnabled(departureEvaluationKillSwitchFlagName)
  }

  /// The keyboard-triggered dwell refresh (ContextDwellRefreshPolicy): its own
  /// remote stop because it multiplies evaluation volume (each refresh buys a
  /// departure extraction + departure evaluation + entry evaluation, plus a
  /// possible forced retrieval), so it must be stoppable without taking the
  /// whole pipeline down. Same inverted fail-open semantics as the flags above.
  @MainActor static var isDwellRefreshEnabled: Bool {
    guard isEnabled else { return false }
    if AppBuild.isNonProduction {
      return ProcessInfo.processInfo.environment[localDwellRefreshOverrideName] != "0"
    }
    return !PostHogManager.shared.isFeatureEnabled(dwellRefreshKillSwitchFlagName)
  }

  static let dwellRefreshKillSwitchFlagName = "context_buckets_dwell_refresh_kill"
  private static let localDwellRefreshOverrideName = "OMI_FORCE_DWELL_REFRESH"

  static let departureEvaluationKillSwitchFlagName = "context_buckets_departure_eval_kill"
  private static let localDepartureEvaluationOverrideName = "OMI_FORCE_DEPARTURE_EVALUATION"

  /// Quotes quality-gated validated facts from sibling buckets of the visit's
  /// live workstream into the director's volatile prompt, and widens delivery
  /// dedup to that workstream.
  ///
  /// Non-production dogfood defaults to on with the same inverted env override
  /// as the flags above (`OMI_FORCE_BUCKET_WORKSTREAMS=0` turns it off).
  /// Production and beta stay off until pooling is validated in dogfood — like
  /// departure evaluation there is deliberately no remote stop yet, because
  /// nothing ships dark to users this way.
  @MainActor static var isWorkstreamPoolingEnabled: Bool {
    guard isEnabled else { return false }
    if AppBuild.isNonProduction {
      return ProcessInfo.processInfo.environment[localWorkstreamPoolingOverrideName] != "0"
    }
    return false
  }

  private static let localWorkstreamPoolingOverrideName = "OMI_FORCE_BUCKET_WORKSTREAMS"

  /// Background workstream tagging plus pre-written notification candidates,
  /// with a small reasoning-lane gate on the delivery path instead of a full
  /// director call when a candidate is armed.
  ///
  /// Non-production dogfood defaults to on with the same inverted env override
  /// as the flags above (`OMI_FORCE_BUCKET_CANDIDATES=0` turns it off).
  /// Production and beta stay off until the reconciler is validated in
  /// dogfood — like workstream pooling there is deliberately no remote stop
  /// yet, because nothing ships dark to users this way.
  @MainActor static var isProactiveCandidatesEnabled: Bool {
    guard isEnabled else { return false }
    if AppBuild.isNonProduction {
      return ProcessInfo.processInfo.environment[localProactiveCandidatesOverrideName] != "0"
    }
    return false
  }

  private static let localProactiveCandidatesOverrideName = "OMI_FORCE_BUCKET_CANDIDATES"

  /// Deterministic write-time fact policy (`ContextFactWritePolicy`): drops
  /// extraction-machinery echoes, caps scenery statements to worthiness 0 so
  /// they can never arm a candidate, and floors named-person speech-act facts
  /// to arming eligibility (nano scores that class 0.0 in 8 of 9 measured).
  ///
  /// Non-production dogfood defaults to on with the same inverted env override
  /// as the flags above (`OMI_FORCE_FACT_WRITE_POLICY=0` turns it off).
  /// Beta reads only a kill switch, fail-open: departure evaluation triggers on
  /// a fact validated at or above the worthiness threshold, and the speech-act
  /// floor in this policy is what lifts "the user asked X for Y" facts (nano
  /// scores that class 0.0 in 8 of 9 measured) over that threshold — enabling
  /// departure evaluation on beta without this floor would fire it almost
  /// never. Stable is gated out by `isEnabled`.
  @MainActor static var isFactWritePolicyEnabled: Bool {
    guard isEnabled else { return false }
    if AppBuild.isNonProduction {
      return ProcessInfo.processInfo.environment[localFactWritePolicyOverrideName] != "0"
    }
    return !PostHogManager.shared.isFeatureEnabled(factWritePolicyKillSwitchFlagName)
  }

  static let factWritePolicyKillSwitchFlagName = "context_buckets_fact_write_policy_kill"
  private static let localFactWritePolicyOverrideName = "OMI_FORCE_FACT_WRITE_POLICY"
}
