import Foundation

/// JavaScript-for-Automation sources used to read Apple Notes through the
/// scriptable Notes app instead of its private CoreData store.
///
/// Two hard performance rules are baked into these scripts, both measured on a
/// real 836-note library:
///
/// - Only *bulk* array accessors are used (`notes.id()`, `notes.name()`,
///   `notes.plaintext()`, …). A per-note `notes.byId(id)` round trip costs
///   ~0.31s **each**; the whole bulk export costs ~0.61s.
/// - No `whose(...)` filtering. Server-side filtering measured *slower* than the
///   full export (0.84s vs 0.61s), so the manifest diff happens in Swift.
///
/// Caller-controlled bounds are passed through the process environment and read
/// with `ObjC.unwrap($.getenv(...))`. They are never string-interpolated into the
/// script text, so a caller value can never become executable JavaScript.
/// (`$.getenv(key).js` yields `undefined` — `ObjC.unwrap` is required.)
enum AppleNotesScript {
  /// Payload schema emitted by both scripts. Bumping this invalidates persisted
  /// sync state, forcing a full resync rather than a silent shape mismatch.
  static let schemaVersion = 1

  /// Environment key for the per-note body cap applied inside the script.
  static let maxBodyCharsEnvironmentKey = "OMI_NOTES_MAX_BODY_CHARS"

  /// Environment key for the folder-attribution cap. Folder names require a
  /// `folders[i].notes.id()` loop (~1.4s for 75 folders), so libraries above the
  /// cap export with `folderMode: "skipped"` rather than paying it.
  static let maxFoldersEnvironmentKey = "OMI_NOTES_MAX_FOLDERS"

  /// Cheap change-detection payload: `{"schema":1,"notes":[{id, modifiedAt}]}`.
  /// ~0.20s / 65KB on the reference library versus 0.61s / 857KB for the body
  /// export, which is why an unchanged manifest skips the body fetch entirely.
  static let manifest = #"""
    ObjC.import("stdlib");

    function omiIso(value) {
      if (!value) { return null; }
      try { return value.toISOString(); } catch (error) { return null; }
    }

    function run() {
      var notes = Application("Notes").notes;

      // Integrity guard: the bulk accessors are separate Apple Events, so a note
      // created or deleted between them shifts every parallel array. Re-reading
      // the id array and comparing turns that silent corruption into a
      // retryable error.
      var ids = notes.id();
      var modified = notes.modificationDate();
      var idsAfter = notes.id();
      if (ids.length !== idsAfter.length) {
        return JSON.stringify({ schema: 1, error: "concurrent_modification" });
      }
      for (var guardIndex = 0; guardIndex < ids.length; guardIndex++) {
        if (ids[guardIndex] !== idsAfter[guardIndex]) {
          return JSON.stringify({ schema: 1, error: "concurrent_modification" });
        }
      }

      var entries = [];
      for (var index = 0; index < ids.length; index++) {
        entries.push({ id: String(ids[index]), modifiedAt: omiIso(modified[index]) });
      }
      return JSON.stringify({ schema: 1, notes: entries });
    }
    """#

  /// Full body export:
  /// `{"schema":1,"lockedSkipped":N,"folderMode":"mapped|skipped","notes":[…]}`.
  ///
  /// Password-protected notes report a readable `name()` but an empty
  /// `plaintext()` (no throw, no prompt); they are skipped and counted rather
  /// than imported as empty notes. `every note` already excludes Recently
  /// Deleted, and bulk `notes.container.name()` returns null for every note —
  /// folder names only come from the folder → note-id loop below.
  static let fullExport = #"""
    ObjC.import("stdlib");

    function omiEnvInt(key, fallbackValue) {
      var raw = null;
      try { raw = ObjC.unwrap($.getenv(key)); } catch (error) { raw = null; }
      if (raw === null || raw === undefined) { return fallbackValue; }
      var parsed = parseInt(String(raw), 10);
      if (isNaN(parsed) || parsed <= 0) { return fallbackValue; }
      return parsed;
    }

    function omiIso(value) {
      if (!value) { return null; }
      try { return value.toISOString(); } catch (error) { return null; }
    }

    function run() {
      var maxBodyChars = omiEnvInt("OMI_NOTES_MAX_BODY_CHARS", 8000);
      var maxFolders = omiEnvInt("OMI_NOTES_MAX_FOLDERS", 200);

      var app = Application("Notes");
      var notes = app.notes;

      // Integrity guard — see the manifest script.
      var ids = notes.id();
      var titles = notes.name();
      var bodies = notes.plaintext();
      var modified = notes.modificationDate();
      var created = notes.creationDate();
      var locked = notes.passwordProtected();
      var idsAfter = notes.id();
      if (ids.length !== idsAfter.length) {
        return JSON.stringify({ schema: 1, error: "concurrent_modification" });
      }
      for (var guardIndex = 0; guardIndex < ids.length; guardIndex++) {
        if (ids[guardIndex] !== idsAfter[guardIndex]) {
          return JSON.stringify({ schema: 1, error: "concurrent_modification" });
        }
      }

      var folderMode = "skipped";
      var folderByNoteId = {};
      try {
        var folders = app.folders;
        var folderNames = folders.name();
        if (folderNames.length <= maxFolders) {
          folderMode = "mapped";
          for (var folderIndex = 0; folderIndex < folderNames.length; folderIndex++) {
            var folderNoteIds = folders[folderIndex].notes.id();
            for (var noteIndex = 0; noteIndex < folderNoteIds.length; noteIndex++) {
              folderByNoteId[String(folderNoteIds[noteIndex])] = String(folderNames[folderIndex]);
            }
          }
        }
      } catch (error) {
        folderMode = "skipped";
        folderByNoteId = {};
      }

      var exported = [];
      var lockedSkipped = 0;
      for (var index = 0; index < ids.length; index++) {
        if (locked[index]) {
          lockedSkipped++;
          continue;
        }
        var noteId = String(ids[index]);
        var body = bodies[index] === null || bodies[index] === undefined ? "" : String(bodies[index]);
        var truncated = false;
        if (body.length > maxBodyChars) {
          body = body.substring(0, maxBodyChars);
          truncated = true;
        }
        exported.push({
          id: noteId,
          title: titles[index] === null || titles[index] === undefined ? "" : String(titles[index]),
          body: body,
          truncated: truncated,
          modifiedAt: omiIso(modified[index]),
          createdAt: omiIso(created[index]),
          folder: folderMode === "mapped" ? folderByNoteId[noteId] || null : null
        });
      }

      return JSON.stringify({
        schema: 1,
        lockedSkipped: lockedSkipped,
        folderMode: folderMode,
        notes: exported
      });
    }
    """#
}
