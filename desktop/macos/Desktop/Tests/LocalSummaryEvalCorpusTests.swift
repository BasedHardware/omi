import Foundation
import XCTest

@testable import Omi_Computer

/// Guards the evaluation corpus against the defect that invalidated the first one.
///
/// The previous corpus padded three authored turns to length with a single
/// template, so ~98% of every transcript was one repeated sentence. Numbers
/// measured against it read as a model capability ceiling and were not one — a
/// model that described the repetition was summarizing it correctly and scored
/// as a failure, and the labelled facts appeared ~50 times each, so "recall"
/// measured copying rather than summarization.
///
/// These are cheap, hermetic assertions that run in CI with no model. They exist
/// so the corpus cannot quietly rot back into a generator: a future change that
/// pads to length will fail here rather than several weeks later in a verdict.
final class LocalSummaryEvalCorpusTests: XCTestCase {
  /// The windows we actually select. A corpus pinned to one of them mislabels
  /// the other, so length classes are asserted against both ends.
  private let smallestSelectedWindow = 4096
  private let largestSelectedWindow = 8192

  // MARK: - Non-degeneracy

  func testNoTranscriptRepeatsAnyUtterance() {
    for scenario in LocalSummaryEvalCorpus.scenarios {
      let texts = scenario.turns.map(\.text)
      let unique = Set(texts)
      XCTAssertEqual(
        unique.count,
        texts.count,
        """
        \(scenario.id) repeats \(texts.count - unique.count) utterance(s) verbatim. \
        Length must come from authored content, never from repeating a line — that is \
        precisely how the first corpus became 98% boilerplate.
        """
      )
    }
  }

  /// Lexical diversity over the whole transcript. A template-padded transcript
  /// collapses this because the same words recur every line.
  func testTranscriptsAreLexicallyDiverse() {
    for scenario in LocalSummaryEvalCorpus.scenarios {
      let words =
        scenario.turns
        .flatMap { $0.text.lowercased().split(separator: " ") }
        .map(String.init)
      guard words.count > 50 else { continue }
      let ratio = Double(Set(words).count) / Double(words.count)
      XCTAssertGreaterThan(
        ratio,
        0.22,
        """
        \(scenario.id) has a type-token ratio of \(String(format: "%.3f", ratio)). \
        The generated corpus scored far below this; natural meeting dialogue of this \
        length sits well above it.
        """
      )
    }
  }

  /// No single phrase may dominate a transcript. Catches a padding template even
  /// when its substitutions make each line technically unique — which is exactly
  /// what the old generator produced.
  func testNoPhraseDominatesATranscript() {
    for scenario in LocalSummaryEvalCorpus.scenarios {
      var counts: [String: Int] = [:]
      var total = 0
      for turn in scenario.turns {
        let words = turn.text.lowercased().split(separator: " ").map(String.init)
        guard words.count >= 6 else { continue }
        for start in 0...(words.count - 6) {
          counts[words[start..<(start + 6)].joined(separator: " "), default: 0] += 1
          total += 1
        }
      }
      guard total > 0, let (phrase, count) = counts.max(by: { $0.value < $1.value }) else { continue }
      let share = Double(count) / Double(total)
      XCTAssertLessThan(
        share,
        0.02,
        """
        \(scenario.id): the phrase "\(phrase)" accounts for \(String(format: "%.1f%%", share * 100)) \
        of all six-word sequences. A dominant phrase means the transcript was padded \
        from a template rather than authored.
        """
      )
    }
  }

  /// A labelled fact repeated throughout the transcript turns recall into a
  /// copying test. In the generated corpus each fact appeared roughly fifty times.
  func testLabelsAreNotRepeatedThroughoutTheTranscript() {
    for scenario in LocalSummaryEvalCorpus.scenarios {
      for label in scenario.mustKeepFacts + scenario.labelledActionItems {
        let hits = scenario.turns.filter {
          LocalSummaryEvalCorpus.containment(label: label, produced: $0.text)
            >= LocalSummaryEvalCorpus.matchThreshold
        }.count
        XCTAssertLessThanOrEqual(
          hits,
          3,
          """
          \(scenario.id): "\(label)" is stated in \(hits) separate turns. A label repeated \
          throughout means the metric measures copying, not summarization.
          """
        )
      }
    }
  }

  /// Every label must actually be supported by the transcript, or the corpus is
  /// scoring models against something that was never said.
  func testEveryLabelIsSupportedByTheTranscript() {
    for scenario in LocalSummaryEvalCorpus.scenarios {
      for label in scenario.mustKeepFacts + scenario.labelledActionItems {
        let supported = scenario.turns.contains {
          LocalSummaryEvalCorpus.containment(label: label, produced: $0.text) >= 0.5
        }
        XCTAssertTrue(
          supported,
          "\(scenario.id): no turn supports the label \"\(label)\". A label the transcript never states is unmeasurable."
        )
      }
    }
  }

  /// Banned facts must genuinely be absent, or a hallucination counter counts
  /// correct recall as a hallucination.
  /// Checked per turn, not against the concatenated transcript.
  ///
  /// Containment over a whole transcript is trivially satisfied: a three-word
  /// banned phrase scores 1.0 as soon as its words appear anywhere across
  /// thousands of turns, however unrelated. A claim is something a speaker said,
  /// so support means *one turn* supports it.
  func testBannedFactsAreAbsentFromTheTranscript() {
    for scenario in LocalSummaryEvalCorpus.scenarios {
      for banned in scenario.hallucinatedIfPresent {
        let supporting = scenario.turns.filter {
          LocalSummaryEvalCorpus.containment(label: banned, produced: $0.text)
            >= LocalSummaryEvalCorpus.matchThreshold
        }
        XCTAssertTrue(
          supporting.isEmpty,
          """
          \(scenario.id): the banned claim "\(banned)" is supported by a turn \
          ("\(supporting.first?.text ?? "")"), so counting it as a hallucination would \
          penalise a model for correct recall.
          """
        )
      }
    }
  }

  // MARK: - Length classes

  func testLengthClassesHoldAgainstBothSelectedWindows() {
    let wrapper = ConversationChunkSummarizer.estimatedTokens(
      ConversationChunkSummarizer.mapPrompt("", index: 1, total: 1)
    )
    let reserve = ConversationChunkSummarizer.completionReserveTokens

    for scenario in LocalSummaryEvalCorpus.scenarios {
      let tokens = scenario.estimatedTokens
      switch scenario.lengthClass {
      case .single:
        XCTAssertLessThan(
          tokens,
          smallestSelectedWindow - wrapper - reserve,
          "\(scenario.id) is declared .single but does not fit the smallest window we select; it would chunk."
        )
      case .medium:
        XCTAssertGreaterThan(tokens, 0, "\(scenario.id) is empty")
      case .long:
        XCTAssertGreaterThan(
          tokens,
          largestSelectedWindow,
          """
          \(scenario.id) is declared .long at \(tokens) estimated tokens but does not exceed the \
          largest window we select (\(largestSelectedWindow)). It would run as a single pass on AFM, \
          so the reduce pass — the stage that always runs on real conversations and the one the \
          summarizer fixes target — would go unmeasured.
          """
        )
      }
    }
  }

  func testCorpusCoversEveryLengthClass() {
    for lengthClass in LocalSummaryEvalCorpus.LengthClass.allCases {
      let count = LocalSummaryEvalCorpus.scenarios.filter { $0.lengthClass == lengthClass }.count
      XCTAssertGreaterThanOrEqual(
        count,
        2,
        "length class \(lengthClass.rawValue) has \(count) scenario(s); a class with one scenario cannot distinguish a finding from an accident."
      )
    }
  }

  // MARK: - Scoring

  func testContainmentToleratesParaphraseButRejectsANameAlone() {
    let label = "Priya will cut the release notes by Friday"
    XCTAssertTrue(
      LocalSummaryEvalCorpus.matches(label: label, produced: "Priya: release notes, Friday"),
      "a compressed restatement is what a summary looks like and must not score as a miss"
    )
    XCTAssertTrue(
      LocalSummaryEvalCorpus.matches(label: label, produced: "Release notes are Priya's, due Friday"),
      "reordering and possessives must not score as a miss"
    )
    XCTAssertFalse(
      LocalSummaryEvalCorpus.matches(label: label, produced: "Priya joined the call"),
      "sharing only a name must not score as a match"
    )
    XCTAssertFalse(
      LocalSummaryEvalCorpus.matches(label: label, produced: "The team discussed several topics"),
      "a contentless sentence must not score as a match"
    )
  }

  func testContainmentIsAsymmetric() {
    // A long summary that contains the label scores; a bare label against a long
    // summary must not be penalised for the summary's extra words.
    let label = "the outage started at 09:12 UTC"
    let produced = "The gateway outage started at 09:12 UTC and lasted roughly forty minutes before recovery."
    XCTAssertTrue(LocalSummaryEvalCorpus.matches(label: label, produced: produced))
  }
}
