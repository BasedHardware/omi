# A placeholder title beside real notes is a finished row

Follow-up to `2026-11-17-notes-pending-title.md`. That change made the transcribing hold and the
`processing` branch of the Home step read any placeholder title as "untitled". Generated notes
whose headline was unusable carry the fallback label beside real content, so on a batch capture
whose transcript receipt had not landed the row was presented as "Transcribing…" and its notes
were hidden.

`home_titles.untitled_pending` is now the test at both sites: no title, or a placeholder on a row
with no notes (`notes_pending`). An empty title keeps its previous meaning. For a note-bearing row
this restores the result these two sites gave before the earlier change.

Not changed, and unchanged from before both changes:

- `fragment_visibility.is_settling_fragment` still holds an uncurated batch capture shorter than
  60 seconds with no projection receipt, whether or not it has notes.
- `utils/episodes/home_read.project_episode` still decides a member's transcription wait from the
  episode deadline stamp alone. Episodes are off in production.

Read path only. No flag, no stored-data change. Evidence: `tests/unit/test_notes_pending_title.py`.
