# Visual audit suites for older revisions

`app/scripts/visual_audit.sh` copies this checkout's harness over both revisions it captures. The
current suite (`../registry.dart`) only compiles against current main, so a revision from before a
large UI change is captured with a compat suite instead.

Each `compat/<name>/` holds:

- `UNTIL`: the first commit where this suite no longer applies. A revision that does not contain
  it is captured with this suite (when several match, the one with the earliest `UNTIL`).
- `registry.dart`: `final auditSuite = AuditSuite(...)` with that revision's theme, default
  providers and scenarios, importing `../../harness.dart`.
- `fakes.dart` and `scenarios/*.dart` as that revision needs them.

Use the current suite's id for the equivalent page (for example the old Profile page is
`settings-account`, the old Settings sheet is `settings-sheet`), so the gallery pairs them. Leave out
pages that did not exist yet; the gallery shows them as "did not exist". A page that only existed
then gets its own id. These files are excluded from analysis on main (`analysis_options.yaml`) and
are checked by running the tool against their revision, not by the smoke test.
