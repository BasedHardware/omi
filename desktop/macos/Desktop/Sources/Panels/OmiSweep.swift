import Foundation
import GRDB

/// Which of the user's own stores a hit came out of.
enum SweepSource: String, Sendable, CaseIterable {
  case memory
  case screen
  case task
  case stagedTask
  case taskChat
  case insight
  case transcript

  /// What the model is told this source is. Written as the user's own thing, because
  /// that is what decides whether the answer is likely to be in it.
  var label: String {
    switch self {
    case .memory: return "memory"
    case .screen: return "screen history"
    case .task: return "task"
    case .stagedTask: return "suggested task"
    case .taskChat: return "task chat"
    case .insight: return "insight Omi extracted"
    case .transcript: return "something said out loud"
    }
  }

  /// How many lines this source may spend.
  ///
  /// Memories get more than the rest and are topped up to this even when the keywords
  /// miss. Measured live: asking "where did I go to graduate school" found nothing,
  /// because the stored memory says "M.S. in Applied Data Intelligence from San Jose
  /// State University" — no "graduate", no "school". The backend's semantic
  /// `search_memories` missed the same row, so widening did not save it either and Omi
  /// told the user it did not know something it plainly knew. Memories are few, short,
  /// and about the user by definition, so showing a recent sample beats matching them.
  var budget: Int {
    self == .memory ? 8 : OmiSweep.perSourceLimit
  }

  /// The tool that hydrates a hit from this source into full content.
  var hydrationHint: String {
    switch self {
    case .memory: return "search_memories or get_memories"
    case .screen: return "semantic_search, or execute_sql on screenshots"
    case .task, .stagedTask: return "get_tasks or search_tasks"
    case .taskChat: return "execute_sql on task_chat_messages"
    case .insight: return "execute_sql on proactive_extractions"
    case .transcript: return "search_conversations"
    }
  }
}

/// One line of the sweep: where something matching is, and just enough of it to tell
/// whether it is worth opening.
struct SweepHit: Sendable, Equatable {
  /// Namespaced so a ref can never be mistaken for a row id of another kind.
  let ref: String
  let source: SweepSource
  let title: String
  let preview: String
  /// BM25, lower is better. Kept for ordering only; never shown to the model, which
  /// would read a number it cannot calibrate as a confidence.
  let score: Double

  /// The score a row carries when the keywords never matched it and it is present only
  /// so the model can see what the source holds. Sorts after every real hit.
  static let inventoryScore = Double.greatestFiniteMagnitude

  /// Whether the question's own words found this, rather than it being shown as
  /// inventory. Evidence and inventory are not the same claim.
  var isKeywordMatch: Bool { score != Self.inventoryScore }
}

/// A keyword pass over every local store the user has, returning where things are
/// rather than what they say.
///
/// This exists because the two obvious designs both fail. Handing the model the full
/// contents of every source blows the context window and grows with the corpus. Handing
/// it only tools and trusting it to search was measured in this codebase and found
/// unreliable — see `ContextDirectorRetrievalHop`, where asking the model first whether
/// it wanted a lookup "proved a coin flip in live runs" while attaching the retrieval
/// delivered every time.
///
/// So the sweep is attached, not offered, and it returns a table of contents: seven
/// sources, three hits each, a 150-character preview per hit. That is a fixed ~3 KB no
/// matter how much history the user has. The model reads it to learn *where* the answer
/// lives, then spends its tool calls opening only what matters — the same two steps as
/// `grep -rl` followed by reading the one file it named.
enum OmiSweep {
  /// Matches `ContextDirectorRetrievalHop.perSourceResultLimit`: the same question of
  /// how many items a prompt can quote before recall stops paying for tokens.
  static let perSourceLimit = 3
  /// Shorter than the director's 400 because a sweep line is an address, not evidence.
  /// Anything the model wants to read properly it opens with a tool.
  static let maxPreviewLength = 150
  static let maxTitleLength = 120
  /// How many rows a source is asked for before near-duplicates are collapsed. Screen
  /// history is the reason: a browser tab strip is OCR'd into every screenshot taken in
  /// that window, so the top matches are routinely the same strip three times over.
  private static let candidateFetchLimit = 12
  /// Two hits whose previews agree over this many leading characters are the same thing
  /// seen twice, and the second one buys the model nothing.
  private static let duplicatePrefixLength = 60
  /// Only single characters are dropped on length. Shortness is a bad proxy for
  /// commonness — "w9", "ai", "id", "ssn" are the most specific words a question about
  /// the user's own paperwork contains, and a length floor of 3 threw all of them away.
  /// Commonness is what the stop list is for.
  private static let minimumTermLength = 2
  /// Words that would match everything the user has ever written. Verbs of asking
  /// ("put", "send", "save") earn their place here too: they are how a person phrases a
  /// request, and they appear in every note they have ever taken.
  private static let stopWords: Set<String> = [
    "the", "and", "for", "was", "what", "when", "where", "which", "who", "whom", "this",
    "that", "these", "those", "with", "from", "have", "has", "had", "you", "your", "my",
    "mine", "me", "our", "ours", "are", "were", "been", "being", "can", "could", "would",
    "should", "will", "shall", "did", "does", "done", "get", "got", "give", "show", "tell",
    "find", "look", "about", "into", "onto", "out", "off", "again", "all", "any", "some",
    "there", "their", "them", "they", "how", "why", "please", "just", "now", "then",
    "put", "one", "two", "set", "make", "made", "need", "want", "know", "say", "said",
    "use", "used", "see", "saw", "let", "was", "his", "her", "its", "not", "but", "own",
    "back", "over", "than", "too", "very", "also", "much", "many", "more", "most",
    "is", "it", "in", "on", "at", "to", "of", "as", "by", "or", "if", "so", "up", "we",
    "do", "be", "an", "am", "he", "us", "go", "went", "goes", "come", "came",
  ]

  // MARK: - Running

  /// Sweep every local source for the question's terms. Never throws and never returns a
  /// partial failure: a source whose index is missing or corrupt contributes nothing, and
  /// the six that answered are still worth more than an error.
  static func run(query: String) async -> Result {
    guard let match = matchExpression(for: query) else { return Result(hits: [], memoryTotal: 0) }
    let (pool, _) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool else { return Result(hits: [], memoryTotal: 0) }

    // One read, one snapshot, seven index lookups. These are FTS5 b-tree probes bounded
    // to three rows each, so running them on separate connections would cost more in
    // pool contention than it could save.
    let outcome: Result =
      (try? await pool.read { db in
        Result(hits: Self.hits(matching: match, in: db), memoryTotal: Self.memoryTotal(in: db))
      }) ?? Result(hits: [], memoryTotal: 0)

    log(
      "OmiSweep: \(outcome.hits.count) hit(s) across "
        + "\(Set(outcome.hits.map(\.source)).count) source(s), \(outcome.memoryTotal) memories")
    return outcome
  }

  /// A sweep and what it could not fit.
  struct Result: Sendable, Equatable {
    let hits: [SweepHit]
    let memoryTotal: Int
  }

  /// Every source swept against one open database. Separate from `run` so a test can
  /// drive the real queries against a real schema instead of only the query builder.
  static func hits(matching match: String, in db: Database) -> [SweepHit] {
    SweepSource.allCases.flatMap { source in
      (try? fetch(source, matching: match, in: db)) ?? []
    }
  }

  /// How many memories exist, so the prompt can say how much of them the sweep is
  /// showing. Without it the model reads eight lines as the whole store: measured live,
  /// it answered "I couldn't find the exact dates" while the memory holding them sat
  /// just outside the budget, and it never called get_memories because nothing told it
  /// there was more to read.
  static func memoryTotal(in db: Database) -> Int {
    (try? Int.fetchOne(
      db, sql: "SELECT COUNT(*) FROM memories WHERE deleted = 0 AND isDismissed = 0")) ?? 0
  }

  private static func fetch(
    _ source: SweepSource, matching match: String, in db: Database
  ) throws -> [SweepHit] {
    let rows = try Row.fetchAll(db, sql: sql(for: source), arguments: [match, candidateFetchLimit])
    let budget = source.budget
    var kept: [SweepHit] = []
    var seen = Set<String>()
    for row in rows {
      guard kept.count < budget else { break }
      let body = ((row["preview"] as String?) ?? "")
        .trimmingCharacters(in: .whitespacesAndNewlines)
      guard !body.isEmpty else { continue }
      let preview = clip(body, to: maxPreviewLength)
      guard seen.insert(duplicateKey(preview)).inserted else { continue }
      kept.append(
        SweepHit(
          ref: "\(source.rawValue):\(row["id"] as Int64? ?? 0)",
          source: source,
          title: clip((row["title"] as String?) ?? "", to: maxTitleLength),
          preview: preview,
          score: (row["score"] as Double?) ?? 0))
    }
    guard kept.count < budget, let fill = topUpSQL(for: source) else { return kept }
    // Room left after the keyword pass, so fill it with what is newest. A source that
    // matched nothing still shows the model what it holds, which is the difference
    // between "you have no such thing" and "these words did not match".
    let recent = try Row.fetchAll(db, sql: fill, arguments: [budget - kept.count + seen.count])
    for row in recent {
      guard kept.count < budget else { break }
      let body = ((row["preview"] as String?) ?? "")
        .trimmingCharacters(in: .whitespacesAndNewlines)
      guard !body.isEmpty else { continue }
      let preview = clip(body, to: maxPreviewLength)
      guard seen.insert(duplicateKey(preview)).inserted else { continue }
      kept.append(
        SweepHit(
          ref: "\(source.rawValue):\(row["id"] as Int64? ?? 0)",
          source: source,
          title: clip((row["title"] as String?) ?? "", to: maxTitleLength),
          preview: preview,
          // Ranked after every keyword hit: this one matched nothing, it is merely here.
          score: SweepHit.inventoryScore))
    }
    return kept
  }

  /// The newest rows of a source, for filling a budget the keywords left unspent. Only
  /// memories have one: every other source is large, noisy, or both, and its newest rows
  /// have no particular claim on a question.
  private static func topUpSQL(for source: SweepSource) -> String? {
    guard source == .memory else { return nil }
    return """
      SELECT id AS id, category AS title, content AS preview
      FROM memories WHERE deleted = 0 AND isDismissed = 0
      ORDER BY createdAt DESC LIMIT ?
      """
  }

  /// What makes two hits the same thing. Case and runs of whitespace differ between two
  /// OCR passes over the same pixels, so neither may decide it.
  nonisolated static func duplicateKey(_ preview: String) -> String {
    String(
      preview.lowercased()
        .split(whereSeparator: { $0.isWhitespace })
        .joined(separator: " ")
        .prefix(duplicatePrefixLength))
  }

  /// Each source's query has the same shape — id, title, preview, bm25 score — so one
  /// renderer can read all seven. Soft-deleted and dismissed rows are filtered here
  /// rather than in the FTS triggers, which must stay in lockstep with the table.
  private static func sql(for source: SweepSource) -> String {
    switch source {
    case .memory:
      return """
        SELECT m.id AS id, m.category AS title, m.content AS preview,
               bm25(memories_fts) AS score
        FROM memories m JOIN memories_fts ON memories_fts.rowid = m.id
        WHERE memories_fts MATCH ? AND m.deleted = 0 AND m.isDismissed = 0
        ORDER BY score ASC LIMIT ?
        """
    case .screen:
      // Omi's own windows are excluded, and the exclusion is load-bearing. Its nav bar
      // ("Chat Brain Tasks Rewind Apps Search what you've seen and heard") is OCR'd into
      // every screenshot of itself, so it matches almost any query and outranks real
      // hits; worse, a screenshot of the user asking Omi a question comes back as an
      // answer to that same question. Measured on a real 2,576-screenshot profile: of
      // the top three screen hits for four sample questions, all but one were Omi's own
      // chrome. `LIKE` is case-insensitive over ASCII, so this covers Omi, Omi Beta,
      // Omi Dev, and every omi-* named bundle.
      return """
        SELECT s.id AS id,
               COALESCE(s.appName, '') || COALESCE(' — ' || s.windowTitle, '') AS title,
               substr(s.ocrText, 1, 400) AS preview,
               bm25(screenshots_fts) AS score
        FROM screenshots s JOIN screenshots_fts ON screenshots_fts.rowid = s.id
        WHERE screenshots_fts MATCH ? AND COALESCE(s.appName, '') NOT LIKE 'omi%'
        ORDER BY score ASC LIMIT ?
        """
    case .task:
      return """
        SELECT a.id AS id,
               CASE WHEN a.completed = 1 THEN 'done' ELSE 'open' END AS title,
               a.description AS preview, bm25(action_items_fts) AS score
        FROM action_items a JOIN action_items_fts ON action_items_fts.rowid = a.id
        WHERE action_items_fts MATCH ? AND a.deleted = 0
        ORDER BY score ASC LIMIT ?
        """
    case .stagedTask:
      return """
        SELECT t.id AS id, COALESCE(t.category, '') AS title,
               t.description AS preview, bm25(staged_tasks_fts) AS score
        FROM staged_tasks t JOIN staged_tasks_fts ON staged_tasks_fts.rowid = t.id
        WHERE staged_tasks_fts MATCH ? AND t.deleted = 0
        ORDER BY score ASC LIMIT ?
        """
    case .taskChat:
      return """
        SELECT m.id AS id, COALESCE(m.sender, '') AS title,
               m.messageText AS preview, bm25(task_chat_messages_fts) AS score
        FROM task_chat_messages m
        JOIN task_chat_messages_fts ON task_chat_messages_fts.rowid = m.id
        WHERE task_chat_messages_fts MATCH ?
        ORDER BY score ASC LIMIT ?
        """
    case .insight:
      return """
        SELECT p.id AS id, COALESCE(p.type, '') AS title,
               p.content AS preview, bm25(proactive_extractions_fts) AS score
        FROM proactive_extractions p
        JOIN proactive_extractions_fts ON proactive_extractions_fts.rowid = p.id
        WHERE proactive_extractions_fts MATCH ? AND p.isDismissed = 0
        ORDER BY score ASC LIMIT ?
        """
    case .transcript:
      return """
        SELECT seg.id AS id, COALESCE(sess.title, '') AS title,
               seg.text AS preview, bm25(transcription_segments_fts) AS score
        FROM transcription_segments seg
        JOIN transcription_segments_fts ON transcription_segments_fts.rowid = seg.id
        LEFT JOIN transcription_sessions sess ON sess.id = seg.sessionId
        WHERE transcription_segments_fts MATCH ?
          AND COALESCE(sess.deleted, 0) = 0 AND COALESCE(sess.discarded, 0) = 0
        ORDER BY score ASC LIMIT ?
        """
    }
  }

  // MARK: - Query

  /// The question as an FTS5 expression, or nil when nothing in it is worth matching.
  ///
  /// Terms are OR'd, not AND'd. A spoken question carries words that appear nowhere in
  /// the stored text — "what's my portfolio link again" is five words of which one is a
  /// term — and AND would return nothing for every real question.
  nonisolated static func matchExpression(for query: String) -> String? {
    let terms =
      query
      .map { $0.isLetter || $0.isNumber ? $0 : " " }
      .map(String.init).joined()
      .split(separator: " ")
      .map { $0.lowercased() }
      .filter { $0.count >= minimumTermLength && !stopWords.contains($0) }
    guard !terms.isEmpty else { return nil }
    // Deduplicated in order: a repeated word adds query cost and changes no ranking.
    var seen = Set<String>()
    let unique = terms.filter { seen.insert($0).inserted }
    return unique.joined(separator: " OR ")
  }

  // MARK: - Rendering

  /// The sweep as the model reads it: one line per hit, grouped by source, with the tool
  /// that opens each kind. An empty sweep is stated rather than omitted — silence would
  /// read as "this step did not run", and the model must know the keywords missed so it
  /// widens the search instead of concluding the user has no such thing.
  nonisolated static func promptSection(_ result: Result) -> String {
    promptSection(hits: result.hits, memoryTotal: result.memoryTotal)
  }

  nonisolated static func promptSection(hits: [SweepHit], memoryTotal: Int = 0) -> String {
    guard !hits.isEmpty else {
      return """
        == KEYWORD SWEEP OF THE USER'S DATA ==
        No stored text matched the words in the question. This means the keywords missed,
        NOT that the user has no such thing — search by meaning instead, with
        search_memories, semantic_search, or search_conversations, before concluding
        anything is absent.
        """
    }
    let grouped = SweepSource.allCases.compactMap { source -> String? in
      let ofSource = hits.filter { $0.source == source }.sorted { $0.score < $1.score }
      guard !ofSource.isEmpty else { return nil }
      let lines = ofSource.map { hit in
        let name = hit.title.isEmpty ? "" : " (\(hit.title))"
        // Inventory is marked, because a line the question never matched is a different
        // claim from one it did, and an unmarked list invites the model to read the
        // whole thing as evidence.
        let mark = hit.isKeywordMatch ? "" : " ·also stored·"
        return "  [\(hit.ref)]\(name)\(mark) \(hit.preview)"
      }
      let shown = ofSource.count
      // Naming the remainder is what turns "nothing else exists" into "read the rest".
      let remainder =
        source == .memory && memoryTotal > shown
        ? " — showing \(shown) of \(memoryTotal); list_memories reads the other "
          + "\(memoryTotal - shown) in one call"
        : ""
      return "\(source.label) — open with \(source.hydrationHint)\(remainder):\n"
        + lines.joined(separator: "\n")
    }
    return """
      == KEYWORD SWEEP OF THE USER'S DATA ==
      Where the question's words appear in the user's own stores. Each line is an address
      and a fragment, not the whole thing: open what looks right with the named tool
      before answering from it. This sweep matched literal words only, so a source with no
      line here may still hold the answer under different wording. Lines marked
      ·also stored· did NOT match the question — they are simply what that source holds,
      and one of them may still answer it in words the question never used.

      \(grouped.joined(separator: "\n\n"))
      """
  }

  private nonisolated static func clip(_ text: String, to limit: Int) -> String {
    let flattened = text.split(whereSeparator: \.isNewline).joined(separator: " ")
      .trimmingCharacters(in: .whitespacesAndNewlines)
    guard flattened.count > limit else { return flattened }
    return String(flattened.prefix(limit)) + "\u{2026}"
  }
}

// MARK: - Hydration

extension OmiSweep {
  /// How much of one opened row the model gets. Generous next to a sweep preview and
  /// still bounded, because a screenshot's OCR text can run to tens of thousands of
  /// characters and only the first page of it is ever the answer.
  static let maxOpenedLength = 2_000
  /// Enough to answer from, few enough that opening everything is not a way around the
  /// sweep's budget.
  static let maxOpenedRefs = 8

  /// Read the full text behind sweep refs.
  ///
  /// This is the second half of grep: the sweep said where, this reads it. It exists so
  /// the model never has to write SQL to open its own search results — a hydration query
  /// is the same three lines for every source, and generating it costs a schema in the
  /// prompt and a class of malformed-query retries for nothing.
  static func open(refs: [String]) async -> String {
    let parsed = refs.prefix(maxOpenedRefs).compactMap(parse)
    guard !parsed.isEmpty else {
      return "No readable refs. A ref looks like memory:12 and comes from the sweep above."
    }
    let (pool, _) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool else { return "The local database is unavailable." }

    let sections: [String] =
      (try? await pool.read { db in
        parsed.map { ref, source, id in
          guard let row = try? Row.fetchOne(db, sql: openSQL(for: source), arguments: [id]),
            let body = (row["body"] as String?)?.trimmingCharacters(in: .whitespacesAndNewlines),
            !body.isEmpty
          else {
            return "[\(ref)] no longer present."
          }
          let when = (row["when"] as String?).map { " · \($0)" } ?? ""
          let context = (row["context"] as String?).flatMap { $0.isEmpty ? nil : " (\($0))" } ?? ""
          return "[\(ref)]\(context)\(when)\n\(clip(body, to: maxOpenedLength))"
        }
      }) ?? []

    log("OmiSweep: opened \(sections.count) of \(refs.count) requested ref(s)")
    return sections.isEmpty ? "Nothing behind those refs." : sections.joined(separator: "\n\n")
  }

  /// Every memory the sweep could not fit, read straight from the table it swept.
  ///
  /// The remainder line has to point at something local. Pointing it at `get_memories`
  /// was measured live: the model took the hint on the first turn, then spent four of
  /// its six turns re-calling a backend tool that never returned the row, and still
  /// answered "I couldn't find those dates" with the row sitting in the local table.
  /// What the sweep advertises and what the model can read are now the same store.
  static func remainingMemories() async -> String {
    let (pool, _) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool else { return "The local database is unavailable." }
    let rows: [Row] =
      (try? await pool.read { db in
        try Row.fetchAll(
          db,
          sql: """
            SELECT id, content FROM memories
            WHERE deleted = 0 AND isDismissed = 0
            ORDER BY createdAt DESC LIMIT ? OFFSET ?
            """,
          arguments: [maxListedMemories, SweepSource.memory.budget])
      }) ?? []
    guard !rows.isEmpty else { return "No memories beyond the ones already listed." }
    log("OmiSweep: listed \(rows.count) remaining memories")
    return rows.map { row in
      "[memory:\(row["id"] as Int64? ?? 0)] "
        + clip((row["content"] as String?) ?? "", to: maxOpenedLength)
    }.joined(separator: "\n")
  }

  /// One call returns the whole remainder, so there is never a second page to re-ask
  /// for. A retry loop costs turns the panel is spinning through.
  static let maxListedMemories = 60

  /// `<source>:<rowid>`, rejecting anything that is not one of our own namespaces. The
  /// refs come back through model output, so they are parsed rather than trusted.
  nonisolated static func parse(_ ref: String) -> (ref: String, source: SweepSource, id: Int64)? {
    let parts = ref.trimmingCharacters(in: .whitespaces).split(separator: ":")
    guard parts.count == 2, let source = SweepSource(rawValue: String(parts[0])),
      let id = Int64(parts[1])
    else { return nil }
    return (ref, source, id)
  }

  /// One row, opened. Every source answers with the same three columns so the caller
  /// renders them identically; `id` is bound, never interpolated.
  private static func openSQL(for source: SweepSource) -> String {
    switch source {
    case .memory:
      return """
        SELECT content AS body, category AS context, createdAt AS "when"
        FROM memories WHERE id = ?
        """
    case .screen:
      return """
        SELECT ocrText AS body,
               COALESCE(appName, '') || COALESCE(' — ' || windowTitle, '') AS context,
               timestamp AS "when"
        FROM screenshots WHERE id = ?
        """
    case .task:
      return """
        SELECT description AS body,
               CASE WHEN completed = 1 THEN 'done task' ELSE 'open task' END AS context,
               COALESCE(dueAt, createdAt) AS "when"
        FROM action_items WHERE id = ?
        """
    case .stagedTask:
      return """
        SELECT description AS body, 'suggested task' AS context, createdAt AS "when"
        FROM staged_tasks WHERE id = ?
        """
    case .taskChat:
      return """
        SELECT messageText AS body, sender AS context, createdAt AS "when"
        FROM task_chat_messages WHERE id = ?
        """
    case .insight:
      return """
        SELECT content AS body, COALESCE(type, '') AS context, createdAt AS "when"
        FROM proactive_extractions WHERE id = ?
        """
    case .transcript:
      // The neighbours are the point: one segment is a sentence, and the answer is
      // usually the exchange around it rather than the line that matched.
      return """
        SELECT (SELECT group_concat(n.text, ' ') FROM transcription_segments n
                WHERE n.sessionId = seg.sessionId
                  AND n.segmentOrder BETWEEN seg.segmentOrder - 4 AND seg.segmentOrder + 4)
                 AS body,
               COALESCE(sess.title, 'conversation') AS context,
               sess.startedAt AS "when"
        FROM transcription_segments seg
        LEFT JOIN transcription_sessions sess ON sess.id = seg.sessionId
        WHERE seg.id = ?
        """
    }
  }
}
