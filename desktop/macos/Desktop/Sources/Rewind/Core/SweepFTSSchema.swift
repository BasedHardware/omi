import Foundation
import GRDB

/// Keyword indexes for the two sources that never had one.
///
/// Five tables already carry an FTS5 index; `memories` and `transcription_segments` were
/// searched with `content LIKE '%term%'` instead, which cannot rank, cannot match a
/// phrase, and cannot answer a two-word query. Those are the two sources a question about
/// the user's own life lands in most often, so a sweep across everything was only as good
/// as its two weakest matchers.
///
/// Both indexes are external-content (`content=`/`content_rowid=`): the rows stay where
/// they are, and dropping either virtual table is a complete rollback.
enum SweepFTSSchema {
  static func registerMigration(on migrator: inout DatabaseMigrator) {
    migrator.registerMigration("createMemoriesFTS") { db in
      try installMemoriesFTS(db)
    }
    migrator.registerMigration("createTranscriptSegmentsFTS") { db in
      try installTranscriptSegmentsFTS(db)
    }
  }

  // MARK: - memories

  /// `deleted` and `isDismissed` are not indexed: FTS5 external-content triggers fire on
  /// every write, and filtering there would leave the index disagreeing with the table
  /// after an undelete. The sweep joins back to `memories` and filters the flags in SQL.
  static func installMemoriesFTS(_ db: Database) throws {
    try dropMemoriesFTS(db)
    try db.execute(
      sql: """
        CREATE VIRTUAL TABLE memories_fts USING fts5(
            content,
            content='memories',
            content_rowid='id',
            tokenize='unicode61'
        )
        """)
    try db.execute(
      sql: """
        CREATE TRIGGER memories_fts_ai AFTER INSERT ON memories BEGIN
            INSERT INTO memories_fts(rowid, content) VALUES (new.id, new.content);
        END
        """)
    try db.execute(
      sql: """
        CREATE TRIGGER memories_fts_ad AFTER DELETE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, content)
            VALUES ('delete', old.id, old.content);
        END
        """)
    try db.execute(
      sql: """
        CREATE TRIGGER memories_fts_au AFTER UPDATE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, content)
            VALUES ('delete', old.id, old.content);
            INSERT INTO memories_fts(rowid, content) VALUES (new.id, new.content);
        END
        """)
    try db.execute(sql: "INSERT INTO memories_fts(rowid, content) SELECT id, content FROM memories")
  }

  static func dropMemoriesFTS(_ db: Database) throws {
    try db.execute(sql: "DROP TRIGGER IF EXISTS memories_fts_ai")
    try db.execute(sql: "DROP TRIGGER IF EXISTS memories_fts_ad")
    try db.execute(sql: "DROP TRIGGER IF EXISTS memories_fts_au")
    try db.execute(sql: "DROP TABLE IF EXISTS memories_fts")
  }

  // MARK: - transcription_segments

  static func installTranscriptSegmentsFTS(_ db: Database) throws {
    try dropTranscriptSegmentsFTS(db)
    try db.execute(
      sql: """
        CREATE VIRTUAL TABLE transcription_segments_fts USING fts5(
            text,
            content='transcription_segments',
            content_rowid='id',
            tokenize='unicode61'
        )
        """)
    try db.execute(
      sql: """
        CREATE TRIGGER transcription_segments_fts_ai
        AFTER INSERT ON transcription_segments BEGIN
            INSERT INTO transcription_segments_fts(rowid, text) VALUES (new.id, new.text);
        END
        """)
    try db.execute(
      sql: """
        CREATE TRIGGER transcription_segments_fts_ad
        AFTER DELETE ON transcription_segments BEGIN
            INSERT INTO transcription_segments_fts(transcription_segments_fts, rowid, text)
            VALUES ('delete', old.id, old.text);
        END
        """)
    try db.execute(
      sql: """
        CREATE TRIGGER transcription_segments_fts_au
        AFTER UPDATE ON transcription_segments BEGIN
            INSERT INTO transcription_segments_fts(transcription_segments_fts, rowid, text)
            VALUES ('delete', old.id, old.text);
            INSERT INTO transcription_segments_fts(rowid, text) VALUES (new.id, new.text);
        END
        """)
    try db.execute(
      sql: """
        INSERT INTO transcription_segments_fts(rowid, text)
        SELECT id, text FROM transcription_segments
        """)
  }

  static func dropTranscriptSegmentsFTS(_ db: Database) throws {
    try db.execute(sql: "DROP TRIGGER IF EXISTS transcription_segments_fts_ai")
    try db.execute(sql: "DROP TRIGGER IF EXISTS transcription_segments_fts_ad")
    try db.execute(sql: "DROP TRIGGER IF EXISTS transcription_segments_fts_au")
    try db.execute(sql: "DROP TABLE IF EXISTS transcription_segments_fts")
  }
}
