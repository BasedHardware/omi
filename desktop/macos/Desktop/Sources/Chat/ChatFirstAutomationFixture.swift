import Foundation

/// Deterministic, non-content fixture facts used by the named Chat-first
/// bundle. This is deliberately a contract probe, not a second production
/// state store: it exposes no IDs, titles, question text, prepared answers,
/// transcripts, or tool manifests. The harness validates actual raw manifests
/// out of process, where byte identity can be compared to the frozen fixture.
enum ChatFirstAutomationFixture {
  enum Scenario: String, CaseIterable, Sendable {
    case interactiveQuestion = "interactive_question"
    case deferredQuestion = "deferred_question"
    case mixedCapture = "mixed_capture"
    case uiFlagOff = "ui_flag_off"
    case outOfCohort = "out_of_cohort"
  }

  struct Contract: Equatable, Sendable {
    let validRichBlockCount: Int
    let hasValidQuestion: Bool
    let hasPreparedAnswer: Bool
    let fakeClockEpochSeconds: Int
    let deferralSeconds: Int
    let captureSourceMode: String
    let proactiveJudgeCalls: Int
    let proactiveEmissions: Int
    let materializationCount: Int
    let rawManifestProofMode: String
    let shellVariant: String
    let chatFirstToolCount: Int

    var bridgeDetail: [String: String] {
      [
        "valid_rich_block_count": "\(validRichBlockCount)",
        "has_valid_question": hasValidQuestion ? "true" : "false",
        "has_prepared_answer": hasPreparedAnswer ? "true" : "false",
        "fake_clock_epoch_seconds": "\(fakeClockEpochSeconds)",
        "deferral_seconds": "\(deferralSeconds)",
        "capture_source_mode": captureSourceMode,
        "proactive_judge_calls": "\(proactiveJudgeCalls)",
        "proactive_emissions": "\(proactiveEmissions)",
        "materialization_count": "\(materializationCount)",
        "raw_manifest_proof_mode": rawManifestProofMode,
        "shell_variant": shellVariant,
        "chat_first_tool_count": "\(chatFirstToolCount)",
      ]
    }
  }

  static func contract(for scenario: Scenario) -> Contract {
    switch scenario {
    case .interactiveQuestion:
      return Contract(
        validRichBlockCount: 1,
        hasValidQuestion: true,
        hasPreparedAnswer: true,
        fakeClockEpochSeconds: 1_784_347_200,
        deferralSeconds: 0,
        captureSourceMode: "none",
        proactiveJudgeCalls: 0,
        proactiveEmissions: 0,
        materializationCount: 0,
        rawManifestProofMode: "external_raw_bytes_digest",
        shellVariant: "chatFirst",
        chatFirstToolCount: 2
      )
    case .deferredQuestion:
      return Contract(
        validRichBlockCount: 1,
        hasValidQuestion: true,
        hasPreparedAnswer: true,
        fakeClockEpochSeconds: 1_784_347_200,
        deferralSeconds: 86_400,
        captureSourceMode: "none",
        proactiveJudgeCalls: 0,
        proactiveEmissions: 0,
        materializationCount: 0,
        rawManifestProofMode: "external_raw_bytes_digest",
        shellVariant: "chatFirst",
        chatFirstToolCount: 2
      )
    case .mixedCapture:
      return Contract(
        validRichBlockCount: 1,
        hasValidQuestion: false,
        hasPreparedAnswer: false,
        fakeClockEpochSeconds: 1_784_347_200,
        deferralSeconds: 0,
        captureSourceMode: "mixed",
        proactiveJudgeCalls: 0,
        proactiveEmissions: 0,
        materializationCount: 0,
        rawManifestProofMode: "external_raw_bytes_digest",
        shellVariant: "chatFirst",
        chatFirstToolCount: 2
      )
    case .uiFlagOff, .outOfCohort:
      return Contract(
        validRichBlockCount: 0,
        hasValidQuestion: false,
        hasPreparedAnswer: false,
        fakeClockEpochSeconds: 1_784_347_200,
        deferralSeconds: 0,
        captureSourceMode: "none",
        proactiveJudgeCalls: 0,
        proactiveEmissions: 0,
        materializationCount: 0,
        rawManifestProofMode: "external_raw_bytes_digest",
        shellVariant: "legacy",
        chatFirstToolCount: 0
      )
    }
  }
}
