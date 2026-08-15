import OSLog
import XCTest

@testable import ContextApp

/// **What survives in the unified log, and what a bug report can therefore be answered with.**
///
/// Reported on 2026-08-15: *"the app produces NO unified-log output"* — every `log show` against
/// this bundle came back empty while the app was demonstrably running. It was not silent. Two
/// things were true at once and both are ordinary, which is exactly why the run cost an hour:
///
/// 1. `log` is a **zsh builtin**. `log show --predicate …` in an interactive zsh never reaches
///    `/usr/bin/log` at all; it fails with `log: too many arguments` and prints nothing.
/// 2. `log show` does not print `OS_LOG_TYPE_INFO` without `--info`, and `ContextLog.info` — which
///    is the level most of this app writes at — is exactly that. A query without the flag is not
///    broken, it is correctly showing the `milestone` and `error` lines only, of which a healthy
///    app can genuinely have none in a five-minute window.
///
/// The level half is the half this app can be wrong about, so it is the half asserted behaviourally
/// here: `ContextLog` emits, `OSLogStore` reads the process's own store back, and the level that
/// comes out is the one `log show` will or will not keep. Nothing is mocked and nothing sleeps —
/// entries for the current process are readable the moment they are written (measured).
///
/// The command half cannot be asserted against `log show` from a hermetic test, so it is pinned
/// where somebody reaching for it will actually read it: the doc comment on `ContextLog`.
final class DiagnosticTraceTests: XCTestCase {

    /// Everything `ContextLog` wrote for this test, by the token planted in the message.
    ///
    /// Scoped to `.currentProcessIdentifier`, which needs no entitlement and cannot see any other
    /// process — so this reads back only what the line above it emitted.
    private func levels(matching token: String, since: Date) throws -> [OSLogEntryLog.Level] {
        let store = try OSLogStore(scope: .currentProcessIdentifier)
        return try store.getEntries(at: store.position(date: since))
            .compactMap { $0 as? OSLogEntryLog }
            .filter { $0.composedMessage.contains(token) }
            .map(\.level)
    }

    // MARK: - The levels themselves

    /// **`milestone` is `.notice`**, which is `OS_LOG_TYPE_DEFAULT` — the level `log show` prints
    /// with no flags at all and keeps on disk for days.
    ///
    /// This is the whole reason `milestone` exists rather than everything being `info`, and the
    /// property every promotion to it depends on. If this ever regressed to `.info`, the lines a
    /// remote diagnosis is built from — the run boundaries, the termination decision, a capture
    /// stand-down — would vanish minutes after they were written and the failure would look exactly
    /// like the report above.
    func testMilestoneIsWrittenAtALevelLogShowKeeps() throws {
        let token = "ctx-milestone-\(UUID().uuidString)"
        let since = Date().addingTimeInterval(-5)

        ContextLog.milestone(token, "test")

        XCTAssertEqual(
            try levels(matching: token, since: since), [.notice],
            """
            ContextLog.milestone has to reach the log as .notice (OS_LOG_TYPE_DEFAULT). That is the \
            level `log show` prints unasked and retains; anything lower is thrown away within \
            minutes and takes every remote diagnosis with it.
            """)
    }

    /// **`error` persists too**, and is the level upload failures, dropped grants and stand-downs
    /// already use. Asserted beside `milestone` so a change that "simplified" the two into one
    /// cannot quietly demote this one.
    func testErrorIsWrittenAtALevelLogShowKeeps() throws {
        let token = "ctx-error-\(UUID().uuidString)"
        let since = Date().addingTimeInterval(-5)

        ContextLog.error(token, "test")

        XCTAssertEqual(try levels(matching: token, since: since), [.error])
    }

    /// **`info` is `OS_LOG_TYPE_INFO`, and that is the fact `--info` exists for.**
    ///
    /// Asserted rather than assumed because it is the load-bearing half of the reported symptom: an
    /// empty `log show` over a window in which the app wrote plenty is not evidence of a silent
    /// app, it is evidence that everything it wrote was at this level. Pinning it here is what
    /// makes the documented invocation on `ContextLog` correct rather than folklore.
    ///
    /// It is deliberately **not** a demand that `info` be promoted. A log that shouts about every
    /// mixer restart is a log people stop reading, which is the failure `ContextLog` calls out.
    func testInfoIsWrittenAtTheLevelLogShowHidesByDefault() throws {
        let token = "ctx-info-\(UUID().uuidString)"
        let since = Date().addingTimeInterval(-5)

        ContextLog.info(token, "test")

        XCTAssertEqual(
            try levels(matching: token, since: since), [.info],
            """
            ContextLog.info is OS_LOG_TYPE_INFO, so `log show` omits it unless asked with --info. \
            If this ever became .notice, the documented query would stop being the right advice \
            and the log would fill with routine progress.
            """)
    }

    // MARK: - The run boundaries

    /// **Static checker, not behavioural coverage.**
    ///
    /// `Engine.start()`, `pause()`, `resume()` and `handleTermination()` cannot be driven from a
    /// headless suite — they take the microphone, the window server and the store — so the guard is
    /// on the source and labelled as such.
    ///
    /// What it protects: these four lines bracket a run. Without them at a persisted level, a log
    /// pulled hours later is a scatter of errors with no way to tell which process they belong to,
    /// whether capture ever came up, or whether a gap in the recording was the app doing as it was
    /// told. That is measured, not hypothetical — on the 2026-08-15 report the only line surviving
    /// for a whole run was the one `applicationWillTerminate` writes.
    func testTheRunBoundariesAreLoggedAtAPersistedLevel() throws {
        let source = try strippedSource(at: "Engine.swift")

        for boundary in ["Engine started", "Engine stopped", "Capture paused", "Capture resumed"] {
            XCTAssertTrue(
                source.contains("ContextLog.milestone(\"\(boundary)\""),
                """
                "\(boundary)" brackets a run and has to survive in the unified log. At \
                ContextLog.info it is evicted within minutes, which leaves a bug report with \
                errors and nothing to place them in.
                """)
        }
    }

    // MARK: - The command in the doc

    /// **Static checker, not behavioural coverage.**
    ///
    /// The query documented on `ContextLog` is the one that gets pasted into bug reports, and the
    /// version that shipped was wrong in both of the ways that produced the "no output at all"
    /// report: a bare `log`, which zsh answers itself, and no `--info`, which hides most of the
    /// file. A doc that is wrong here costs an hour every time somebody follows it.
    func testTheDocumentedQueryActuallyWorks() throws {
        let source = try String(
            contentsOf: InkSourceSweep.uiSourceRoot.appendingPathComponent("Support/Log.swift"),
            encoding: .utf8)

        XCTAssertTrue(
            source.contains("/usr/bin/log show"),
            """
            The documented invocation must be absolute. `log` is a zsh builtin and shadows \
            /usr/bin/log in an interactive shell, where `log show --predicate …` fails with \
            "too many arguments" and prints nothing — which reads as an app that logs nothing.
            """)
        XCTAssertFalse(
            source.contains("\n/// log show"),
            "a bare `log show` in the docs is the invocation that silently does nothing in zsh")
        XCTAssertTrue(
            source.contains("--info"),
            """
            Without --info the query hides every ContextLog.info line, which is most of this file. \
            The documented command has to be the one that shows them.
            """)
        XCTAssertTrue(
            source.contains("subsystem == \"com.omi.context-for-claude\""),
            "the documented predicate has to name the subsystem ContextLog actually registers")
    }

    // MARK: - Helpers

    /// Comments stripped, so prose naming a boundary does not stand in for the call that logs it.
    private func strippedSource(at relativePath: String) throws -> String {
        let url = InkSourceSweep.uiSourceRoot.appendingPathComponent(relativePath)
        return InkSourceSweep.strippingComments(from: try String(contentsOf: url, encoding: .utf8))
    }
}
