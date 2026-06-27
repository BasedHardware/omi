# Screenshot Embedding Migration Strategy

## Overview

This document explains how we handle embedding migrations for existing users when embedding logic changes.

## Current Status (Feb 2026)

- **Embedding Model**: Gemini `gemini-embedding-001` (3072 dimensions by default)
- **Task Types**:
  - Documents: `RETRIEVAL_DOCUMENT` (for screenshot embeddings)
  - Queries: `RETRIEVAL_QUERY` (for search queries)
- **Granularity**: One embedding per screenshot (concatenated OCR text with app context)

## Migration History

### Migration: `fullEmbeddingBackfillV2`

**When**: Feb 11, 2026
**Why**: Ensure all users get fresh, correct Gemini embeddings after test phase

**What it does**:
1. Clears ALL existing screenshot embeddings
2. Resets backfill status to `completed = 0, processedCount = 0`
3. Triggers full backfill on next app launch

**Affected users**:
- Users who installed during test phase (had 1000-item test limit)
- Users with incomplete backfills due to API errors
- Users with embeddings created with wrong parameters

**Database changes**:
```sql
UPDATE screenshots SET embedding = NULL WHERE embedding IS NOT NULL;

UPDATE migration_status
SET completed = 0, processedCount = 0, startedAt = datetime('now'), completedAt = NULL
WHERE name = 'screenshot_embedding_backfill';
```

## How Migrations Work

### 1. Migration Execution (One-Time)

Migrations are registered in `RewindDatabase.swift` using GRDB's migrator:

```swift
migrator.registerMigration("fullEmbeddingBackfillV2") { db in
    // Clear embeddings and reset backfill
}
```

Each migration runs **once per database** and is tracked in the `migration_status` table.

### 2. Backfill Process

After migration resets the backfill:

1. On next app launch, `OCREmbeddingService.backfillIfNeeded()` runs
2. Checks `migration_status` table for `screenshot_embedding_backfill` status
3. If `completed = 0`, starts processing missing embeddings
4. Processes in batches of 100 screenshots
5. Updates progress every 1000 items
6. Marks complete when all screenshots embedded

### 3. Real-Time Pipeline

New screenshots are embedded immediately in `RewindIndexer.swift`:

```swift
await OCREmbeddingService.shared.embedScreenshot(
    id: screenshotId,
    ocrText: ocrText,
    appName: appName,
    windowTitle: windowTitle
)
```

This ensures newly captured screenshots always have embeddings, independent of backfill status.

## Testing Migrations Locally

### Test Full Migration Flow

1. **Simulate old user with embeddings**:
   ```bash
   sqlite3 ~/Library/Application\ Support/Omi/omi.db "
   UPDATE migration_status
   SET completed = 1
   WHERE name = 'screenshot_embedding_backfill'
   "
   ```

2. **Check pre-migration state**:
   ```bash
   sqlite3 ~/Library/Application\ Support/Omi/omi.db "
   SELECT COUNT(*) FROM screenshots WHERE embedding IS NOT NULL
   "
   ```

3. **Run the app** (migration executes automatically)

4. **Verify migration ran**:
   ```bash
   sqlite3 ~/Library/Application\ Support/Omi/omi.db "
   SELECT completed, processedCount FROM migration_status
   WHERE name = 'screenshot_embedding_backfill'
   "
   ```
   Should show: `0|0` (reset for backfill)

5. **Watch backfill logs**:
   ```bash
   tail -f /private/tmp/omi.log | grep OCREmbedding
   ```

### Test Semantic Search

Use the test script after backfill completes:

```bash
python3 scripts/test_semantic_search.py
```

Expected: Top results should be semantically relevant to each query.

## Monitoring Backfill Progress

### Check Current Status

```bash
sqlite3 ~/Library/Application\ Support/Omi/omi.db "
SELECT
    completed,
    processedCount,
    startedAt,
    completedAt
FROM migration_status
WHERE name = 'screenshot_embedding_backfill'
"
```

### Check Embedding Coverage

```bash
sqlite3 ~/Library/Application\ Support/Omi/omi.db "
SELECT
    COUNT(*) as total_screenshots,
    SUM(CASE WHEN embedding IS NOT NULL THEN 1 ELSE 0 END) as with_embeddings,
    SUM(CASE WHEN embedding IS NULL AND ocrText IS NOT NULL THEN 1 ELSE 0 END) as missing_embeddings
FROM screenshots
"
```

## Future Migration Considerations

If we need to change embeddings again (new model, different granularity, etc.):

1. **Add a new migration** in `RewindDatabase.swift`
2. **Clear old embeddings**: `UPDATE screenshots SET embedding = NULL`
3. **Reset backfill**: Update `migration_status` for `screenshot_embedding_backfill`
4. **Update model/logic** in `OCREmbeddingService.swift` and `EmbeddingService.swift`
5. **Test locally** with the steps above
6. **Document** the change in this file

## Performance Notes

- **Backfill rate**: ~100 screenshots every 200ms = ~500 screenshots/minute
- **For 143,884 screenshots**: ~288 minutes (~4.8 hours)
- **Rate limiting**: Required by Gemini API to avoid quota errors
- **Memory usage**: Disk-based search, no in-memory index needed
- **User impact**: Backfill runs in background, doesn't block app usage

## Related Files

- `Desktop/Sources/Rewind/Core/RewindDatabase.swift` - Migration definitions
- `Desktop/Sources/Rewind/Services/OCREmbeddingService.swift` - Embedding & backfill logic
- `Desktop/Sources/ProactiveAssistants/Services/EmbeddingService.swift` - Gemini API calls
- `scripts/test_semantic_search.py` - Validation test suite
- `scripts/verify_embeddings.py` - Quick embedding check
