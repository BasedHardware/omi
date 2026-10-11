import Foundation

@testable import Omi_Computer

/// Engine-neutral evaluation corpus for the local conversation summarizer.
///
/// ## Why this replaces the generated corpus
///
/// The first version of this corpus authored three plot turns per scenario and
/// then padded to length with a template:
///
/// ```
/// "On walkthrough round \(n) we restated \(fact). The open action remains: \(action)."
/// ```
///
/// Reaching a 4096-token window from three short turns took ~150 of those, so
/// **~98% of every transcript was one sentence with two substitutions**. Two
/// consequences, both of which corrupted the measurement it was built for:
///
/// 1. A model that summarized such a transcript *correctly* would say the
///    speakers restated the same facts repeatedly. That is an accurate summary
///    of a degenerate transcript, and it scored as a meta-overview failure.
/// 2. Facts and actions appeared verbatim ~50 times each, so retention and
///    recall measured whether a model could copy a sentence it had just seen
///    fifty times, not whether it could summarize a meeting.
///
/// Numbers taken against it are withdrawn. This corpus is **fully authored**:
/// every turn is written, nothing is generated, and `LocalSummaryEvalCorpusTests`
/// fails the build if repetition creeps back in.
///
/// ## Shape
///
/// Real conversations are not uniform in length, and a corpus built exclusively
/// to force map+reduce measures only the tail. Scenarios are spread across three
/// length classes so single-pass and chunked paths are both exercised, and so
/// the chunked result can be compared against the single-pass one.
///
/// Labels (`labelledActionItems`, `mustKeepFacts`, `hallucinatedIfPresent`) were
/// written with each scenario, before any model output.
enum LocalSummaryEvalCorpus {
  struct Turn: Sendable, Equatable {
    var speaker: String
    var text: String

    init(_ speaker: String, _ text: String) {
      self.speaker = speaker
      self.text = text
    }
  }

  /// How long the transcript is relative to the engine's context window.
  ///
  /// Resolved against the *selected engine's* window at run time rather than a
  /// constant, because AFM (8192) and a bundled small model (4096) disagree, and
  /// a corpus pinned to one of them mislabels the other.
  enum LengthClass: String, Sendable, CaseIterable {
    /// Comfortably inside any window we select. No map pass.
    case single
    /// Inside a large window, chunked on a small one. The interesting middle.
    case medium
    /// Exceeds every window we select. Always map+reduce.
    case long
  }

  struct Scenario: Sendable {
    var id: String
    var lengthClass: LengthClass
    /// Commitments a competent summary should surface. Scored by content-word
    /// containment, not substring, so paraphrase is not counted as a miss.
    var labelledActionItems: [String]
    /// Facts that must survive into the final overview or sections. On a chunked
    /// run these are the reduce pass's job.
    var mustKeepFacts: [String]
    /// Plausible-sounding claims the transcript never makes.
    var hallucinatedIfPresent: [String]
    var turns: [Turn]

    func segments() -> [TranscriptHash.Segment] {
      turns.map { TranscriptHash.Segment(speaker: $0.speaker, text: $0.text) }
    }

    var estimatedTokens: Int {
      ConversationChunkSummarizer.estimatedTokens(
        ConversationChunkSummarizer.plainTranscript(segments())
      )
    }
  }

  // MARK: - Shared topic blocks

  /// Coherent sub-discussions, each with its own specifics, reused across the
  /// long scenarios in different subsets and orders.
  ///
  /// Reuse **across** scenarios is deliberate and harmless: each transcript is
  /// still internally non-repeating, which is the property that was broken.
  /// Reuse *within* one transcript is what the invariant test forbids.
  struct TopicBlock: Sendable {
    var id: String
    var turns: [Turn]
  }

  static let blockOnCallRotation = TopicBlock(
    id: "on-call-rotation",
    turns: [
      Turn("SPEAKER_00", "Before we move on, the on-call rotation for next month still has two open weeks."),
      Turn("SPEAKER_02", "I can take the week of the eleventh. I'm not travelling then."),
      Turn("SPEAKER_01", "That leaves the week of the twenty-fifth, which is the holiday week, so nobody wants it."),
      Turn("SPEAKER_00", "We could split it. Two people at half a week each, and neither carries the whole thing."),
      Turn("SPEAKER_02", "Splitting handoffs is how we missed the pager last quarter. I'd rather one person own it."),
      Turn("SPEAKER_01", "Then it should rotate to whoever had the lightest month, and that's Dana by a wide margin."),
      Turn("SPEAKER_00", "Dana isn't here. I'll ask rather than volunteer her in absentia."),
      Turn("SPEAKER_02", "Fine. If she says no we draw lots, and I'll accept the outcome without arguing it again."),
      Turn("SPEAKER_01", "One more thing — the escalation policy still pages the old team alias, which nobody reads."),
      Turn("SPEAKER_00", "That's a five minute fix and it has been open for three weeks. I'll do it after this call."),
    ]
  )

  static let blockVendorContract = TopicBlock(
    id: "vendor-contract",
    turns: [
      Turn("SPEAKER_01", "The observability vendor came back on renewal. They want a eighteen percent increase."),
      Turn("SPEAKER_00", "On what basis? Our ingest volume is flat year over year, if anything slightly down."),
      Turn(
        "SPEAKER_01", "They're repricing the retention tier. Thirty days used to be included, now it's a line item."),
      Turn("SPEAKER_02", "We don't query anything past seven days except during incident review, and that's rare."),
      Turn("SPEAKER_00", "Then we should buy seven days hot and archive the rest to cold storage ourselves."),
      Turn("SPEAKER_02", "The archive path isn't free either. Someone has to build the rehydration tooling."),
      Turn("SPEAKER_01", "It's maybe two weeks of work against a recurring cost, so it pays back inside a quarter."),
      Turn("SPEAKER_00", "Get both numbers in writing before we decide. I don't want to argue this from memory."),
      Turn("SPEAKER_02", "Their contact also floated a multi-year lock for a discount. I'd be careful there."),
      Turn("SPEAKER_01", "Agreed, we've been burned by that. A multi-year on a tool we might replace is a trap."),
    ]
  )

  static let blockOnboardingMetrics = TopicBlock(
    id: "onboarding-metrics",
    turns: [
      Turn("SPEAKER_00", "The onboarding funnel numbers came in and the drop is not where we assumed."),
      Turn(
        "SPEAKER_02", "We thought it was the permissions screen. It isn't — that one converts at ninety-one percent."),
      Turn("SPEAKER_01", "Where does it actually fall over? I've been telling people it was permissions for a month."),
      Turn("SPEAKER_02", "The step after. People grant permission, then sit on the empty state and never record."),
      Turn("SPEAKER_00", "So the problem is that an empty app doesn't tell you what to do with it."),
      Turn("SPEAKER_01", "That's a content problem more than a design problem. The screen isn't broken, it's silent."),
      Turn("SPEAKER_02", "A sample conversation would fix it, but then we're shipping fake data in a privacy product."),
      Turn("SPEAKER_00", "Not fake. Prompt them to record thirty seconds of themselves and process that one properly."),
      Turn("SPEAKER_01", "That's better. It's their own data and it demonstrates the thing in one step."),
      Turn("SPEAKER_02", "I'll mock it this week. It's a small enough change that we can test it quickly."),
    ]
  )

  static let blockSupportBacklog = TopicBlock(
    id: "support-backlog",
    turns: [
      Turn("SPEAKER_01", "Support backlog is at two hundred and ten open tickets, up from one forty last month."),
      Turn("SPEAKER_00", "Is that volume or throughput? Those need different answers and we keep conflating them."),
      Turn("SPEAKER_01", "Mostly volume. Incoming is up about forty percent, resolution rate is roughly unchanged."),
      Turn("SPEAKER_02", "Forty percent of what, though? If half of it is one bug we should just fix the bug."),
      Turn("SPEAKER_01", "It isn't one bug. The top cluster is about a third and it's all sync-related complaints."),
      Turn("SPEAKER_00", "Sync complaints usually mean something upstream regressed and nobody noticed."),
      Turn("SPEAKER_02", "Or it means our sync status UI is unclear and people report working behaviour as broken."),
      Turn("SPEAKER_01", "Both are true. I read forty of them and about half were genuinely confused, not broken."),
      Turn("SPEAKER_00", "Then the fix is partly a status indicator, which is much cheaper than a sync rewrite."),
      Turn("SPEAKER_02", "Let's not scope a rewrite off a ticket count. Read the other hundred first."),
    ]
  )

  static let blockHiringPipeline = TopicBlock(
    id: "hiring-pipeline",
    turns: [
      Turn("SPEAKER_00", "Two candidates cleared the loop this week and we owe both an answer by Thursday."),
      Turn("SPEAKER_02", "The second one was stronger on systems but weaker on the product conversation."),
      Turn("SPEAKER_01", "That's a training gap, not a capability gap. Systems depth is the harder thing to teach."),
      Turn("SPEAKER_02", "I'd agree if the role were pure infrastructure, but this one sits close to users."),
      Turn("SPEAKER_00", "How close? If they're reading support tickets weekly then product instinct matters a lot."),
      Turn("SPEAKER_01", "Weekly is the plan, but it's the plan for every role and it rarely survives contact."),
      Turn("SPEAKER_02", "Then let's be honest about the role before we decide, rather than after."),
      Turn("SPEAKER_00", "Fair. I'll rewrite the scope in one paragraph tonight and we vote on it tomorrow."),
      Turn("SPEAKER_01", "The first candidate also asked about remote policy and we gave two different answers."),
      Turn("SPEAKER_00", "That's embarrassing. One of us should own that answer and the rest of us repeat it."),
    ]
  )

  static let blockPerformanceRegression = TopicBlock(
    id: "performance-regression",
    turns: [
      Turn("SPEAKER_02", "Cold start went from one point one seconds to one point nine over the last three releases."),
      Turn("SPEAKER_00", "That's a big move to go unnoticed. Do we have per-release numbers or just the endpoints?"),
      Turn("SPEAKER_02", "Just endpoints, which is the actual problem. We measure it manually when someone complains."),
      Turn("SPEAKER_01", "So we can't attribute it. It could be one bad change or six mediocre ones."),
      Turn("SPEAKER_02", "My guess is the font loading, because the timing lines up with the typography work."),
      Turn("SPEAKER_00", "Guessing is how we spent two weeks on the wrong thing last time. Instrument it first."),
      Turn(
        "SPEAKER_01", "A startup trace on every build is maybe a day of CI work, and then we stop guessing forever."),
      Turn("SPEAKER_02", "I'll take that. It's more useful than the fix even if the fix turns out to be one line."),
      Turn("SPEAKER_00", "Set a budget too, so a regression fails the build rather than getting discovered quarterly."),
      Turn("SPEAKER_01", "One point two seconds as the ceiling. Generous today, and it stops the slow drift."),
    ]
  )

  static let blockDocumentationDebt = TopicBlock(
    id: "documentation-debt",
    turns: [
      Turn("SPEAKER_01", "Three people asked this week how to run the integration suite locally."),
      Turn("SPEAKER_00", "It's documented. The document is just wrong, which is worse than not existing."),
      Turn("SPEAKER_02", "It references a setup script we deleted in March and an environment variable we renamed."),
      Turn("SPEAKER_01", "Wrong documentation costs more than none, because people trust it and lose an hour."),
      Turn("SPEAKER_00", "Can we make the document executable so it can't drift? Run the steps in CI."),
      Turn("SPEAKER_02", "For setup instructions that mostly works. Prose around them still rots silently."),
      Turn("SPEAKER_01", "Then keep prose to a minimum and let the commands be the documentation."),
      Turn("SPEAKER_00", "I'd rather have six correct lines than two correct pages nobody finishes reading."),
      Turn("SPEAKER_02", "I'll rewrite it this week and delete the parts I can't verify by running them."),
      Turn("SPEAKER_01", "Delete aggressively. Anything you're unsure about is probably already wrong."),
    ]
  )

  static let blockPricingExperiment = TopicBlock(
    id: "pricing-experiment",
    turns: [
      Turn("SPEAKER_00", "The pricing test has been running eleven days and the result is not what we expected."),
      Turn("SPEAKER_01", "Conversion is flat between the two tiers, which means price wasn't the objection."),
      Turn("SPEAKER_02", "Or the sample is too small and we're reading noise as a finding, which we've done before."),
      Turn("SPEAKER_01", "Eleven days at this volume is about nine hundred per arm. That's not nothing."),
      Turn("SPEAKER_00", "It's not nothing but it's not conclusive either, especially for a flat result."),
      Turn("SPEAKER_02", "A flat result is still informative. It says stop optimizing price and go look elsewhere."),
      Turn("SPEAKER_01", "Where elsewhere? The next hypothesis was that the trial length is wrong."),
      Turn("SPEAKER_00", "Trial length is a much slower experiment. We'd be waiting a month for each arm."),
      Turn("SPEAKER_02", "Then run it, but start it now rather than after we finish arguing about this one."),
      Turn("SPEAKER_00", "Agreed. Let the pricing test run to two weeks and start the trial test in parallel."),
    ]
  )

  static let blockSecurityReview = TopicBlock(
    id: "security-review",
    turns: [
      Turn("SPEAKER_02", "The external review came back with four findings, one of which is genuinely serious."),
      Turn("SPEAKER_00", "Start with the serious one and we can triage the rest afterwards."),
      Turn("SPEAKER_02", "Session tokens don't rotate on privilege change, so an old token keeps its old scope."),
      Turn("SPEAKER_01", "How long is the window? If tokens are short-lived the practical exposure is small."),
      Turn("SPEAKER_02", "An hour. Small, but an hour of stale elevated scope is still a real finding."),
      Turn("SPEAKER_00", "Is the fix invasive? Rotating on scope change usually means touching the refresh path."),
      Turn("SPEAKER_02", "It touches refresh, yes, and refresh is the code nobody wants to touch."),
      Turn("SPEAKER_01", "Which is exactly why it has a finding against it. Avoidance compounds."),
      Turn("SPEAKER_00", "Schedule it properly rather than squeezing it in. A rushed auth change is worse."),
      Turn("SPEAKER_02", "The other three are low severity and I'd batch them into normal work, not a security push."),
    ]
  )

  static let blockRoadmapTradeoff = TopicBlock(
    id: "roadmap-tradeoff",
    turns: [
      Turn("SPEAKER_00", "We have room for two of the four things on the list, and everyone wants a different two."),
      Turn("SPEAKER_01", "Search is the one users ask for most often, by a factor of about three."),
      Turn("SPEAKER_02", "Asked-for and valuable aren't the same. People ask for search when navigation is bad."),
      Turn("SPEAKER_00", "That's a real point, but we've used it to justify not building search twice now."),
      Turn("SPEAKER_01", "And navigation got better both times and the search requests didn't go down."),
      Turn("SPEAKER_02", "Then I withdraw the objection. The evidence went against my argument, not for it."),
      Turn("SPEAKER_00", "Search and what else? The export work is small and unblocks two enterprise conversations."),
      Turn("SPEAKER_01", "Export is small only because we keep descoping it. The honest version isn't small."),
      Turn("SPEAKER_02", "Define the honest version in writing, then we pick with real numbers instead of vibes."),
      Turn("SPEAKER_00", "This week. I'd rather delay the decision than make it on a number we made up."),
    ]
  )

  static let blockTestFlakiness = TopicBlock(
    id: "test-flakiness",
    turns: [
      Turn("SPEAKER_01", "The suite failed four times yesterday and all four were the same two tests."),
      Turn("SPEAKER_02", "Those two have been flaky since spring. Everyone re-runs without looking anymore."),
      Turn("SPEAKER_00", "That's the real cost. A flaky suite trains people to ignore red, including real red."),
      Turn("SPEAKER_01", "Do we quarantine them or fix them? Quarantine has been the answer for four months."),
      Turn("SPEAKER_02", "Quarantine was supposed to be temporary and it became the permanent state."),
      Turn("SPEAKER_00", "Then delete them. An ignored test is worse than no test because it implies coverage."),
      Turn("SPEAKER_01", "They cover the reconnect path, which is genuinely worth covering."),
      Turn("SPEAKER_02", "Covering it badly isn't covering it. Delete and rewrite against a deterministic clock."),
      Turn("SPEAKER_00", "Rewrite, don't just delete. I want the gap visible if the rewrite doesn't happen."),
      Turn("SPEAKER_01", "File it as a blocking issue then, so it can't quietly fall off the list again."),
    ]
  )

  static let blockAccessibilityAudit = TopicBlock(
    id: "accessibility-audit",
    turns: [
      Turn("SPEAKER_02", "The accessibility pass found the transcript view is unusable with VoiceOver."),
      Turn("SPEAKER_00", "Unusable how? Missing labels, or the reading order being wrong, or both?"),
      Turn(
        "SPEAKER_02", "Reading order mostly. It reads timestamps before speakers, so every line starts with a number."),
      Turn(
        "SPEAKER_01", "That's a grouping fix rather than a rewrite. The elements exist, they're just ordered badly."),
      Turn("SPEAKER_00", "Any keyboard issues? Those tend to travel with reading-order problems."),
      Turn("SPEAKER_02", "Tab order skips the filter control entirely, so keyboard users can't reach it at all."),
      Turn("SPEAKER_01", "Both of those are small. It's the kind of thing that stays broken because nobody owns it."),
      Turn(
        "SPEAKER_00", "Then assign it rather than agreeing it's important and moving on, which is the usual pattern."),
      Turn("SPEAKER_02", "I'll take it. It's a day of work and I'd rather do it than discuss it again next month."),
      Turn("SPEAKER_01", "Add a check to the suite too, otherwise it regresses the next time the view changes."),
    ]
  )

  static let blockDataRetentionPolicy = TopicBlock(
    id: "data-retention-policy",
    turns: [
      Turn(
        "SPEAKER_00",
        "Priya, counsel signed a forty-five day cap for raw audio last Tuesday, yet the production retention table still lists ninety and the nightly job never flipped."
      ),
      Turn(
        "SPEAKER_01",
        "Omar priced that leftover window at roughly forty-two hundred a month, which looks small until you stack the transcript store sitting on the same invoice."
      ),
      Turn(
        "SPEAKER_02",
        "Lee, searchable text is what customers actually query. I would keep those twelve months even if the wav files leave earlier than anyone likes."
      ),
      Turn(
        "SPEAKER_00",
        "A Frankfurt erasure still takes eleven days because the wav path and the transcript path are separate tickets. That delay is the compliance failure, not the calendar."
      ),
      Turn(
        "SPEAKER_00",
        "California's clock is forty-five as well, so matching one number beats inventing a region matrix. I was wrong to defend ninety as a safety buffer."
      ),
      Turn(
        "SPEAKER_02",
        "Screen captures live in that bucket today. If we shorten audio and leave those, the hold has not shrunk. Dana raised exactly that in the counsel thread."
      ),
      Turn(
        "SPEAKER_01",
        "Then the job has to cover wav files, captures, and embeddings together, or the policy is theater. A spreadsheet that only describes the audio row fools nobody."
      ),
      Turn(
        "SPEAKER_02",
        "Legal hold is already a prefix in the bucket. We should not invent a second freeze just because the default shortens. The exception path works."
      ),
      Turn(
        "SPEAKER_00",
        "I drop the ninety-day fight. Cut raw media to forty-five, keep searchable text twelve months, and write the hold exception into the policy note before Friday."
      ),
      Turn(
        "SPEAKER_01",
        "Priya owns the table change. Omar, can you join the deletion paths so a Frankfurt request finishes in one pass instead of eleven calendar days?"
      ),
      Turn(
        "SPEAKER_02",
        "Yes. I will wire that join before Friday. Embeddings stay until we rehearse a restore, because rebuilding them from scratch is miserable and slow."
      ),
      Turn(
        "SPEAKER_00",
        "Lee still owes a written call on whether screen captures count as media or as notes. Until that sentence exists I refuse to flip production."
      ),
      Turn(
        "SPEAKER_01",
        "Leave captures unresolved if we must. The rest is set: forty-five on binaries, twelve months on text, hold prefix unchanged, deletion join by Friday."
      ),
      Turn(
        "SPEAKER_02",
        "I will park those four bullets in the counsel thread so nobody reopens ninety on Monday. If Lee answers on captures we amend the note once."
      ),
      Turn(
        "SPEAKER_00",
        "One caution remains. Shrinking the default does not skip a restore rehearsal against cold storage before a customer finds a hold they cannot open."
      ),
      Turn(
        "SPEAKER_01",
        "Schedule that rehearsal for next Wednesday, Omar, and copy Priya. If restore fails we delay the cut rather than discovering it from a lawyer."
      ),
    ]
  )

  static let blockMobileCrashTriage = TopicBlock(
    id: "mobile-crash-triage",
    turns: [
      Turn(
        "SPEAKER_01",
        "Android 1.8.4 is sitting at ninety-six point four crash-free, while iOS on the same build is ninety-nine point one. That gap is not a rounding error."
      ),
      Turn(
        "SPEAKER_00",
        "Crashlytics shows eight hundred forty NativeMethodException events inside the Opus encoder, almost all on Pixel 8 running Android 15. Sam, that is a narrow blast."
      ),
      Turn(
        "SPEAKER_02",
        "Narrow still ships. I want the Play staged rollout paused at twenty percent until we know whether 1.8.5 on Tuesday even contains a fix."
      ),
      Turn(
        "SPEAKER_01",
        "Mina mapped the cliff to the opus-android bump, one point three point one to one point four point zero, which landed in 1.8.4 and nowhere else."
      ),
      Turn(
        "SPEAKER_00",
        "Then yanking Play is cheaper than waiting. A Tuesday train that might contain a fix is not a plan if the encoder is throwing today."
      ),
      Turn(
        "SPEAKER_02",
        "Chris, I disagree with killing the whole 1.8.4 line. Zero point eight percent of sessions, one device family. Pinning the encoder back is enough."
      ),
      Turn(
        "SPEAKER_00",
        "A pin means a 1.8.4.1 on Friday, not a lecture about percentages. People who crash twice uninstall, and those reviews land before Tuesday."
      ),
      Turn(
        "SPEAKER_01",
        "I can cut 1.8.4.1 with the old encoder this afternoon. QA on Pixel 8 is the bottleneck, and we have two of those in the drawer."
      ),
      Turn(
        "SPEAKER_02",
        "Give the devices to QA tonight. If the pin is clean by Thursday noon, ship Friday. If it is not, then I will accept pausing Play."
      ),
      Turn(
        "SPEAKER_00",
        "Sam already drafted the Play halt. Mina, write the 1.8.4.1 store notes so review does not read as if we vanished overnight."
      ),
      Turn(
        "SPEAKER_00",
        "Those notes are mine. Moving Crashlytics onto Sentry mobile belongs in another meeting; mixing it with the encoder pin would bury the only urgent patch."
      ),
      Turn(
        "SPEAKER_02",
        "Leave Sentry for another meeting. The encoder pin is the only decision that changes user damage this week, and I was slow to admit that."
      ),
      Turn(
        "SPEAKER_00",
        "Decision: pause Play at twenty percent today, ship 1.8.4.1 Friday if QA signs the Pixel 8 pin, otherwise keep the halt through Tuesday's 1.8.5."
      ),
      Turn(
        "SPEAKER_01",
        "I still want a watch on Samsung foldables, because we have twelve similar stacks there without a clean repro. Do not close the ticket on Pixel alone."
      ),
      Turn(
        "SPEAKER_02",
        "Fair. Chris will keep the foldable bucket open. Everything else is the pin, the halt, and Friday, and I will stop arguing percentages."
      ),
    ]
  )

  static let blockLocalizationBacklog = TopicBlock(
    id: "localization-backlog",
    turns: [
      Turn(
        "SPEAKER_00",
        "German and Japanese are six weeks behind English in Crowdin, with four hundred twelve strings sitting in needs-review. That is a release risk, not a translation hobby."
      ),
      Turn(
        "SPEAKER_02",
        "Jordan, the Japanese honorifics broke because vendors mixed polite desu-masu with casual forms in the assistant replies. Readers notice that in the first sentence."
      ),
      Turn(
        "SPEAKER_01",
        "Ines wants a string freeze ten days before each train. Product still drops copy on Thursday for a Friday ship, so the freeze has never been real."
      ),
      Turn(
        "SPEAKER_01",
        "Then pick a freeze we will actually keep. Tuesday noon of ship week is late, but it is a time people can remember without a calendar bot."
      ),
      Turn(
        "SPEAKER_02",
        "Our in-house linguist is back on October third. Hiring a Japanese contractor for three weeks of overlap sounded smart until finance capped it at twelve hours."
      ),
      Turn(
        "SPEAKER_01",
        "Twelve hours will not unstick four hundred strings. I would rather skip Portuguese-Brazil this cycle than ship Japanese that addresses the user like a stranger."
      ),
      Turn(
        "SPEAKER_00",
        "Dana will hate skipping pt-BR, because the Sao Paulo trial starts the twentieth. She can hate it in writing. Broken Japanese is worse."
      ),
      Turn(
        "SPEAKER_02",
        "I changed my mind on the contractor. Twelve billed hours of a stranger will add inconsistency, not remove it. Jordan owns ja until October third."
      ),
      Turn(
        "SPEAKER_01",
        "I can own ja. Give me freeze authority at Tuesday noon, and I will reject late English rather than translating it badly overnight."
      ),
      Turn(
        "SPEAKER_00",
        "Authority granted. Ines, German gets the same noon cutoff, so we refuse to run two freeze cultures inside one train."
      ),
      Turn(
        "SPEAKER_02",
        "German is healthier; the backlog there is mostly review, not missing copy. I will still honor noon, and I will bounce Thursday heroics to the next train."
      ),
      Turn(
        "SPEAKER_01",
        "Document the skip for pt-BR in the launch checklist so sales does not promise it on the nineteenth. Silence is how that trial gets lied to."
      ),
      Turn(
        "SPEAKER_00",
        "Jordan writes that checklist line today. Crowdin review SLA is forty-eight hours for frozen strings, and anything past that ships English with a visible marker."
      ),
      Turn(
        "SPEAKER_02",
        "A visible marker in Japanese is embarrassing, but it is honest. Hidden English inside a ja build is how we got the honorific mess."
      ),
      Turn(
        "SPEAKER_01",
        "I will also kill the vendor style guide that allowed mixed register. One page, polite form only, no exceptions for witty microcopy."
      ),
      Turn(
        "SPEAKER_00",
        "Please do. Witty English dies in translation, and we have spent a year paying tutors to learn that the expensive way."
      ),
      Turn(
        "SPEAKER_02",
        "Hold the October third question: does the linguist inherit Jordan's freeze, or do we reopen contractor talk? Wait until she is actually in the seat."
      ),
    ]
  )

  static let blockDesignSystemDrift = TopicBlock(
    id: "design-system-drift",
    turns: [
      Turn(
        "SPEAKER_01",
        "Figma's Onyx 2 library lists fourteen colors that do not exist in Theme.swift, and the primary button radius is eight there and ten in AppKit."
      ),
      Turn(
        "SPEAKER_00",
        "Alex measured the marketing site as a third palette entirely, pulled from a Webflow kit nobody named in the brand folder. We are not drifting. We are forked."
      ),
      Turn(
        "SPEAKER_02",
        "Tomas wants a single tokens.json generating Swift, CSS, and the site. I like the idea and I distrust JSON that cannot make a compiler fail a typo."
      ),
      Turn(
        "SPEAKER_01",
        "A generated Swift enum can fail the build when a token disappears. That is the point. Hand-edited Theme.swift is how the fourteen ghosts appeared."
      ),
      Turn(
        "SPEAKER_00",
        "Webflow will not consume our JSON without a custom embed, and marketing will not wait. If the site stays a fork, the pipeline is a vanity project."
      ),
      Turn(
        "SPEAKER_02",
        "Then scope the pipeline to the apps first and leave Webflow as a documented exception, not as a pretend source of truth. I was overreaching."
      ),
      Turn(
        "SPEAKER_01",
        "Radius eight is the Figma spec from April. AppKit's ten came from a hit-target tweak Chris made in May without a token change. That should be eight."
      ),
      Turn(
        "SPEAKER_00",
        "Reverting hit targets to please Figma is how we get mis-taps. Publish radius ten back into Onyx 2 and stop treating the file as scripture."
      ),
      Turn(
        "SPEAKER_02",
        "I side with the apps on ten. Design can update the library in an afternoon. Shipping a tap regression to match a rectangle is backwards."
      ),
      Turn(
        "SPEAKER_01",
        "Alex, the generator is yours so Theme.swift is an output by October eighteenth, with a CI diff that fails on hand edits."
      ),
      Turn(
        "SPEAKER_01",
        "I'll build the generator. I need a frozen token list this week from Tomas, including the fourteen ghosts marked kill or add, not a mood board."
      ),
      Turn(
        "SPEAKER_02",
        "I will mark them. Nine of the fourteen are leftover dark-mode experiments. Kill those. The other five are real and missing from code."
      ),
      Turn(
        "SPEAKER_01",
        "Put the five into the October eighteenth drop. Until then, no new color enters Figma unless it already has a Swift case. That rule is the whole fix."
      ),
      Turn(
        "SPEAKER_00",
        "Marketing still needs an answer. I will send a one-line exception: Webflow stays manual, and any campaign using a fourth palette gets rejected."
      ),
      Turn(
        "SPEAKER_02",
        "Send it. If they ignore it we escalate once, not weekly. The apps plus a generator is the work; the site is a letter."
      ),
      Turn(
        "SPEAKER_01",
        "Illustration style forked too; leave it. Color and radius are enough for one sitting, and we finally chose a source of truth."
      ),
    ]
  )

  static let blockApiVersioning = TopicBlock(
    id: "api-versioning",
    turns: [
      Turn(
        "SPEAKER_00",
        "Public slash v1 conversations still exposes fields we removed in January, and Acme Health broke when we added source_device without a header they understood."
      ),
      Turn(
        "SPEAKER_02",
        "They send Accept application slash vnd.omi.v1+json, which we barely honor. Nadia wants a slash v2 with a sunset header. I think two surfaces for eleven partners is worse."
      ),
      Turn(
        "SPEAKER_01",
        "Chris counted three partners still reading created_at after we renamed it started_at, and that rename never shipped a deprecation warning. The mess is ours."
      ),
      Turn(
        "SPEAKER_01",
        "A v2 fantasy lets us feel clean while v1 rots. Put Sunset and Deprecation headers on the undocumented fields now, and pick a date partners can staff for."
      ),
      Turn(
        "SPEAKER_01",
        "March first is six months. That is staffable. Cutting v1 this year is not, and I will not pretend a winter rewrite is available."
      ),
      Turn(
        "SPEAKER_02",
        "I withdraw v2 for this year. Headers plus a partner note is the adult version. I wanted a clean break because Acme yelled, which is a bad reason."
      ),
      Turn(
        "SPEAKER_00",
        "Nadia, draft the partner note naming created_at, the silent source_device add, and the March first sunset, in language counsel will sign tonight."
      ),
      Turn(
        "SPEAKER_02",
        "I will draft it tonight. Omar should sanity-check the header names against RFC 8594 before I send anything that makes us look unread."
      ),
      Turn(
        "SPEAKER_01",
        "I will check the headers. created_at does not become a permanent alias. Undated aliases are exactly how this surface turned into a junk drawer."
      ),
      Turn(
        "SPEAKER_00",
        "Give them six months of both fields, then created_at dies on March first. Temporary aliases with a date are not junk. Undated ones are."
      ),
      Turn(
        "SPEAKER_01",
        "Fine. Dual-write until March first, then fail closed. Document that in the changelog the same day the headers ship, not a week later."
      ),
      Turn(
        "SPEAKER_02",
        "Acme also asked for a sandbox that mirrors prod schemas. That is a different budget. Leave it off the sunset mail or it hitchhikes."
      ),
      Turn(
        "SPEAKER_00",
        "Sandbox stays off. Scope is headers, dual fields, March first, Nadia's note. Chris watches the three stragglers weekly until they move, and the other eight get silence."
      ),
      Turn(
        "SPEAKER_01",
        "If a fourth partner appears on created_at after the note goes out, we still wait until March. Special cases are how dates become fiction."
      ),
      Turn(
        "SPEAKER_02",
        "Agreed on the fiction point. I wanted to soothe Acme with a private exception, and that would have taught everyone to skip the mail."
      ),
    ]
  )

  static let blockCustomerAdvisoryBoard = TopicBlock(
    id: "customer-advisory-board",
    turns: [
      Turn(
        "SPEAKER_02",
        "Thursday's advisory board had nine customers. Seven asked for shared workspaces. Five, all above two hundred seats, asked for Okta. Those are not the same product."
      ),
      Turn(
        "SPEAKER_00",
        "Lee also heard the forty-nine dollar plan people want Spanish transcription, which did not make the enterprise whiteboard. The room is biased toward whoever flew in."
      ),
      Turn(
        "SPEAKER_01",
        "Priya is right about bias, and we still promised Okta in Q2 and slipped it. Ignoring the five largest logos because the sample is skewed is a convenient dodge."
      ),
      Turn(
        "SPEAKER_01",
        "Shared workspaces imply multi-user accounts we do not have. Shipping a folder rename and calling it sharing would be worse than saying not this year."
      ),
      Turn(
        "SPEAKER_00",
        "Say not this year on sharing, then. Research spike only, no dates. Okta in November is a date we can staff if Sam stops treating identity as a side quest."
      ),
      Turn(
        "SPEAKER_01",
        "Identity is not a side quest. I delayed Okta because SCIM landed as a surprise in the same thread. Unbundle them. Okta sign-in first, SCIM later."
      ),
      Turn(
        "SPEAKER_00",
        "Unbundle accepted. Spanish transcription is a model pack, not a workspace. I can spike it next sprint with two raters, which is smaller than the board made it sound."
      ),
      Turn(
        "SPEAKER_02",
        "Two raters will not certify medical Spanish. If the forty-nine dollar people are clinics, we should not dabble. If they are students, two raters is fine."
      ),
      Turn(
        "SPEAKER_01",
        "Lee, pull the nine accounts. I think two clinics were in the room and seven were not. We have been arguing about a room we have not named."
      ),
      Turn(
        "SPEAKER_00",
        "I just checked. One clinic, eight general. Spike Spanish. Do not advertise clinical accuracy. That sentence belongs in the recap Priya sends tomorrow."
      ),
      Turn(
        "SPEAKER_02",
        "I will write the recap. Okta November, Spanish spike next sprint, shared workspaces stay research, SCIM explicitly later. No apology tour for Q2."
      ),
      Turn(
        "SPEAKER_01",
        "Add two mid-market seats to the next board so we stop hearing only from people who can fly. I will find them; I will not let sales pick mascots."
      ),
      Turn(
        "SPEAKER_00",
        "Find them by the thirtieth or we run the next board skewed again. That part is not optional even if Okta slips another week."
      ),
      Turn(
        "SPEAKER_02",
        "Okta cannot slip another week if November is the date. Sam owns a weekly demo to the five logos, even if it is ugly."
      ),
      Turn(
        "SPEAKER_01",
        "Ugly demos I will give. SCIM stays out of that same walkthrough. If a logo asks, the answer is later, not maybe."
      ),
      Turn(
        "SPEAKER_00",
        "Later is the answer. Sharing waits, Okta gets staffed, Spanish gets a spike, the board gets rebalanced. Thursday produced that list, and it is enough."
      ),
    ]
  )

  static let blockBuildTimes = TopicBlock(
    id: "build-times",
    turns: [
      Turn(
        "SPEAKER_00",
        "Clean debug compile on my M2 went from four minutes twenty in January to eleven minutes last Tuesday. Incremental is still about forty seconds. Clean is the pain."
      ),
      Turn(
        "SPEAKER_02",
        "The CI macOS job is thirty-eight minutes now. Jordan profiled it: SwiftSyntax macros eat three minutes, then generated GraphQL eats two. The rest is death by a thousand files."
      ),
      Turn(
        "SPEAKER_01",
        "Splitting GraphQL again revived last year's import cycle. I will not cheer for a sequel. Mina, you lived that split."
      ),
      Turn(
        "SPEAKER_00",
        "I lived it, and I am not doing it this month. Alex timed removing Rewind tests from the default Desktop scheme at ninety seconds saved, and nobody runs them there."
      ),
      Turn(
        "SPEAKER_02",
        "Dropping tests to make a scheme faster feels like cheating. Then I timed it myself. Ninety seconds is real, and those tests still run in their own scheme."
      ),
      Turn(
        "SPEAKER_01",
        "I concede the Rewind default. Drop them. The macro split can be a two-day spike with a kill date, not an open rewrite."
      ),
      Turn(
        "SPEAKER_00",
        "Jordan, cap the spike at two days. If macros still own three minutes after that, we live with it through this quarter rather than inventing a third architecture."
      ),
      Turn(
        "SPEAKER_02",
        "Cap accepted. I already suspect half the macro time is one code-gen for routing tables. If I cannot prove that in two days I will stop."
      ),
      Turn(
        "SPEAKER_01",
        "Please stop if you cannot prove it. Last winter we spent a week on module maps and the number did not move. I still remember the graph."
      ),
      Turn(
        "SPEAKER_00",
        "Publish the eleven-minute number in the engineering channel today so people stop guessing. A chart that only lives on Jordan's laptop is how this drifted."
      ),
      Turn(
        "SPEAKER_02",
        "I will post the chart. Alex, land the scheme change this afternoon so tomorrow's CI picks it up without waiting on the macro spike."
      ),
      Turn(
        "SPEAKER_02",
        "I'll land the scheme change. A comment in the scheme file must explain why Rewind tests are absent, or someone will add them back as a favor."
      ),
      Turn(
        "SPEAKER_00",
        "Add the comment. Buying a handful of M4 CI machines is a budget thread, not a compile thread, and mixing them lets hardware hide the macros."
      ),
      Turn(
        "SPEAKER_02",
        "Keep them unmixed. Faster machines hide the macro, they do not explain it. I wanted the hardware too, and that was laziness dressed as urgency."
      ),
    ]
  )

  static let blockContractorOffboarding = TopicBlock(
    id: "contractor-offboarding",
    turns: [
      Turn(
        "SPEAKER_01",
        "Ravi and Elise both end October thirty-first. Elise still holds production AWS through a personal Okta account. That should have been impossible, and it is current."
      ),
      Turn(
        "SPEAKER_00",
        "Revoke first, collect hardware second. Dana, cut AWS on Friday even if her Notion runbook is still mid-copy. Access is not a souvenir."
      ),
      Turn(
        "SPEAKER_02",
        "Tomas, Elise wrote the billing reconciler, and the runbook lives in a personal Notion she owns. If we revoke on Friday without a copy, finance goes blind."
      ),
      Turn(
        "SPEAKER_02",
        "Sam asked for a paid overlap week past the thirty-first. Finance said no. So the copy happens this week or we rewrite from the source, which is worse."
      ),
      Turn(
        "SPEAKER_00",
        "Tomas shadows her on the reconciler every afternoon through Thursday. I do not care if it is awkward. Friday the keys die."
      ),
      Turn(
        "SPEAKER_02",
        "Awkward I can sit through. Reconstructing her private Notion from Slack crumbs is impossible, so I will export today, formatting be damned."
      ),
      Turn(
        "SPEAKER_01",
        "Ravi's laptop was supposedly shipped October second. Tracking has been stuck in Louisville for six days. Lee, if it is not scanned by October twelfth we file."
      ),
      Turn(
        "SPEAKER_00",
        "File meaning a police report, not another polite email. Devices with prod crumbs sitting in a depot is how these stories get interesting for the wrong people."
      ),
      Turn(
        "SPEAKER_02",
        "I thought a police report was overkill last time. Looking at Elise's Okta, I was naive. File if Louisville does not move."
      ),
      Turn(
        "SPEAKER_01",
        "Nadia should pull both of them from the partner Slack on the thirty-first at noon, not when someone remembers in November. Shared channels outlive contracts."
      ),
      Turn(
        "SPEAKER_00",
        "Noon on the thirty-first, calendar invite, Nadia owns it. Also rotate the billing webhook secret after Elise's last day, even if Tomas thinks he copied everything."
      ),
      Turn(
        "SPEAKER_02",
        "Rotate it. I think I copied everything and I do not trust that sentence. Secrets are cheap to rotate and expensive to wonder about."
      ),
      Turn(
        "SPEAKER_01",
        "I will write a single offboarding checklist from this conversation so the next pair is not a scavenger hunt. It will include Okta, Notion, Slack, and hardware."
      ),
      Turn(
        "SPEAKER_00",
        "Include the Louisville clause. Rewriting the reconciler in November versus living on Elise's export is a November debate. Do not decide it while she is still in the chair."
      ),
      Turn(
        "SPEAKER_02",
        "Live on the export through November. Rewriting under a deadline we invented would be how we bounce payroll. I wanted a rewrite and I am wrong this month."
      ),
      Turn(
        "SPEAKER_01",
        "Payroll is the constraint. Shadow, export, revoke Friday, file on the laptop if needed, rotate the webhook. That is the list, and it is finite."
      ),
    ]
  )

  static let blockAnalyticsEventTaxonomy = TopicBlock(
    id: "analytics-event-taxonomy",
    turns: [
      Turn(
        "SPEAKER_00",
        "PostHog currently lists one hundred eighty-six event names, and forty of them have not fired since March. That is a graveyard with a search box."
      ),
      Turn(
        "SPEAKER_02",
        "We emit recording_started, record_start, and did_start_recording depending on the client. Chris wants a closed enum. Flutter still ships stringly names from a dart file."
      ),
      Turn(
        "SPEAKER_01",
        "Ines found the first-summary funnel uses three different events by platform, so the dashboard that looks like a story is actually three stories glued together."
      ),
      Turn(
        "SPEAKER_00",
        "Freezing all new events until a taxonomy doc exists will slow every launch. I would rather require a name in a one-pager than halt the train."
      ),
      Turn(
        "SPEAKER_01",
        "A one-pager I can write by Wednesday. Jordan, if product wants a new name after Wednesday it goes in that doc first or it does not ship."
      ),
      Turn(
        "SPEAKER_02",
        "I will live with a one-pager. Deleting the forty unused names this month would break two old boards that still point at them."
      ),
      Turn(
        "SPEAKER_00",
        "Keep the dead names until October, then delete. Chris aliases the three first-summary events this week so the funnel stops lying before the graveyard cleanup."
      ),
      Turn(
        "SPEAKER_02",
        "I can alias them. Flutter will still send the old strings until the dart file changes, so the alias has to accept both or we invent a fourth."
      ),
      Turn(
        "SPEAKER_01",
        "Accept both through October. Ines, rename the dart strings while Chris lands the alias, so the dual-name window stays short."
      ),
      Turn(
        "SPEAKER_01",
        "I'll do the dart rename. Canonical name has to live in the one-pager before Flutter moves, or I will pick a fourth by accident."
      ),
      Turn(
        "SPEAKER_02",
        "Canonical name is summary_first_completed. Ugly, unique, and not a verb salad. Put it in Wednesday's page and I will stop bikeshedding."
      ),
      Turn(
        "SPEAKER_01",
        "Locked. I also want a lint that fails CI when a new event string is not in the page. Without a lint the page becomes folklore by November."
      ),
      Turn(
        "SPEAKER_00",
        "Lint is Chris's follow-up after the page, not in the same patch as the alias. One patch that does both will sit in review until Christmas."
      ),
      Turn(
        "SPEAKER_02",
        "Sequence accepted: page Wednesday, alias and dart this week, lint next, deletions in October. I wanted the lint first and that was ego."
      ),
      Turn(
        "SPEAKER_01",
        "Ego or not, the three-name funnel is the user-visible lie. Everything else is hygiene. Ship the alias even if the lint slips a week."
      ),
      Turn(
        "SPEAKER_00",
        "Ship the alias. Forcing desktop and mobile to share one enum package is a monorepo dream. A one-pager people obey beats the dream."
      ),
      Turn(
        "SPEAKER_02",
        "Leave the package alone. If either client ignores the page after Wednesday, we revert their event, not the process. That threat has to be real once."
      ),
    ]
  )

  static let blockFeatureFlagCleanup = TopicBlock(
    id: "feature-flag-cleanup",
    turns: [
      Turn(
        "SPEAKER_01",
        "PostHog holds forty-seven flags, and twelve of them have been at one hundred percent for more than ninety days. That is not experimentation. That is ivy."
      ),
      Turn(
        "SPEAKER_00",
        "new_onboarding_v3 is one of those twelve, and the v2 code still compiles. Omar wants it gone. Priya is treating v2 as a parachute that has not been packed in a year."
      ),
      Turn(
        "SPEAKER_02",
        "A parachute nobody has pulled is not a parachute. Untested fallbacks fail closed in the wrong direction. I changed my mind; delete v2 next cycle."
      ),
      Turn(
        "SPEAKER_01",
        "ios_live_activity has been at zero percent for eleven months because legal never signed the copy. A flag that cannot turn on is a shrine."
      ),
      Turn(
        "SPEAKER_00",
        "Then legal sits Thursday or the flag is deleted Friday. I am tired of a row that exists to avoid a thirty-minute meeting. Alex, put it on their calendar."
      ),
      Turn(
        "SPEAKER_02",
        "Calendar is up. Deleting twelve flags in one day would spend November chasing a silent visual regression. Warn two weeks in the channel first."
      ),
      Turn(
        "SPEAKER_01",
        "Two-week warning, then kill anything still fully on for sixty days. Write that as policy, not as a mood. Omar can draft three sentences."
      ),
      Turn(
        "SPEAKER_00",
        "Three sentences by tomorrow. Include the live-activity ultimatum. Exclude anything under fifty percent, because those are still experiments even if they look neglected."
      ),
      Turn(
        "SPEAKER_02",
        "Under fifty I agree. The scary ones are the hundred-percent ivy and the forever-zeros. Neglected middles can wait a quarter."
      ),
      Turn(
        "SPEAKER_01",
        "Who owns the weekly stale report after this? If it is nobody, we will have forty-seven again by March and this conversation will reprise."
      ),
      Turn(
        "SPEAKER_00",
        "Mina, run the weekly report for a quarter, then rotate. A permanent owner becomes a janitor, and janitors quit the job quietly."
      ),
      Turn(
        "SPEAKER_00",
        "I'll run weekly reports for a quarter. I want a PostHog saved view, not a screenshot I forget to paste. If the view breaks, the report is allowed to skip."
      ),
      Turn(
        "SPEAKER_01",
        "Saved view, skip if broken, but skipping twice in a row pages Omar. A skip hatch without a limit is how ivy returns."
      ),
      Turn(
        "SPEAKER_00",
        "Page is too loud. A Slack nag I will take. Paging a person because a marketing flag went stale trains people to ignore pagers."
      ),
      Turn(
        "SPEAKER_02",
        "Slack nag, twice, then it becomes a ticket on the cleanup board. I overreached on paging. Flags are not a SEV."
      ),
      Turn(
        "SPEAKER_01",
        "Decision: warn two weeks, delete hundred-percent ivy after sixty days, legal Thursday or live-activity dies, Mina's view for a quarter. v2 code goes next cycle."
      ),
    ]
  )

  static let blockDatabaseMigrationWindow = TopicBlock(
    id: "database-migration-window",
    turns: [
      Turn(
        "SPEAKER_00",
        "We need transcript_language on conversations, fourteen million rows. The last ALTER on this table locked writes for nine minutes in June, which users felt as a hang."
      ),
      Turn(
        "SPEAKER_02",
        "Nadia booked a weekend window October nineteenth, two to six UTC. That is Sunday morning in Tokyo, and eight percent of monthly actives live there. I would not."
      ),
      Turn(
        "SPEAKER_01",
        "Tomas wants expand-contract: nullable column in the Tuesday 0.12.149 deploy, which is instant, then a backfill, then NOT NULL in November. I like that more than a Japanese Sunday."
      ),
      Turn(
        "SPEAKER_01",
        "Priya is worried the backfill will fight sync workers. If we crawl at fifty thousand rows a minute we will lose that fight. Twenty thousand is boring and safe."
      ),
      Turn(
        "SPEAKER_02",
        "Twenty thousand a minute is about twelve hours for fourteen million. Start Wednesday at ten UTC, pause if p95 write crosses eighty milliseconds. That is a kill switch I trust."
      ),
      Turn(
        "SPEAKER_01",
        "I wanted fifty thousand because I wanted it done overnight. Crossing eighty milliseconds to save a few hours is how June happened. I yield. Twenty thousand."
      ),
      Turn(
        "SPEAKER_00",
        "Cancel the October nineteenth window publicly so on-call does not baby-sit an empty change. Nadia, send that cancellation today while people still have the invite."
      ),
      Turn(
        "SPEAKER_02",
        "I will cancel it. I will also put the eighty millisecond pause in the runbook, because a backfill without a kill switch is just a slow version of June."
      ),
      Turn(
        "SPEAKER_01",
        "Nullable now, backfill Wednesday, NOT NULL only after a week of zero pauses. If we pause more than three times, we stop and redesign the writer."
      ),
      Turn(
        "SPEAKER_00",
        "Three pauses is the budget. Tomas owns the worker. It must be idempotent; a restart that double-writes languages will be worse than a missing column."
      ),
      Turn(
        "SPEAKER_02",
        "Idempotent I can do with a where-null predicate. Folding NOT NULL into the backfill week is off the table. November is the earliest."
      ),
      Turn(
        "SPEAKER_01",
        "November is fine. Product can treat unknown language as auto until then. Do not block the summarizer on a column that is still filling."
      ),
      Turn(
        "SPEAKER_00",
        "Do not block. A one-time detect pass over historical rows without language is a quality project, not this migration, and I refuse to smuggle it."
      ),
      Turn(
        "SPEAKER_02",
        "Keep detect separate. If someone attaches it to the backfill we will still be running at Christmas. I wanted to sneak it in, and that was greedy."
      ),
      Turn(
        "SPEAKER_01",
        "Greedy is accurate. Ship the column Tuesday, crawl Wednesday, watch p95, cancel the weekend. That is the entire move, and it is smaller than it felt."
      ),
      Turn(
        "SPEAKER_00",
        "Smaller is the point. Announce the crawl in status so support does not open a sync incident when writes look briefly busy. One paragraph, no jargon."
      ),
    ]
  )

  static let blockPushNotificationOptOut = TopicBlock(
    id: "push-notification-opt-out",
    turns: [
      Turn(
        "SPEAKER_01",
        "iOS notification opt-out hit twenty-two percent after the daily digest launched August twelfth. Android is nine. The digest fires at eight local and people disable everything."
      ),
      Turn(
        "SPEAKER_00",
        "Mina wants categories: digest versus mention versus crash. Categories exist on iOS fifteen and up, but the app still asks for a single authorization on first launch."
      ),
      Turn(
        "SPEAKER_02",
        "Sam, that single prompt is the mistake. People who meant to silence a morning summary are silencing crash alerts they might actually need."
      ),
      Turn(
        "SPEAKER_01",
        "Lee read forty App Store reviews that say spam. Jordan wants the digest killed. Priya notes a thirty-one percent open rate among people who kept it, which is not nothing."
      ),
      Turn(
        "SPEAKER_00",
        "Killing a thirty-one percent open channel because of a permission prompt is backwards. Split the toggle. Keep the digest. Stop asking for provisional permission on first launch."
      ),
      Turn(
        "SPEAKER_02",
        "I drop the kill idea. I was reacting to the reviews, not the open rate. A digest-only switch in 1.8.5 is the grown-up fix."
      ),
      Turn(
        "SPEAKER_01",
        "1.8.5 already has two other commits. Adding a toggle is small if we do not also redesign the whole permission primer. Resist the redesign."
      ),
      Turn(
        "SPEAKER_00",
        "Resist it. Mina, build the digest-only switch and watch opt-out for two weeks after it ships, using Android as the control since it barely moved."
      ),
      Turn(
        "SPEAKER_00",
        "I'll own the two-week watch. Freeze the iOS category strings by Monday or store review will bounce us for changing notification purpose copy mid-review."
      ),
      Turn(
        "SPEAKER_01",
        "Freeze the strings Monday. Mention and crash stay on the original authorization. Digest becomes optional and defaults to on for existing users, off for new ones."
      ),
      Turn(
        "SPEAKER_00",
        "Default off for new users will tank the open rate. Default on, with a one-tap mute in the first digest itself. Teach the control where the annoyance lives."
      ),
      Turn(
        "SPEAKER_02",
        "Mute-in-digest is better than a settings archaeology hunt. I was wrong about default off. Existing and new both start on, mute is local and obvious."
      ),
      Turn(
        "SPEAKER_01",
        "Local mute must sync, or a phone and a watch will disagree at eight. That sync is the only extra work, and it belongs in 1.8.5 with the toggle."
      ),
      Turn(
        "SPEAKER_00",
        "Then the extra work is in. Android categories landed later and look different. Do not stall 1.8.5 on making the two platforms identical."
      ),
      Turn(
        "SPEAKER_02",
        "Do not block. Measure two weeks, then talk Android. If iOS opt-out is still twenty-two after a mute that is obvious, then we revisit killing the digest."
      ),
    ]
  )

  static let blockBrandRefresh = TopicBlock(
    id: "brand-refresh",
    turns: [
      Turn(
        "SPEAKER_00",
        "Northcurrent delivered a wordmark that reads like a hearing-aid company, and we have already paid forty-eight thousand. Chris and Dana both hate the lowercase-only lockup."
      ),
      Turn(
        "SPEAKER_02",
        "Marketing printed five hundred stickers last week. Throwing them out is a tantrum. Using them internally is how we get value without putting that mark on the menu bar."
      ),
      Turn(
        "SPEAKER_01",
        "Ines is right about the menu bar. The old mark is readable at eighteen pixels. The new one turns into a smudge. Alex mocked a sixteen pixel variant overnight."
      ),
      Turn(
        "SPEAKER_00",
        "The sixteen pixel variant is the only shippable artifact in the pile. Keep their warm gray, reject the navy they pushed, and put Alex's mark in the app."
      ),
      Turn(
        "SPEAKER_02",
        "Firing the agency over a lockup feels dramatic, and I said fire them yesterday. Looking at the gray, they did get the palette right. Renegotiate the remaining twelve thousand instead."
      ),
      Turn(
        "SPEAKER_01",
        "Twelve thousand buys a website wordmark we can actually use, not more app icons. Put those terms in the change order. Do not let them redraw the menu bar again."
      ),
      Turn(
        "SPEAKER_00",
        "Alex, productionize the app icon from your overnight mock by next Wednesday, with a dark-menu version. That Wednesday is the ship date, not a critique session."
      ),
      Turn(
        "SPEAKER_00",
        "I'll productionize the icon. I will not sit in another three-hour review with Northcurrent if Dana is already decided. Send them the mock and a no on navy."
      ),
      Turn(
        "SPEAKER_01",
        "Dana is decided. I will send the mail. Stickers go in the office drawer, website may use the wordmark, app uses Alex. Three surfaces, three answers, stop blending them."
      ),
      Turn(
        "SPEAKER_00",
        "Three answers is the resolution. A corrected sticker run waits until the website wordmark exists, or we print a fourth mistake for fun."
      ),
      Turn(
        "SPEAKER_02",
        "No reprint. I wanted a corrected run for the conference in November, and that deadline is how the first five hundred happened. Wear the old pin."
      ),
      Turn(
        "SPEAKER_01",
        "Keep last year's pin on the lanyard. If sales complains, point them at the forty-eight thousand we already spent learning that agencies do not see eighteen pixel menus."
      ),
      Turn(
        "SPEAKER_00",
        "Point them once. After that it is a closed thread. Brand is not a weekly salon, and this one already cost more attention than the icon deserved."
      ),
      Turn(
        "SPEAKER_02",
        "Closed. I will archive the navy explorations so they do not resurface in a December deck as if nobody voted."),
    ]
  )

  static let blockIncidentPostmortemProcess = TopicBlock(
    id: "incident-postmortem-process",
    turns: [
      Turn(
        "SPEAKER_01",
        "Postmortems currently take three weeks and read like charge sheets. The June fourteenth gateway write-up still says owner TBD, which is a monument to the process."
      ),
      Turn(
        "SPEAKER_00",
        "The template demands five sections, including a customer comms timeline nobody fills. Nadia wants a one-page form due in forty-eight hours. Omar thinks rushed writing misses causes."
      ),
      Turn(
        "SPEAKER_02",
        "Rushed writing misses causes on SEV-1. SEV-2 using the same novel is why TBD sits for months. Split the templates. I was defending a single form out of habit."
      ),
      Turn(
        "SPEAKER_02",
        "Split accepted. SEV-1 keeps the long form. SEV-2 and below get Nadia's page due in two business days. Chris closes the June fourteenth TBD this Friday."
      ),
      Turn(
        "SPEAKER_00",
        "Chris, close June fourteenth without waiting for a perfect timeline. A named owner and a cause sentence beat another week of archaeology."
      ),
      Turn(
        "SPEAKER_02",
        "I can close it Friday with a cause sentence. I will not invent a comms timeline that did not happen. Blank is truer than a reconstructed fiction."
      ),
      Turn(
        "SPEAKER_01",
        "Blank on comms is allowed on the short form. Banned language is human error as a title. That phrase is a verdict and it does not belong in the header."
      ),
      Turn(
        "SPEAKER_00",
        "Ban it in the header and in the first paragraph. If someone needs to describe a missed check, they describe the check, not the person. Nadia, add that rule to the page."
      ),
      Turn(
        "SPEAKER_02",
        "It will be in the page. Lee wanted a blame-free label at the top, which I thought was soft. After reading June fourteenth, the label is load-bearing."
      ),
      Turn(
        "SPEAKER_01",
        "Forty-eight hours for SEV-2 starts at mitigation, not at the Slack announcement. People game the announcement time. Mitigation is in the incident doc already."
      ),
      Turn(
        "SPEAKER_00",
        "Start at mitigation. If a SEV-2 misses the two-day page, it becomes a standing agenda item, not a shame thread. Shame threads are how we got charge sheets."
      ),
      Turn(
        "SPEAKER_02",
        "Agenda item I will run. A scoreboard of who filed late is shame with extra columns, and I will not operate one."
      ),
      Turn(
        "SPEAKER_01",
        "No scoreboard. SEV-3 might deserve the short page or just a Slack template; wait until the short page has been used twice before inventing a third form."
      ),
      Turn(
        "SPEAKER_00",
        "Leave SEV-3 alone. Ship the split this week, close June fourteenth Friday, ban the verdict phrase. That is enough process for a sitting that was about process."
      ),
      Turn(
        "SPEAKER_02",
        "Enough. I will delete the five-section requirement from the wiki so the long form is opt-in for SEV-1 rather than the default nobody wanted."
      ),
      Turn(
        "SPEAKER_01",
        "Delete it today, not after the next incident. Wikis that change after the fire are how TBD survived the summer."
      ),
    ]
  )

  static let blockRecruitingReferralProgram = TopicBlock(
    id: "recruiting-referral-program",
    turns: [
      Turn(
        "SPEAKER_00",
        "The referral bonus is still two thousand dollars, unchanged since twenty twenty-two, while senior engineering referrals elsewhere pay five to eight. We have had three referrals this year."
      ),
      Turn(
        "SPEAKER_02",
        "One of those three became a hire: Tomas referred Ines. The funnel is not empty. It is tiny. Priya wants six thousand. Finance caps us at four without the board."
      ),
      Turn(
        "SPEAKER_01",
        "Dana thinks money is not why people stay quiet. They do not know which roles are open. The jobs channel has been a ghost town since spring, which is on us."
      ),
      Turn(
        "SPEAKER_00",
        "Then we take the four thousand starting November first, and Dana posts open reqs in Monday standup for a month. Cash without a list is a poster nobody reads."
      ),
      Turn(
        "SPEAKER_02",
        "I wanted six and I will take four. Board time for two extra thousand is a worse use than filling the roles. I concede the cap."
      ),
      Turn(
        "SPEAKER_01",
        "Jordan, put a refer link on the careers page so people do not forward a Greenhouse URL that expires. That link is the actual product."
      ),
      Turn(
        "SPEAKER_01",
        "I can ship the link this week. Legal still has not said whether contractors may refer. If the answer is late, launch without them rather than holding the page."
      ),
      Turn(
        "SPEAKER_02",
        "Launch without contractors. I asked legal two weeks ago and maybe is not a plan. We can add them in a footnote later if counsel ever wakes up."
      ),
      Turn(
        "SPEAKER_01",
        "Footnote later. Tell standup that Ines came in through Tomas so the story is concrete. Abstract generosity does not move people. A name does."
      ),
      Turn(
        "SPEAKER_00",
        "Use the names. Do not publish the bonus in that standup or we will spend the hour on fairness theater. Point at the careers link and sit down."
      ),
      Turn(
        "SPEAKER_02",
        "Sit down after two minutes, agreed. Sales referrals should pay the same four thousand. Mixing rates is how people stop referring."
      ),
      Turn(
        "SPEAKER_01",
        "Same rate. If finance wants a sales exception they can bring it to the board, not to this room. We are not minting a second ladder."
      ),
      Turn(
        "SPEAKER_00",
        "No second ladder. Four thousand, November first, Monday reqs for a month, careers link this week, contractors parked, Ines-and-Tomas as the example. Stop there."
      ),
      Turn(
        "SPEAKER_02",
        "Stop there. I will also archive the two-thousand figure on the intranet so a candidate does not find a stale number and think we are lying."
      ),
      Turn(
        "SPEAKER_01",
        "Archive that figure today. Stale intranet numbers are how we ended up defending two thousand in the first place, like a fossil."
      ),
    ]
  )

  static let blockOfficeMoveLogistics = TopicBlock(
    id: "office-move-logistics",
    turns: [
      Turn(
        "SPEAKER_01",
        "The lease at eighty-eight King ends December thirty-first. The fourteenth-and-Folsom space has forty-two desks against the sixty we have now, and people still badge four point two days a week."
      ),
      Turn(
        "SPEAKER_00",
        "Hybrid policy says three. Reality is four point two. If we accept forty-two desks it is first-come assigned, not a secret ranking. Ines, run a seating survey before Friday."
      ),
      Turn(
        "SPEAKER_02",
        "I can run the survey. I will not run a popularity contest. Ask for days-in-office and monitor needs, then assign, and let the leftover feelings go to a waitlist."
      ),
      Turn(
        "SPEAKER_02",
        "The mover quoted thirty-one thousand including the server closet. That closet holds a ten-gig switch from twenty twenty-three, and the new building's shared riser is one gig."
      ),
      Turn(
        "SPEAKER_00",
        "Tomas wants four units at Hurricane Electric for four hundred a month to keep the controller and the build cache. Chris says we should already be cloud-only. The switch still terminates office wifi."
      ),
      Turn(
        "SPEAKER_02",
        "Cloud-only is a slogan until someone names the wifi controller. Keep the four-U. I argued for dumping it last month, and I had not counted the cache."
      ),
      Turn(
        "SPEAKER_01",
        "Keep the four-U. Move dates December twelfth and thirteenth, office dark those two days. Anyone who needs a desk goes to the Folsom space on the fourteenth, assigned or not."
      ),
      Turn(
        "SPEAKER_00",
        "Assigned by then. Survey closes October tenth so Ines has time. Extra monitors have no closet waiting, and I will not draw a storage room onto a floor plan."
      ),
      Turn(
        "SPEAKER_02",
        "Store extra monitors at HE for a month, then sell or recycle. A graveyard in the new space will eat the forty-two desks before humans sit down."
      ),
      Turn(
        "SPEAKER_01",
        "Sell after a month. Parking is unpriced by the Folsom landlord. Do not promise parking in the survey or we will have invented a perk."
      ),
      Turn(
        "SPEAKER_00",
        "No parking promise. Nadia should also cancel the King building's December events so we do not host a holiday thing in a half-packed office. That cancellation is this week."
      ),
      Turn(
        "SPEAKER_02",
        "I will cancel the events. I wanted to keep the party at King as a goodbye, and that is nostalgia with a certificate of insurance we will not get."
      ),
      Turn(
        "SPEAKER_01",
        "Nostalgia denied. Party at Folsom in January if people still care. December is boxes. Tomas books HE this week before the four-U window disappears."
      ),
      Turn(
        "SPEAKER_00",
        "Book it. Chris, I need you on the record that wifi will ride that rack, so this does not get relitigated as cloud-only in a December standup."
      ),
      Turn(
        "SPEAKER_02",
        "On the record: wifi controller plus build cache at HE, everything else cloud. The cloud-only slogan is retired. Slogans do not packet-switch."
      ),
      Turn(
        "SPEAKER_01",
        "Packet-switch they do not. Forty-two desks, survey, HE rack, December twelfth move, monitors sold after a month, no parking fiction. That is the plan."
      ),
      Turn(
        "SPEAKER_00",
        "We still move even if the survey says we need fifty desks we do not have. Crowding is cheaper than another year of King at this rent."
      ),
    ]
  )

  static let blockOpenSourceLicenceAudit = TopicBlock(
    id: "open-source-licence-audit",
    turns: [
      Turn(
        "SPEAKER_00",
        "The scan found six GPL-ish packages. ffmpeg-kit is LGPL and we compile it into iOS, which may trigger a source offer. SomeChart on Android is GPL-3, which is worse."
      ),
      Turn(
        "SPEAKER_02",
        "Harrington and Wu's memo is dated September second. Sam thought ffmpeg-kit was MIT. I thought that too. We were both reading a README badge instead of the license file."
      ),
      Turn(
        "SPEAKER_01",
        "Charts we can replace: Swift Charts on iOS, Vico on Android under Apache two. ffmpeg is the hard one because the WAV to M4A path still goes through it."
      ),
      Turn(
        "SPEAKER_00",
        "Omar floated a source-offer URL in Settings. Priya hates how that looks. Legal insists the URL exists if we keep ffmpeg-kit. Optics lose to the memo."
      ),
      Turn(
        "SPEAKER_02",
        "Optics lose. Put the URL in Settings as a dull row, not a banner. I wanted to hide it in a web page. Hiding is what the memo forbids."
      ),
      Turn(
        "SPEAKER_01",
        "Rip SomeChart this sprint. Do not panic-delete ffmpeg. Spike replacing ffmpeg-kit with AVFoundation export by October twenty-fifth, and if the spike fails we keep the URL."
      ),
      Turn(
        "SPEAKER_00",
        "Mina, replace SomeChart this sprint with Vico, including the one dashboard that uses custom markers. If markers are the hold-up, ship without them."
      ),
      Turn(
        "SPEAKER_00",
        "I'll swap in Vico this sprint, and I will ship without custom markers rather than keep GPL-3 for a dotted line. Markers are vanity. The license is not."
      ),
      Turn(
        "SPEAKER_01",
        "Vanity is the right word. Lee should own the AVFoundation spike, two days, no heroics. A failed spike that we record is better than a quiet maybe."
      ),
      Turn(
        "SPEAKER_00",
        "Two days, recorded. Tomas, list the other four GPL-ish hits by Friday with a yes, no, or replace, not a paragraph. False positives still need names."
      ),
      Turn(
        "SPEAKER_02",
        "A table I can do. I already suspect two are transitive test-only deps. If they never ship, they are a CI problem, not a store problem."
      ),
      Turn(
        "SPEAKER_01",
        "Call test-only out explicitly so legal does not make us offer source for a linter. The memo is blunt, and blunt people misread graphs."
      ),
      Turn(
        "SPEAKER_00",
        "Explicit. Decision: Vico this sprint, Settings URL this sprint, ffmpeg spike by the twenty-fifth, table of the remaining four on Friday. No banners, no panic."
      ),
      Turn(
        "SPEAKER_02",
        "No panic. I will also pin ffmpeg-kit until the spike returns so a casual upgrade does not change the license under us again."
      ),
      Turn(
        "SPEAKER_01",
        "Pin it today. Casual upgrades are how the MIT badge fooled us. The badge was decoration. The file was the product."
      ),
      Turn(
        "SPEAKER_00",
        "Decoration is a kind word. After Friday I want the license file in the review checklist for any new native dep, or we will repeat this with a smile."
      ),
    ]
  )

  static let blockModelProviderEvaluation = TopicBlock(
    id: "model-provider-evaluation",
    turns: [
      Turn(
        "SPEAKER_00",
        "Blind scores on forty tapes: on-device AFM at six point two faithfulness, GPT four point one mini at eight point one, Haiku at eight point four, Flash-Lite at seven point nine."
      ),
      Turn(
        "SPEAKER_02",
        "Flash-Lite is four hundred milliseconds at p fifty and four tenths of a cent. Haiku is one point eight cents. Mina wants Flash-Lite on reduce because two tenths of a point is not four times the bill."
      ),
      Turn(
        "SPEAKER_01",
        "Lee says the forty tapes are almost all English meetings, so the two-tenth gap might vanish on other languages. Switching reduce on that set is a guess dressed as a table."
      ),
      Turn(
        "SPEAKER_01",
        "Keep AFM for the first pass when the window fits; it is free and private. Reduce stays on Haiku until we add ten non-English tapes, then we revisit Flash-Lite in two weeks."
      ),
      Turn(
        "SPEAKER_02",
        "I wanted Flash-Lite this week and I will wait. Two weeks is honest if Lee actually adds the tapes. If the tapes slip, we do not quietly switch to save a cent."
      ),
      Turn(
        "SPEAKER_01",
        "I will add the tapes. Jordan already has six Japanese and four Spanish candidates in the eval bucket. I need someone to score them, not just to dump files."
      ),
      Turn(
        "SPEAKER_00",
        "Nadia, score those ten with the same rubric as the forty, and keep the provider column hidden. If the rubric drifts the table becomes a mood."
      ),
      Turn(
        "SPEAKER_02",
        "I can score them, and I will keep the column hidden. English and Japanese stay on separate rows; averaging them would hide a failure inside a pretty mean."
      ),
      Turn(
        "SPEAKER_01",
        "Separate rows, agreed. Cost numbers belong next to them: Haiku at one point eight cents, Flash-Lite at four tenths, AFM at zero. A score without a price is a trophy."
      ),
      Turn(
        "SPEAKER_00",
        "Trophies we have. Do not switch the first pass off AFM while this is running. Privacy is the product story, and a cheaper reduce does not require breaking it."
      ),
      Turn(
        "SPEAKER_02",
        "First pass stays. Omar asked whether GPT should even remain in the matrix. Eight point one at one point one cents is fine, but it is a third bill we do not need."
      ),
      Turn(
        "SPEAKER_01",
        "Drop GPT from production choices; keep it in the eval matrix so we notice if Haiku regresses. An eval-only row is cheap. A third production path is not."
      ),
      Turn(
        "SPEAKER_00",
        "Eval-only GPT is fine. Production is AFM then Haiku. Two weeks, ten tapes, separate rows. If Japanese Haiku falls below seven, we do not ship that reduce there."
      ),
      Turn(
        "SPEAKER_02",
        "A floor of seven is a real gate. I would have hand-waved it. Write the floor into the eval note so a future us cannot average our way around it."
      ),
      Turn(
        "SPEAKER_01",
        "I will write the floor. Flash-Lite as a Haiku-outage fallback, rather than a replacement, waits until the ten tapes exist. No fallback folklore before that."
      ),
      Turn(
        "SPEAKER_00",
        "No folklore. A fallback nobody measured is how the third path instinct appeared. Measure, then maybe. Never the other way around."
      ),
      Turn(
        "SPEAKER_02",
        "Measure then maybe. I will also freeze the forty-tape set so we stop adding English examples that make AFM look worse without teaching us anything new."
      ),
      Turn(
        "SPEAKER_01",
        "Freeze the forty. New work is the ten, the floor, and the two-week revisit. Everything else is rearranging trophies on the same shelf."
      ),
    ]
  )

  static let blockChurnInterviewFindings = TopicBlock(
    id: "churn-interview-findings",
    turns: [
      Turn(
        "SPEAKER_01",
        "August had twelve cancel interviews. Five never opened the app after week two. Three named Mac battery. Two wanted month-to-month. Two cited the model-provider blog post."
      ),
      Turn(
        "SPEAKER_00",
        "Jordan, battery is the 1.8.3 regression we already shipped a fix for on September fourth. If we are still hearing it, the email did not travel. Say the fix in the next note."
      ),
      Turn(
        "SPEAKER_02",
        "Alex reread the blog. Paragraph four says we send audio to the cloud, which is only true for backup. That sentence is doing damage the interviews named."
      ),
      Turn(
        "SPEAKER_01",
        "Rewrite paragraph four today, Alex, in the present tense, with on-device as the default. Do not add a guilt screen to cancellation. Priya is right that guilt converts nothing and stains the brand."
      ),
      Turn(
        "SPEAKER_00",
        "Ines wanted a kill-switch screenshot in the cancel flow. A one-line on-device by default plus a settings link is enough. A screenshot of a toggle looks like a hostage card."
      ),
      Turn(
        "SPEAKER_02",
        "The screenshot is gone. I was trying to teach at the door. Teaching belongs in the blog and the note, not in the last page before a person leaves."
      ),
      Turn(
        "SPEAKER_01",
        "Month-to-month is the one I cannot solve here. Finance hates it. Leave the SKU off the cancel flow as a save offer we cannot honor."
      ),
      Turn(
        "SPEAKER_00",
        "No save offer. Chris, write the next-note sentence on the September fourth battery fix, with a link, not a paragraph of apology."
      ),
      Turn(
        "SPEAKER_00",
        "The sentence is mine. I will tack on a parenthetical that backup audio is opt-in, because that is the actual claim paragraph four mangled."
      ),
      Turn(
        "SPEAKER_01",
        "Parenthetical is good. The five who never returned after week two are the harder pile. That is activation, not pricing, and it rhymes with the empty-state work without being the same bug."
      ),
      Turn(
        "SPEAKER_00",
        "Do not merge it with empty-state. Different people, different week. Assign a separate look at day-ten return, and keep it off this cancel thread so we do not boil the ocean."
      ),
      Turn(
        "SPEAKER_02",
        "Separate look, owned by Lee, sample the five if they replied to outreach. If they did not reply, we still have the notes, and we do not chase them."
      ),
      Turn(
        "SPEAKER_01",
        "Do not chase. A battery footnote on the in-app about screen is extra medicine. One blog repair and one email is the dose."
      ),
      Turn(
        "SPEAKER_00",
        "Dose accepted. Blog today, email sentence this week, cancel flow gets one line and a link, month-to-month stays with finance, day-ten split off. Twelve calls paid for that."
      ),
      Turn(
        "SPEAKER_02",
        "Harvest is the right size. I wanted a grand retention program. Twelve calls do not fund a program. They fund four precise edits."
      ),
      Turn(
        "SPEAKER_01",
        "Four edits. If November's interviews still mention paragraph four, then we failed the rewrite, not the strategy, and we fix the sentence again."
      ),
    ]
  )

  static let blockStorageCostGrowth = TopicBlock(
    id: "storage-cost-growth",
    turns: [
      Turn(
        "SPEAKER_00",
        "S3 was eleven hundred forty in January and thirty-eight ninety in August. Sixty-one percent is raw audio, twenty-two embeddings, seventeen everything else. That mix should have triggered a rule we never enabled."
      ),
      Turn(
        "SPEAKER_02",
        "The Glacier-after-thirty-days rule exists on the staging bucket. Someone pointed the console at the wrong account. Prod has been hot storage all year, which is an expensive typo."
      ),
      Turn(
        "SPEAKER_01",
        "Nadia, enable Glacier on prod audio after a restore drill next Wednesday, not before. A rule without a drill is how a lawyer finds a file we cannot open."
      ),
      Turn(
        "SPEAKER_00",
        "Omar can add idempotency keys this week. Chris found about twelve percent duplicate audio from the desktop uploader retrying in 0.12.140 without keys. That is not growth. That is a leak."
      ),
      Turn(
        "SPEAKER_02",
        "Keys this week. I thought the retries were harmless because the objects hashed the same, and they did not; timestamps in the path made twins. I was wrong."
      ),
      Turn(
        "SPEAKER_01",
        "Twins we can garbage-collect after keys land. Do not garbage-collect first or we will delete the original by accident. Order matters, and I want it written down."
      ),
      Turn(
        "SPEAKER_00",
        "Written: keys, then a dry-run collector, then Glacier after the Wednesday drill. Embeddings stay float32. Nadia's int8 drop cost two points on retrieval, which is more than I will spend for eight hundred a month."
      ),
      Turn(
        "SPEAKER_02",
        "I pushed int8 because eight hundred looks loud on a slide. Two retrieval points are louder in the product. I yield on quantizing until she has a one-point-or-better scheme."
      ),
      Turn(
        "SPEAKER_01",
        "One-point-or-better is the bar. Tomas, build the dry-run collector with a report of would-delete bytes, no actual deletes, by next Friday."
      ),
      Turn(
        "SPEAKER_01",
        "I can. I will exclude anything with a legal-hold prefix so the collector cannot be clever. Clever collectors are how holds vanish."
      ),
      Turn(
        "SPEAKER_02",
        "Exclude holds. Derived embeddings should never go to Glacier; restore latency there ruins search. Audio can wait a day. Vectors cannot."
      ),
      Turn(
        "SPEAKER_01",
        "Never for vectors. Write a lifecycle comment so a helpful person does not copy the audio rule onto the embeddings prefix in a year."
      ),
      Turn(
        "SPEAKER_00",
        "Comment in the Terraform, not in a wiki. Wikis do not apply rules. If the copy happens anyway, the comment at the resource is the thing they will actually see."
      ),
      Turn(
        "SPEAKER_02",
        "Terraform comment, agreed. Announce the Wednesday drill in status so nobody files a sev when restore looks slow. One paragraph, name Omar as the drill owner."
      ),
      Turn(
        "SPEAKER_01",
        "Omar owns the drill, Tomas the dry-run, Nadia the rule after. Twelve percent twins are the surprise win; Glacier is the boring win. Both ship."
      ),
    ]
  )

  static let blockKeyboardShortcutConflicts = TopicBlock(
    id: "keyboard-shortcut-conflicts",
    turns: [
      Turn(
        "SPEAKER_01",
        "Record toggle is Command-Shift-R, which collides with Safari's reader and Chrome's too. Eighteen support tickets in ninety days is not a mysterious signal."
      ),
      Turn(
        "SPEAKER_00",
        "The global shortcut also fires inside input fields, including once in a password box, which is how you get a recording you did not mean and a password you might have spoken."
      ),
      Turn(
        "SPEAKER_02",
        "Dana wants Command-Option-O for Omi. Option chords are awkward on some laptops. Lee remaps Caps Lock and thinks everyone will. They will not."
      ),
      Turn(
        "SPEAKER_01",
        "Sam floated Command-Shift-S until someone remembered Sketch. We do not win that fight. Command-Shift-O starting in 0.12.150 is ugly and free of famous collisions."
      ),
      Turn(
        "SPEAKER_00",
        "Ugly I can sell. Migrate existing users only if they still have the factory binding. People who customized R on purpose should keep R. A banner once, not a nag."
      ),
      Turn(
        "SPEAKER_02",
        "A banner once, with a button that opens the shortcut pane. I wanted to steal Option-O anyway, then I checked Zoom's neighbors and backed off. Good."
      ),
      Turn(
        "SPEAKER_01",
        "Alex, change the factory default and the migration predicate, including a test that a custom binding is left untouched. That test is the whole point."
      ),
      Turn(
        "SPEAKER_01",
        "I'll handle the predicate. Seventy percent never change the default, so most people will move, and that is acceptable if the banner tells them what moved."
      ),
      Turn(
        "SPEAKER_02",
        "Tell them what moved, not why we are sorry. Sorry copy makes it sound dangerous. It is a key. Ines should write eight words, not a paragraph."
      ),
      Turn(
        "SPEAKER_01",
        "Eight words. Capture while a password field is focused should be suppressed. Security will agree. Product likes always-on. Always-on is how the spoken password happens."
      ),
      Turn(
        "SPEAKER_00",
        "Suppress on password fields. If product wants always-on they can bring a case that is not hypothetical. We have a real case in the ticket pile."
      ),
      Turn(
        "SPEAKER_02",
        "Suppress. I will add the field-type check. I was the always-on person last quarter, and the ticket pile is the evidence I asked for, so I lose."
      ),
      Turn(
        "SPEAKER_01",
        "You lose politely, which I appreciate. Also ignore the eighteen tickets that are actually people who remapped and forgot; support can close those with the banner screenshot."
      ),
      Turn(
        "SPEAKER_00",
        "Close those after 0.12.150, not before, or we will re-explain a default that has not moved yet. Timing is the only kindness here."
      ),
    ]
  )

  static let blockErrorBudgetPolicy = TopicBlock(
    id: "error-budget-policy",
    turns: [
      Turn(
        "SPEAKER_00",
        "SRE wants ninety-nine point nine monthly on the sync API, which is forty-three minutes of five-hundreds. Last month we burned fifty-one on the June gateway outage alone."
      ),
      Turn(
        "SPEAKER_02",
        "If we adopt that target, Mina wants a deploy freeze after fifty percent burn. That freeze is how you never ship the language backfill. I will not sign it."
      ),
      Turn(
        "SPEAKER_01",
        "Omar is right that fifty percent is a trap. Our informal bar is a Grafana board that looks fine. A real number can be looser than nine-nine-nine and still be a number."
      ),
      Turn(
        "SPEAKER_00",
        "Ninety-nine point five for Q4 is three point six hours. Freeze only after seventy-five percent burn, and only for SEV-1-class work. Language backfill can ship if p95 stays under eighty milliseconds."
      ),
      Turn(
        "SPEAKER_02",
        "I can live with nine-nine-five and a seventy-five freeze. I wanted nine-nine-nine because it sounds like adulthood. Adulthood that cannot ship is a costume."
      ),
      Turn(
        "SPEAKER_01",
        "Costume is fair. Do not page on burn rate. Page on user-facing SEV. A burn-rate page at two in the morning about a budget is how on-call starts ignoring pages."
      ),
      Turn(
        "SPEAKER_00",
        "No burn pages. Chris, put the Q4 number into the SRE doc today, with the seventy-five percent freeze clause and the p95 guard for the backfill."
      ),
      Turn(
        "SPEAKER_00",
        "I'll update the SRE doc today. January is when we revisit nine-nine-nine, so this does not harden into a forever compromise without a date."
      ),
      Turn(
        "SPEAKER_01",
        "January revisit, on the calendar, not in a footnote. If Q4 is quiet we may earn the tighter target. If it is not, we keep the hours we can actually spend."
      ),
      Turn(
        "SPEAKER_00",
        "Earn it with quiet, not with a slide. Priya asked whether product launches pause at seventy-five. They pause only if the launch is a SEV-1 risk. A copy change does not."
      ),
      Turn(
        "SPEAKER_02",
        "Copy changes never pause. I will put examples in the doc so a cautious person does not freeze the website. Caution without examples becomes religion."
      ),
      Turn(
        "SPEAKER_01",
        "Examples help. Desktop sync should not share this budget. Mixing them will make a laptop blip burn the API, which is nonsense."
      ),
      Turn(
        "SPEAKER_00",
        "Separate budgets. API is API. Desktop is a client. If someone wants a single dashboard they can stack the graphs, not the minutes."
      ),
      Turn(
        "SPEAKER_02",
        "Stack the graphs. I almost merged them for simplicity, and simplicity there is a lie. Two graphs, two minutes, one January date."
      ),
      Turn(
        "SPEAKER_01",
        "Two graphs. Ship the doc today, tell the backfill owners the p95 guard, and leave nine-nine-nine in January where it cannot sabotage October."
      ),
      Turn(
        "SPEAKER_00",
        "October has enough sabotage of its own. Number chosen, freeze rule chosen, paging rule chosen, backfill allowed under eighty. Stop decorating it."
      ),
    ]
  )

  static let sharedBlocks: [TopicBlock] = [
    blockOnCallRotation, blockVendorContract, blockOnboardingMetrics, blockSupportBacklog,
    blockHiringPipeline, blockPerformanceRegression, blockDocumentationDebt, blockPricingExperiment,
    blockSecurityReview, blockRoadmapTradeoff, blockTestFlakiness, blockAccessibilityAudit,
    blockDataRetentionPolicy, blockMobileCrashTriage, blockLocalizationBacklog, blockDesignSystemDrift,
    blockApiVersioning, blockCustomerAdvisoryBoard, blockBuildTimes, blockContractorOffboarding,
    blockAnalyticsEventTaxonomy, blockFeatureFlagCleanup, blockDatabaseMigrationWindow,
    blockPushNotificationOptOut, blockBrandRefresh, blockIncidentPostmortemProcess,
    blockRecruitingReferralProgram, blockOfficeMoveLogistics, blockOpenSourceLicenceAudit,
    blockModelProviderEvaluation, blockChurnInterviewFindings, blockStorageCostGrowth,
    blockKeyboardShortcutConflicts, blockErrorBudgetPolicy,
  ]

  // MARK: - Scenarios

  /// Labels are drawn from the *plot* turns below, never from a shared block.
  ///
  /// A shared block appears in several scenarios, so a label taken from one would
  /// be scored against transcripts that legitimately never make that commitment.
  /// Plot turns belong to exactly one scenario and state each label once, which is
  /// what `testLabelsAreNotRepeatedThroughoutTheTranscript` enforces.
  ///
  /// Speakers name each other in dialogue because diarization gives anonymous
  /// `SPEAKER_00`-style labels, so a name is only recoverable if somebody says it.
  static let scenarios: [Scenario] = [
    // ---- single-pass -----------------------------------------------------
    Scenario(
      id: "standup-short",
      lengthClass: .single,
      labelledActionItems: [
        "Priya cuts the release notes by Friday",
        "Omar runs the rollback drill on Tuesday",
      ],
      mustKeepFacts: [
        "candidate 0.12.148 ships Thursday",
        "Omar owns the rollback drill",
      ],
      hallucinatedIfPresent: [
        "the team decided to rewrite the billing stack",
        "the contractor was let go this week",
        "the release slipped to next quarter",
      ],
      turns: [
        Turn(
          "SPEAKER_00",
          "Quick one before the standup proper. Candidate 0.12.148 ships Thursday, assuming nothing new turns up overnight."
        ),
        Turn(
          "SPEAKER_01",
          "Thursday works for me. Priya cuts the release notes by Friday, so they trail the build by a day."),
        Turn("SPEAKER_00", "A day behind is fine as long as they exist before anyone outside the team asks for them."),
        Turn("SPEAKER_02", "Omar runs the rollback drill on Tuesday, before the build rather than after it goes out."),
        Turn("SPEAKER_00", "Good. Last time we drilled after shipping, which taught us almost nothing worth having."),
        Turn("SPEAKER_01", "Anything blocking? I have nothing on my side beyond the notes themselves."),
        Turn(
          "SPEAKER_02",
          "Nothing blocking. Staging has been healthy for the first full week in a while, which I am not going to jinx."
        ),
        Turn(
          "SPEAKER_00", "Then that is it. Shorter than usual, which I will take as a good sign rather than a warning."),
      ]
    ),
    Scenario(
      id: "incident-debrief-short",
      lengthClass: .single,
      labelledActionItems: [
        "Mina pages the on-call for the remaining 5xx",
        "Chris files the incident document today",
      ],
      mustKeepFacts: [
        "the outage started at 09:12 UTC",
        "the cause was a bad ACL on the gateway",
      ],
      hallucinatedIfPresent: [
        "customer data was exfiltrated during the outage",
        "the team agreed to migrate to a different cloud provider",
        "production logs were deleted to recover",
      ],
      turns: [
        Turn(
          "SPEAKER_00",
          "Short debrief on this morning. The outage started at 09:12 UTC and ran about forty minutes end to end."),
        Turn("SPEAKER_01", "The cause was a bad ACL on the gateway. A rule change went out without the staging soak."),
        Turn(
          "SPEAKER_00",
          "Was the soak skipped deliberately, or did the pipeline simply let it through without complaint?"),
        Turn(
          "SPEAKER_01",
          "The pipeline let it through. The soak is advisory for ACL changes, which genuinely surprised me."),
        Turn("SPEAKER_02", "There is still a trickle from one region. Mina pages the on-call for the remaining 5xx."),
        Turn("SPEAKER_00", "Do that now rather than after this meeting. A trickle is usually how the next one starts."),
        Turn("SPEAKER_02", "Paging now."),
        Turn(
          "SPEAKER_01",
          "Chris files the incident document today, while the detail is still fresh enough to be accurate."),
        Turn("SPEAKER_00", "Include the advisory-soak part. That is the finding, not the ACL rule itself."),
        Turn("SPEAKER_01", "Agreed. The rule was the trigger and the missing gate is the actual cause."),
      ]
    ),

    // ---- medium ----------------------------------------------------------
    Scenario(
      id: "planning-medium",
      lengthClass: .medium,
      labelledActionItems: [
        "Sam ships the three-door onboarding prototype this cycle",
        "Lee records the user-test clips alongside it",
      ],
      mustKeepFacts: [
        "onboarding drops the purple accent",
        "the startup budget ceiling is 1.2 seconds",
      ],
      hallucinatedIfPresent: [
        "the onboarding redesign was cancelled outright",
        "an outside agency was hired to do the work",
        "the team moved to quarterly release trains",
      ],
      turns: [
        Turn(
          "SPEAKER_00",
          "Planning for the next two weeks. Three topics, and I would like an actual decision on all three."),
        Turn(
          "SPEAKER_01", "Onboarding first? The redesign has been sitting in review for eight days with no comments."),
        Turn("SPEAKER_00", "Onboarding first. Where did the purple accent land, are we keeping it or not?"),
        Turn(
          "SPEAKER_02",
          "Onboarding drops the purple accent. It fails contrast at the small sizes and we kept it for sentimental reasons."
        ),
        Turn(
          "SPEAKER_01", "Sentimental is fair, it has been there since the very first build. But it fails, so it goes."),
        Turn("SPEAKER_00", "Sam, where is the prototype? It was supposed to land before this meeting."),
        Turn(
          "SPEAKER_02",
          "Sam ships the three-door onboarding prototype this cycle. The scaffolding is done and the copy is what is slow."
        ),
        Turn(
          "SPEAKER_01",
          "Lee records the user-test clips alongside it, so we can watch people rather than speculate about them."),
        Turn("SPEAKER_00", "Five users or ten? Five tells us about the obvious problems and very little else."),
        Turn(
          "SPEAKER_01", "Five to start. If all five trip on the same thing we do not need another five to confirm it."),
      ] + blockOnboardingMetrics.turns + blockRoadmapTradeoff.turns + [
        Turn("SPEAKER_00", "Last thing. Startup has drifted and nobody noticed until it was nearly double."),
        Turn(
          "SPEAKER_02",
          "Then set a number. The startup budget ceiling is 1.2 seconds and anything above it fails the build."),
        Turn(
          "SPEAKER_01",
          "Generous against where we are today, but generous is the point. It stops the slow drift rather than the current value."
        ),
      ] + blockPerformanceRegression.turns
    ),
    Scenario(
      id: "vendor-and-support-medium",
      lengthClass: .medium,
      labelledActionItems: [
        "Jordan gets both vendor numbers in writing before any decision",
        "Nadia reads the remaining hundred sync tickets before anyone scopes a rewrite",
      ],
      mustKeepFacts: [
        "the vendor wants an eighteen percent increase",
        "support backlog is at 210 open tickets",
      ],
      hallucinatedIfPresent: [
        "the vendor contract was terminated on the call",
        "three additional support engineers were approved",
        "the sync subsystem rewrite was scheduled to begin",
      ],
      turns: [
        Turn("SPEAKER_00", "Two topics today, and both of them are about money once you follow them far enough.")
      ] + blockVendorContract.turns + blockSupportBacklog.turns + [
        Turn(
          "SPEAKER_00", "To be explicit about who owns what, because last time this got vague immediately afterwards."),
        Turn(
          "SPEAKER_01",
          "Jordan gets both vendor numbers in writing before any decision. I am not arguing this from memory again."),
        Turn(
          "SPEAKER_02",
          "Nadia reads the remaining hundred sync tickets before anyone scopes a rewrite off a ticket count."),
      ] + blockOnCallRotation.turns
    ),

    // ---- long (forces map+reduce on every engine we select) ---------------
    Scenario(
      id: "quarterly-review-long",
      lengthClass: .long,
      labelledActionItems: [
        "Alex rewrites the role scope in one paragraph tonight",
        "Tomas schedules the token rotation fix as real scheduled work",
        "Ines starts the trial-length test in parallel rather than after",
      ],
      mustKeepFacts: [
        "session tokens do not rotate on privilege change",
        "the pricing result is flat between the two tiers",
      ],
      hallucinatedIfPresent: [
        "the company confirmed a customer data breach",
        "the pricing experiment showed a clear winner",
        "the free tier is being shut down",
      ],
      turns: [
        Turn(
          "SPEAKER_00",
          "This is the long one. Quarterly review, so we are going wide rather than deep on any single item."),
        Turn("SPEAKER_01", "How long do we have? Wide and unbounded is exactly how these turn into three hours."),
        Turn("SPEAKER_00", "Ninety minutes. If a topic needs more than ten we take it somewhere else and move on."),
      ] + blockSecurityReview.turns + blockPricingExperiment.turns + blockHiringPipeline.turns
        + blockPerformanceRegression.turns + blockTestFlakiness.turns + blockAccessibilityAudit.turns
        + blockDocumentationDebt.turns + blockDataRetentionPolicy.turns + blockMobileCrashTriage.turns
        + blockLocalizationBacklog.turns + blockDesignSystemDrift.turns + blockApiVersioning.turns
        + blockCustomerAdvisoryBoard.turns + blockBuildTimes.turns + blockContractorOffboarding.turns
        + blockAnalyticsEventTaxonomy.turns + blockFeatureFlagCleanup.turns
        + blockStorageCostGrowth.turns + blockKeyboardShortcutConflicts.turns + [
          Turn("SPEAKER_00", "That is the lot. Three things I am holding people to, and I will say them out loud now."),
          Turn(
            "SPEAKER_01", "Alex rewrites the role scope in one paragraph tonight, before the vote happens tomorrow."),
          Turn(
            "SPEAKER_02",
            "Tomas schedules the token rotation fix as real scheduled work, not squeezed into a Friday afternoon."),
          Turn(
            "SPEAKER_00",
            "Ines starts the trial-length test in parallel rather than after, because sequential costs us a month."),
        ]
    ),
    Scenario(
      id: "eng-allhands-long",
      lengthClass: .long,
      labelledActionItems: [
        "Dana instruments startup with a trace on every build",
        "Sam rewrites the integration setup document and deletes unverifiable steps",
        "Chris assigns the accessibility fixes today rather than agreeing they matter",
      ],
      mustKeepFacts: [
        "wrong documentation costs more than none",
        "the escalation policy pages an alias nobody reads",
      ],
      hallucinatedIfPresent: [
        "the security audit found no issues at all",
        "search was cut from the roadmap entirely",
        "the accessibility work was deferred to next year",
      ],
      turns: [
        Turn(
          "SPEAKER_00",
          "Engineering all-hands. Less decision-making than usual and more getting everybody current on the same facts."
        ),
        Turn(
          "SPEAKER_02", "Are we doing questions throughout or at the end? Last time the end meant never, in practice."),
        Turn("SPEAKER_00", "Throughout. If it runs long that is a better problem than people leaving here uninformed."),
      ] + blockDatabaseMigrationWindow.turns + blockPushNotificationOptOut.turns + blockBrandRefresh.turns
        + blockIncidentPostmortemProcess.turns + blockRecruitingReferralProgram.turns
        + blockOfficeMoveLogistics.turns + blockOpenSourceLicenceAudit.turns
        + blockModelProviderEvaluation.turns + blockChurnInterviewFindings.turns
        + blockStorageCostGrowth.turns + blockKeyboardShortcutConflicts.turns
        + blockErrorBudgetPolicy.turns + blockDocumentationDebt.turns + blockAccessibilityAudit.turns
        + blockOnCallRotation.turns + blockRoadmapTradeoff.turns + [
          Turn(
            "SPEAKER_00",
            "Three things leaving this room with a name attached, and I will repeat them so nobody has to guess."),
          Turn(
            "SPEAKER_01",
            "Dana instruments startup with a trace on every build, so we stop discovering regressions quarterly."),
          Turn(
            "SPEAKER_02",
            "Sam rewrites the integration setup document and deletes unverifiable steps rather than leaving them to rot."
          ),
          Turn(
            "SPEAKER_00",
            "Chris assigns the accessibility fixes today rather than agreeing they matter and moving on again."),
        ]
    ),
  ]

  // MARK: - Scoring helpers

  /// Content words, lowercased, with stopwords and punctuation removed.
  ///
  /// Substring matching scored "Priya: release notes, Friday" as a miss against
  /// "Priya will cut the release notes by Friday", which made every recall number
  /// a lower bound under paraphrase — the exact thing a summarizer is supposed to do.
  ///
  /// Number-words and inflection are folded before the set is built: a model that
  /// writes "18%" against a label of "eighteen percent", or "schedule" against
  /// "schedules", is not a miss. NaturalLanguage's lemmatizer is not used; it
  /// is not stable across macOS versions.
  static func contentWords(_ text: String) -> Set<String> {
    let stopwords: Set<String> = [
      "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "had", "has", "have", "he",
      "her", "his", "i", "in", "is", "it", "its", "of", "on", "or", "our", "she", "that", "the",
      "their", "them", "they", "this", "to", "was", "we", "were", "will", "with", "you", "your",
    ]
    var cleaned = ""
    cleaned.reserveCapacity(text.count)
    for character in text.lowercased() {
      if character == "%" {
        cleaned.append(" percent ")
      } else if character.isLetter || character.isNumber {
        cleaned.append(character)
      } else {
        cleaned.append(" ")
      }
    }
    let folded = foldNumberWords(cleaned.split(separator: " ").map(String.init))
    return Set(
      folded
        .map { token in token.allSatisfy(\.isNumber) ? token : conservativeStem(token) }
        .filter { token in
          !stopwords.contains(token) && (token.count > 1 || token.allSatisfy(\.isNumber))
        }
    )
  }

  /// Fraction of the label's content words present in `produced`.
  ///
  /// Asymmetric on purpose: a summary may add words, but a summary that drops
  /// the label's nouns has not captured it.
  static func containment(label: String, produced: String) -> Double {
    let labelWords = contentWords(label)
    guard !labelWords.isEmpty else { return 0 }
    let producedWords = contentWords(produced)
    return Double(labelWords.intersection(producedWords).count) / Double(labelWords.count)
  }

  /// Two-thirds of the label's content words. Tolerates paraphrase and dropped
  /// connectives; rejects a summary that merely shares a name.
  static let matchThreshold = 0.67

  static func matches(label: String, produced: String) -> Bool {
    containment(label: label, produced: produced) >= matchThreshold
  }

  /// Whether `banned` is claimed by a single sentence or bullet of `produced`.
  ///
  /// Containment against a whole overview+sections body (~2,000 characters) is
  /// how "the pricing experiment showed a clear winner" fired on a summary that
  /// said the pricing test was flat: `pricing`, `experiments`, `showed`, and
  /// `clear` (from "clear ownership") each occurred somewhere. A claim lives in
  /// a sentence, so presence means one unit supports it.
  static func claims(_ banned: String, in produced: String) -> Bool {
    scoringUnits(in: produced).contains { matches(label: banned, produced: $0) }
  }

  /// Produced action that is, after whitespace and case folding, a contiguous
  /// substring of one transcript turn, or that contains a run of at least
  /// `verbatimRunLength` words copied from one turn.
  ///
  /// `action_support` rewards this by construction (the copied span is in the
  /// transcript). This flag reports the copying instead of pretending a
  /// lexical tweak can tell it apart from an attributed paraphrase.
  static let verbatimRunLength = 12

  static func isVerbatimCopy(_ action: String, of turns: [Turn]) -> Bool {
    let needle = collapsedWhitespace(action)
    guard !needle.isEmpty else { return false }
    let actionWords = needle.split(separator: " ").map(String.init)
    for turn in turns {
      let haystack = collapsedWhitespace(turn.text)
      if haystack.contains(needle) { return true }
      let turnWords = haystack.split(separator: " ").map(String.init)
      if containsCopiedRun(actionWords, in: turnWords, length: verbatimRunLength) { return true }
    }
    return false
  }

  // MARK: - Normalization

  private static let onesValues: [String: Int] = [
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
  ]

  private static let tensValues: [String: Int] = [
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
    "ninety": 90,
  ]

  /// Cardinals zero..ninety-nine plus hundred/thousand compounds. "and" between
  /// magnitude and remainder is consumed ("two hundred and ten" → 210).
  private static func foldNumberWords(_ tokens: [String]) -> [String] {
    var folded: [String] = []
    var index = 0
    while index < tokens.count {
      if let parsed = parseNumberPhrase(tokens, startingAt: index) {
        folded.append(String(parsed.value))
        index += parsed.consumed
      } else {
        folded.append(tokens[index])
        index += 1
      }
    }
    return folded
  }

  private static func parseNumberPhrase(_ tokens: [String], startingAt start: Int) -> (
    value: Int, consumed: Int
  )? {
    var index = start
    var total = 0
    var current = 0
    var consumedAny = false

    func takeBelowHundred() -> Int? {
      guard index < tokens.count else { return nil }
      if let ones = onesValues[tokens[index]] {
        index += 1
        return ones
      }
      if let tens = tensValues[tokens[index]] {
        index += 1
        if index < tokens.count, let ones = onesValues[tokens[index]], ones > 0, ones < 10 {
          index += 1
          return tens + ones
        }
        return tens
      }
      return nil
    }

    // `afterMagnitude` is what lets a remainder attach: "two hundred ten" and
    // "two hundred and ten" are one number, but "one forty" is two tokens and
    // "five and ten" is two numbers. Summing every adjacent number word turned
    // "up from one forty" into 41.
    var afterMagnitude = false
    var tookSmall = false
    while index < tokens.count {
      if tokens[index] == "and", afterMagnitude, index + 1 < tokens.count,
        onesValues[tokens[index + 1]] != nil || tensValues[tokens[index + 1]] != nil
      {
        index += 1
        continue
      }
      if tokens[index] == "thousand" {
        consumedAny = true
        total += (current == 0 ? 1 : current) * 1000
        current = 0
        index += 1
        afterMagnitude = true
        tookSmall = false
        continue
      }
      if tokens[index] == "hundred" {
        consumedAny = true
        current = (current == 0 ? 1 : current) * 100
        index += 1
        afterMagnitude = true
        tookSmall = false
        continue
      }
      if !tookSmall, let small = takeBelowHundred() {
        current += small
        consumedAny = true
        afterMagnitude = false
        tookSmall = true
        continue
      }
      break
    }

    guard consumedAny else { return nil }
    return (total + current, index - start)
  }

  /// Plural / 3rd-person / -ed / -ing sufficient to fold schedule/schedules/
  /// scheduled/scheduling onto one token. Deterministic; no dictionary.
  private static func conservativeStem(_ word: String) -> String {
    if word.count <= 3 { return word }
    var stem = word
    if stem.hasSuffix("sses") {
      stem = String(stem.dropLast(2))
    } else if stem.hasSuffix("ies"), stem.count >= 5 {
      stem = String(stem.dropLast(3)) + "y"
    } else if stem.hasSuffix("s"), !stem.hasSuffix("ss"), stem.count >= 4 {
      stem = String(stem.dropLast())
    }

    if stem.count >= 6, stem.hasSuffix("ing"), hasVowel(String(stem.dropLast(3))) {
      stem = String(stem.dropLast(3))
    } else if stem.count >= 5, stem.hasSuffix("ed"), hasVowel(String(stem.dropLast(2))) {
      stem = String(stem.dropLast(2))
    }

    if stem.count >= 6, stem.hasSuffix("e") {
      stem = String(stem.dropLast())
    }
    return stem
  }

  private static func hasVowel(_ word: String) -> Bool {
    word.contains { "aeiou".contains($0) }
  }

  /// Lines, bullets and table cells always split. `.`, `!` and `?` split only
  /// when followed by whitespace or the end, so "0.12.148" and "1.2 seconds"
  /// stay inside the sentence that states them.
  private static func scoringUnits(in text: String) -> [String] {
    var units: [String] = []
    var current = ""
    let characters = Array(text)
    for (offset, character) in characters.enumerated() {
      let hardBreak = character.isNewline || character == "|" || character == "\u{2022}"
      let next = offset + 1 < characters.count ? characters[offset + 1] : " "
      let sentenceEnd = (character == "." || character == "!" || character == "?") && next.isWhitespace
      if hardBreak || sentenceEnd {
        units.append(current)
        current = ""
      } else {
        current.append(character)
      }
    }
    units.append(current)
    return
      units
      .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
      .filter { !$0.isEmpty }
  }

  private static func collapsedWhitespace(_ text: String) -> String {
    text.lowercased().split(whereSeparator: \.isWhitespace).joined(separator: " ")
  }

  private static func containsCopiedRun(_ actionWords: [String], in turnWords: [String], length: Int)
    -> Bool
  {
    guard actionWords.count >= length, turnWords.count >= length else { return false }
    var turnRuns: Set<String> = []
    for start in 0...(turnWords.count - length) {
      turnRuns.insert(turnWords[start..<(start + length)].joined(separator: " "))
    }
    for start in 0...(actionWords.count - length) {
      if turnRuns.contains(actionWords[start..<(start + length)].joined(separator: " ")) {
        return true
      }
    }
    return false
  }
}
