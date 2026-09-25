//
//  SearchRanking.swift — how a page of screens and a page of spoken lines become **one** list.
//
//  The panel reads two halves (`RewindQueries.search` for what was on screen,
//  `ScreenSearchQueries.conversations` for what was said) and shows one answer. Everything about how
//  those two are ordered against each other lives here, as pure functions over values, because it is
//  the part of the surface that is invisible in a screenshot and impossible to eyeball: a ranking is
//  only ever wrong *relative to* an answer nobody can see.
//
//  # The rule
//
//  **Coverage first, recency second, and neither source may crowd out the other.**
//
//  1. **Coverage** — the fraction of the distinct words the user typed that appear in the hit's own
//     text. For a screen that is its window title, its app name and the matched OCR/accessibility
//     text; for a spoken line it is the words themselves. It is the one signal that means the same
//     thing on both sides, which is the whole reason it is the primary key: bm25 scores from
//     `frames_fts` and `segments_fts` are not comparable numbers, and comparing them anyway is how a
//     ranking silently becomes a coin flip. `Queries.recall` reaches the same conclusion for the MCP
//     surface and blends the two the same way round.
//  2. **Recency** breaks coverage ties, newest first. With nothing typed there are no terms, every
//     hit covers everything, and the order collapses to pure recency — which is exactly what "show
//     me what this Mac has captured" should be.
//  3. **The run cap** stops the denser source from filling the page. Screen capture writes a frame
//     every three seconds; speech writes a line a sentence. A pure merge on time is therefore a page
//     of screenshots on any normal machine, and the conversation the user was searching for is on
//     page four — which is the same failure `Queries`' moment-collapsing exists to prevent, in a
//     different costume. So no kind may take more than `maximumRun` cards in a row while the other
//     still has something to show.
//
//  Ties on both signals put speech before the screen it was said in front of, matching `Queries`'
//  own tie-break so the two surfaces never disagree about which of two simultaneous rows leads.
//

import Foundation

enum SearchRanking {

    /// The longest unbroken run of one kind, in cards.
    ///
    /// Two full grid rows. Expressed from the grid rather than as a bare number because that is what
    /// sets it: the cap exists so that a reader who has not scrolled has seen both kinds, and "what
    /// is on screen" is measured in rows. One row would be too eager — it would interleave a
    /// conversation into a page where twelve screens genuinely are the better answer; three rows is
    /// most of the visible panel, which is no cap at all.
    static let maximumRun = SearchLayout.resultColumns * 2

    // MARK: - Scoring

    /// A hit and the one comparable number the order is built from.
    struct Scored: Equatable {
        let moment: SearchMoment
        /// 0…1. Never zero — see `coverage(of:terms:)`.
        let coverage: Double
    }

    /// **The merge.** Both inputs arrive newest-first from SQL; the result is at most `limit` cards.
    ///
    /// Takes the query rather than pre-computed terms so a caller cannot score one half against a
    /// different reading of the question than the other.
    static func merge(
        screens: [SearchMoment],
        conversations: [SearchMoment],
        query: String,
        limit: Int
    ) -> [SearchMoment] {
        guard limit > 0 else { return [] }
        let terms = words(in: query)
        let left = order(screens, terms: terms)
        let right = order(conversations, terms: terms)

        var result: [SearchMoment] = []
        result.reserveCapacity(min(limit, left.count + right.count))
        var screenIndex = 0
        var spokenIndex = 0
        var runKind: SearchMoment.Kind?
        var run = 0

        while result.count < limit, screenIndex < left.count || spokenIndex < right.count {
            let takeScreen: Bool
            if spokenIndex >= right.count {
                takeScreen = true
            } else if screenIndex >= left.count {
                takeScreen = false
            } else if run >= maximumRun, let runKind {
                // The cap only ever *yields*: it hands the slot to the other kind, which by
                // construction still has cards, and never invents an ordering of its own.
                takeScreen = runKind != .screen
            } else {
                takeScreen = leads(left[screenIndex], right[spokenIndex])
            }

            let picked = takeScreen ? left[screenIndex].moment : right[spokenIndex].moment
            if takeScreen { screenIndex += 1 } else { spokenIndex += 1 }

            if picked.kind == runKind {
                run += 1
            } else {
                runKind = picked.kind
                run = 1
            }
            result.append(picked)
        }
        return result
    }

    /// One kind's page, best first. Exposed so the ordering inside a half is assertable on its own.
    static func order(_ moments: [SearchMoment], terms: [String]) -> [Scored] {
        moments
            .map { Scored(moment: $0, coverage: coverage(of: $0.relevanceText, terms: terms)) }
            .sorted(by: leads)
    }

    /// Which of two scored hits comes first. Total and deterministic: two hits are never "equal",
    /// so the order cannot depend on the sort's stability.
    private static func leads(_ lhs: Scored, _ rhs: Scored) -> Bool {
        if lhs.coverage != rhs.coverage { return lhs.coverage > rhs.coverage }
        if lhs.moment.capturedAt != rhs.moment.capturedAt {
            return lhs.moment.capturedAt > rhs.moment.capturedAt
        }
        if lhs.moment.kind != rhs.moment.kind {
            // Speech reads better before the screen it was said in front of — the same tie-break
            // `Queries.kindRank` applies to the MCP answer.
            return lhs.moment.kind == .conversation
        }
        return lhs.moment.rowId > rhs.moment.rowId
    }

    // MARK: - Coverage

    /// Fraction of the distinct typed words this text contains.
    ///
    /// **Never zero.** A hit is in the page because FTS matched it, so a zero here would only ever
    /// mean this cheap tokenizer and the porter-stemmed index disagreed — and an under-credited hit
    /// is the direction that costs a true match its place. One word's worth of credit is the floor,
    /// exactly as `Queries.coverage` floors it for the same reason.
    static func coverage(of text: String, terms: [String]) -> Double {
        guard !terms.isEmpty else { return 1 }
        let tokens = Set(words(in: text))
        let matched = terms.filter { term in
            tokens.contains(term) || tokens.contains { inflected($0, matches: term) }
        }.count
        return Double(max(matched, 1)) / Double(terms.count)
    }

    /// Lowercased distinct alphanumeric words, in the order they appear.
    ///
    /// Deliberately **not** a re-implementation of `Queries`' FTS tokenizer, and it does not need to
    /// be one: the index has already decided *which* rows are in the page, and this decides only how
    /// they are ordered relative to each other. A cheap, obvious, testable split is the right tool
    /// for that, where a second copy of the stemming rules would be a second thing to keep in sync
    /// with SQLite's.
    static func words(in text: String) -> [String] {
        var found: [String] = []
        var seen: Set<String> = []
        var token = ""

        func flush() {
            guard !token.isEmpty else { return }
            let word = token.lowercased()
            token = ""
            guard seen.insert(word).inserted else { return }
            found.append(word)
        }

        for scalar in text.unicodeScalars {
            if CharacterSet.alphanumerics.contains(scalar) {
                token.unicodeScalars.append(scalar)
            } else {
                flush()
            }
        }
        flush()
        return found
    }

    /// The suffixes the porter-stemmed index folds away but a plain comparison would not.
    private static let inflectionSuffixes: Set<String> = ["s", "es", "d", "ed", "ing", "ly", "er", "ers"]

    /// Deliberately narrower than a prefix test, and for a measured reason: `Queries` records that
    /// crediting incidental prefixes is how a browser bookmark bar came to outrank a real match
    /// ("pack" must not be paid for "package"). The same rule holds here or the two surfaces rank the
    /// same corpus differently.
    private static func inflected(_ token: String, matches term: String) -> Bool {
        let (longer, shorter) = token.count >= term.count ? (token, term) : (term, token)
        guard shorter.count >= 3, longer.count > shorter.count, longer.hasPrefix(shorter) else {
            return false
        }
        return inflectionSuffixes.contains(String(longer.dropFirst(shorter.count)))
    }
}
