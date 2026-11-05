import Foundation

/// A sentence to say out loud with blanks the user fills in ("My name is ___ and I spend most of
/// my time ___."), matched against what was heard: the fixed words get checked off, the blanks
/// fill with the user's own words. Matching is fuzzy (recognizers mishear, people paraphrase) and
/// works for any language that separates words with spaces.
public struct GapSentence: Equatable, Sendable {
    /// One word of the template as shown, or a blank.
    public enum Part: Equatable, Sendable {
        case word(String)
        case blank
    }

    public let parts: [Part]

    /// `___` (two or more underscores) marks a blank.
    public init(_ template: String) {
        var parts: [Part] = []
        let pieces = template.components(separatedBy: "__")
        var previousWasBlank = false
        for (index, piece) in pieces.enumerated() {
            let text = piece.trimmingCharacters(in: CharacterSet(charactersIn: "_"))
            // "___." leaves the period behind: glue punctuation to the blank (nothing to say).
            for word in text.split(whereSeparator: \.isWhitespace) where !Self.tokens(String(word)).isEmpty {
                parts.append(.word(String(word)))
                previousWasBlank = false
            }
            if index < pieces.count - 1, !previousWasBlank {
                parts.append(.blank)
                previousWasBlank = true
            }
        }
        self.parts = parts
    }

    /// A sentence that is only a blank: "say anything".
    public static let free = GapSentence("___")

    /// What was said, laid over the template.
    public struct Match: Equatable, Sendable {
        public enum Piece: Equatable, Sendable {
            case word(String, heard: Bool)
            /// The user's words in this blank; empty while not said yet.
            case blank(String)
        }

        public let pieces: [Piece]

        public var fixedTotal: Int {
            pieces.count { if case .word = $0 { true } else { false } }
        }

        public var fixedHeard: Int {
            pieces.count { if case .word(_, true) = $0 { true } else { false } }
        }

        public var blanks: [String] {
            pieces.compactMap { if case let .blank(text) = $0 { text } else { nil } }
        }

        /// Most fixed words heard (recognizers drop the odd short word) and every blank has at
        /// least one word. A sentence that is only a blank needs a few words.
        public var isComplete: Bool {
            let filled = blanks.allSatisfy { !$0.isEmpty }
            guard fixedTotal > 0 else {
                return blanks.reduce(0) { $0 + $1.split(separator: " ").count } >= GapSentence.freeWords
            }
            return filled && fixedHeard * 10 >= fixedTotal * 6
        }

        /// 0…1: how much of the sentence is there.
        public var progress: Double {
            if isComplete { return 1 }
            let total = fixedTotal + blanks.count
            guard total > 0 else { return 0 }
            if fixedTotal == 0 {
                let words = blanks.reduce(0) { $0 + $1.split(separator: " ").count }
                return min(1, Double(words) / Double(GapSentence.freeWords))
            }
            return Double(fixedHeard + blanks.count { !$0.isEmpty }) / Double(total)
        }
    }

    static let freeWords = 3

    // MARK: Matching

    private enum Item {
        case token(String, part: Int)
        case blank(part: Int)
    }

    /// Aligns the spoken words to the template (an edit distance where blanks take any number of
    /// words for free), then reads off which fixed words were heard and what fills each blank.
    public func match(_ spoken: String) -> Match {
        var items: [Item] = []
        for (index, part) in parts.enumerated() {
            switch part {
            case let .word(word): items += Self.tokens(word).map { Item.token($0, part: index) }
            case .blank: items.append(.blank(part: index))
            }
        }
        // Tokens of what was said, each pointing back to the word it came from ("I'm" → i, am).
        var said: [(token: String, word: Int)] = []
        let words = spoken.split(whereSeparator: \.isWhitespace).map(String.init).suffix(Self.maximumWords)
        let shown = Array(words).map { $0.trimmingCharacters(in: .punctuationCharacters) }
        for (index, word) in words.enumerated() {
            said += Self.tokens(word).map { ($0, index) }
        }
        let path = align(items, said.map(\.token))

        var heard = Set<Int>()
        var fills: [Int: [Int]] = [:]
        for step in path {
            switch step {
            case let .match(item, _):
                if case let .token(_, part) = items[item] { heard.insert(part) }
            case let .fill(item, token):
                if case let .blank(part) = items[item], fills[part]?.last != said[token].word {
                    fills[part, default: []].append(said[token].word)
                }
            }
        }
        let pieces = parts.enumerated().map { index, part -> Match.Piece in
            switch part {
            case let .word(word): .word(word, heard: heard.contains(index))
            case .blank: .blank((fills[index] ?? []).map { shown[$0] }.filter { !$0.isEmpty }.joined(separator: " "))
            }
        }
        return Match(pieces: pieces)
    }

    private enum Step {
        case match(item: Int, token: Int)
        case fill(item: Int, token: Int)
    }

    private enum Move { case none, match, substitute, delete, insert, blank(Int) }

    /// Costs: a fuzzy match 0, a word not said or said differently 2–3, an extra word 2, words
    /// inside a blank 0. Ties go to the path with more matched words, then to words in the
    /// earlier blank (a name said so far belongs in the first gap, not the last).
    private func align(_ items: [Item], _ tokens: [String]) -> [Step] {
        let rows = items.count, columns = tokens.count
        let infinity = Int.max / 4
        let unit = 100_000, matched = 1000
        var ordinals: [Int: Int] = [:]
        for (index, item) in items.enumerated() {
            if case .blank = item { ordinals[index] = ordinals.count }
        }
        var cost = Array(repeating: Array(repeating: infinity, count: columns + 1), count: rows + 1)
        var move = Array(repeating: Array(repeating: Move.none, count: columns + 1), count: rows + 1)
        cost[0][0] = 0
        for row in 0 ... rows {
            for column in 0 ... columns where cost[row][column] < infinity {
                let here = cost[row][column]
                func relax(_ toRow: Int, _ toColumn: Int, _ value: Int, _ how: Move) {
                    if value < cost[toRow][toColumn] {
                        cost[toRow][toColumn] = value
                        move[toRow][toColumn] = how
                    }
                }
                if column < columns { relax(row, column + 1, here + 2 * unit, .insert) }
                guard row < rows else { continue }
                switch items[row] {
                case let .token(word, _):
                    relax(row + 1, column, here + 2 * unit, .delete)
                    if column < columns {
                        if Self.similar(word, tokens[column]) {
                            relax(row + 1, column + 1, here - matched, .match)
                        } else {
                            relax(row + 1, column + 1, here + 3 * unit, .substitute)
                        }
                    }
                case .blank:
                    let ordinal = ordinals[row] ?? 0
                    for end in column ... columns {
                        relax(row + 1, end, here + (end - column) * ordinal, .blank(end - column))
                    }
                }
            }
        }
        return backtrack(move, rows: rows, columns: columns)
    }

    private func backtrack(_ move: [[Move]], rows: Int, columns: Int) -> [Step] {
        var steps: [Step] = []
        var row = rows, column = columns
        while row > 0 || column > 0 {
            switch move[row][column] {
            case .match:
                steps.append(.match(item: row - 1, token: column - 1))
                row -= 1; column -= 1
            case .substitute:
                row -= 1; column -= 1
            case .delete:
                row -= 1
            case .insert:
                column -= 1
            case let .blank(count):
                for token in stride(from: column - 1, through: column - count, by: -1) {
                    steps.append(.fill(item: row - 1, token: token))
                }
                row -= 1; column -= count
            case .none:
                return steps.reversed()
            }
        }
        return steps.reversed()
    }

    static let maximumWords = 60

    /// Lowercased, accents and ß folded, English contractions spelled out, punctuation gone.
    static func tokens(_ word: String) -> [String] {
        var text = word.lowercased()
            .replacingOccurrences(of: "\u{2019}", with: "'")
            .replacingOccurrences(of: "ß", with: "ss")
            .folding(options: [.diacriticInsensitive], locale: nil)
        for (short, long) in [("n't", " not"), ("'m", " am"), ("'re", " are"), ("'ve", " have"), ("'ll", " will"), ("'d", " would")] {
            text = text.replacingOccurrences(of: short, with: long)
        }
        let kept = text.unicodeScalars.map { CharacterSet.alphanumerics.contains($0) || $0 == " " ? Character($0) : " " }
        return String(kept).split(separator: " ").map(String.init)
    }

    /// Same word, allowing for how recognizers and people bend it: short words exactly, longer
    /// ones within a letter or two, and different endings ("arbeite" / "arbeiten").
    static func similar(_ lhs: String, _ rhs: String) -> Bool {
        if lhs == rhs { return true }
        let shorter = min(lhs.count, rhs.count), longer = max(lhs.count, rhs.count)
        if shorter <= 2 { return false }
        if shorter >= 4, lhs.hasPrefix(rhs) || rhs.hasPrefix(lhs) { return true }
        let allowed = longer <= 4 ? 1 : longer <= 7 ? 2 : 3
        return longer - shorter <= allowed && distance(lhs, rhs) <= allowed
    }

    static func distance(_ lhs: String, _ rhs: String) -> Int {
        let lhs = Array(lhs), rhs = Array(rhs)
        var previous = Array(0 ... rhs.count)
        for (row, left) in lhs.enumerated() {
            var current = [row + 1] + Array(repeating: 0, count: rhs.count)
            for (column, right) in rhs.enumerated() {
                current[column + 1] = min(previous[column + 1] + 1, current[column] + 1, previous[column] + (left == right ? 0 : 1))
            }
            previous = current
        }
        return previous[rhs.count]
    }
}

/// The voice sample's progress follows the sentences: each finished one is a full step, the one
/// being spoken fills its step only part of the way until it is done.
public enum VoiceProgress {
    public static func fraction(completed: Int, total: Int, current: Double) -> Double {
        guard total > 0 else { return 0 }
        if completed >= total { return 1 }
        return (Double(completed) + min(0.9, max(0, current))) / Double(total)
    }
}
