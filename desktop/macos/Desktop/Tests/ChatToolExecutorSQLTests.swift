import XCTest
import GRDB
@testable import Omi_Computer

private final class OwnerAuthorizationSequence: @unchecked Sendable {
    private let lock = NSLock()
    private var remainingAllowedChecks: Int

    init(allowedChecks: Int) {
        remainingAllowedChecks = allowedChecks
    }

    func isCurrent() -> Bool {
        lock.lock()
        defer { lock.unlock() }
        guard remainingAllowedChecks > 0 else { return false }
        remainingAllowedChecks -= 1
        return true
    }
}

private struct OwnerFenceDefaultsReference: @unchecked Sendable {
    let value: UserDefaults
}

private final class SQLTransactionObserver: TransactionObserver, @unchecked Sendable {
    private let blocksCommit: Bool
    private let commitRelease = DispatchSemaphore(value: 0)
    private let lock = NSLock()
    private var reachedWillCommit = false
    private var willCommitWaiters: [CheckedContinuation<Void, Never>] = []
    private var observedDML = false
    private var committed = false
    private var rolledBack = false

    init(blocksCommit: Bool = false) {
        self.blocksCommit = blocksCommit
    }

    func observes(eventsOfKind eventKind: DatabaseEventKind) -> Bool { true }

    func databaseDidChange(with event: DatabaseEvent) {
        lock.withLock { observedDML = true }
    }

    func databaseWillCommit() throws {
        let waiters = lock.withLock { () -> [CheckedContinuation<Void, Never>] in
            reachedWillCommit = true
            let waiters = willCommitWaiters
            willCommitWaiters.removeAll()
            return waiters
        }
        waiters.forEach { $0.resume() }
        if blocksCommit { commitRelease.wait() }
    }

    func databaseDidCommit(_ db: Database) {
        lock.withLock { committed = true }
    }

    func databaseDidRollback(_ db: Database) {
        lock.withLock { rolledBack = true }
    }

    func waitUntilWillCommit() async {
        if lock.withLock({ reachedWillCommit }) { return }
        await withCheckedContinuation { continuation in
            let resumeImmediately = lock.withLock { () -> Bool in
                if reachedWillCommit { return true }
                willCommitWaiters.append(continuation)
                return false
            }
            if resumeImmediately { continuation.resume() }
        }
    }

    func allowCommit() {
        commitRelease.signal()
    }

    func snapshot() -> (observedDML: Bool, committed: Bool, rolledBack: Bool) {
        lock.withLock { (observedDML, committed, rolledBack) }
    }
}

final class ChatToolExecutorSQLTests: XCTestCase {
    private var originalAuthOwner: String?
    private var originalOwnerOverride: String?
    private var originalOwnerBackup: String?

    override func setUp() async throws {
        try await super.setUp()
        originalAuthOwner = UserDefaults.standard.string(forKey: .authUserId)
        originalOwnerOverride = UserDefaults.standard.string(forKey: .automationOwnerOverride)
        originalOwnerBackup = UserDefaults.standard.string(forKey: .automationOwnerABackup)
        await restoreOriginalOwnerDefaults()
    }

    override func tearDown() async throws {
        await restoreOriginalOwnerDefaults()
        try await super.tearDown()
    }

    func testReadOnlySQLAllowsSelectAndReadOnlyCTE() {
        XCTAssertTrue(ChatToolExecutor.isReadOnlySQLStatement("SELECT * FROM screenshots LIMIT 1"))
        XCTAssertTrue(
            ChatToolExecutor.isReadOnlySQLStatement(
                "WITH recent AS (SELECT * FROM screenshots LIMIT 5) SELECT * FROM recent"
            )
        )
    }

    func testReadOnlySQLBlocksDataModifyingCTEs() {
        XCTAssertFalse(
            ChatToolExecutor.isReadOnlySQLStatement(
                "WITH target AS (SELECT id FROM screenshots LIMIT 1) DELETE FROM screenshots WHERE id IN (SELECT id FROM target) RETURNING id"
            )
        )
        XCTAssertFalse(
            ChatToolExecutor.isReadOnlySQLStatement(
                "WITH target AS (SELECT id FROM action_items LIMIT 1) UPDATE action_items SET completed = 1 WHERE id IN (SELECT id FROM target) RETURNING id"
            )
        )
        XCTAssertFalse(
            ChatToolExecutor.isReadOnlySQLStatement(
                "WITH new_row AS (SELECT 'x' AS value) INSERT INTO action_items (description) SELECT value FROM new_row RETURNING id"
            )
        )
    }

    func testReadOnlySQLIgnoresMutatingWordsInsideLiteralsAndComments() {
        XCTAssertTrue(
            ChatToolExecutor.isReadOnlySQLStatement(
                "SELECT * FROM screenshots WHERE ocrText LIKE '%DELETE%' -- UPDATE later"
            )
        )
        XCTAssertTrue(
            ChatToolExecutor.isReadOnlySQLStatement(
                "WITH words AS (SELECT 'INSERT UPDATE DELETE' AS text) SELECT text FROM words"
            )
        )
    }

    func testSQLAuthorizationIsOutsideSwiftPhysicalPreconditions() {
        XCTAssertEqual(
            ChatToolExecutor.physicalExecutionPrecondition(toolName: "execute_sql"),
            .satisfied
        )
    }

    func testPostDMLOwnerRevocationRollsBackPrimarySQLWrite() async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("owner-bound-sql-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }

        let pool = try DatabasePool(path: directory.appendingPathComponent("test.sqlite").path)
        try await pool.write { db in
            try db.execute(sql: "CREATE TABLE probe (value TEXT NOT NULL)")
        }
        let observer = SQLTransactionObserver()
        pool.add(transactionObserver: observer, extent: .nextTransaction)
        // Initial guard, lease admission, and in-transaction preflight pass. The
        // fourth check runs after INSERT and deliberately revokes authorization.
        let authorization = OwnerAuthorizationSequence(allowedChecks: 3)

        let result = try await ChatToolExecutor.executeWriteQuery(
            "INSERT INTO probe(value) VALUES ('must-roll-back')",
            dbQueue: pool,
            expectedOwnerID: "owner-a",
            ownerIsCurrent: { _ in authorization.isCurrent() }
        )

        XCTAssertEqual(result, ChatToolExecutor.authorizedOwnerChangedResult())
        let count = try await pool.read { db in
            try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM probe") ?? -1
        }
        XCTAssertEqual(count, 0)
        let transaction = observer.snapshot()
        XCTAssertTrue(transaction.observedDML, "the production SQL DML must execute before revocation")
        XCTAssertFalse(transaction.committed)
        XCTAssertTrue(transaction.rolledBack, "the post-DML authorization check must roll back")
    }

    @MainActor
    func testEffectiveOwnerTransitionWaitsThroughPhysicalSQLCommit() async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("owner-commit-fence-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }

        let pool = try DatabasePool(path: directory.appendingPathComponent("test.sqlite").path)
        try await pool.write { db in
            try db.execute(sql: "CREATE TABLE probe (value TEXT NOT NULL)")
        }
        let observer = SQLTransactionObserver(blocksCommit: true)
        pool.add(transactionObserver: observer, extent: .nextTransaction)

        let suiteName = "OwnerCommitFence.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        defer { defaults.removePersistentDomain(forName: suiteName) }
        defaults.set("owner-a", forKey: .authUserId)
        let defaultsReference = OwnerFenceDefaultsReference(value: defaults)

        let writeTask = Task.detached {
            try await ChatToolExecutor.executeWriteQuery(
                "INSERT INTO probe(value) VALUES ('committed-for-owner-a')",
                dbQueue: pool,
                expectedOwnerID: "owner-a",
                ownerIsCurrent: { expectedOwnerID in
                    RuntimeOwnerIdentity.currentOwnerId(
                        defaults: defaultsReference.value,
                        allowAutomationOverride: true
                    ) == expectedOwnerID
                }
            )
        }

        await observer.waitUntilWillCommit()
        let transitionTask = Task { @MainActor in
            await RuntimeOwnerIdentity.applyAutomationOwnerOverride(
                "owner-b",
                defaults: defaults
            )
        }
        await EffectiveOwnerTransitionFence.shared.waitUntilTransitionIsPending()

        XCTAssertNil(defaults.string(forKey: .automationOwnerOverride))
        XCTAssertEqual(defaults.string(forKey: .authUserId), "owner-a")

        observer.allowCommit()
        _ = try await writeTask.value
        _ = await transitionTask.value

        let count = try await pool.read { db in
            try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM probe") ?? -1
        }
        XCTAssertEqual(count, 1)
        XCTAssertEqual(defaults.string(forKey: .automationOwnerOverride), "owner-b")
        let transaction = observer.snapshot()
        XCTAssertTrue(transaction.observedDML)
        XCTAssertTrue(transaction.committed)
        XCTAssertFalse(transaction.rolledBack)
    }

    @MainActor
    func testKernelStampedReadOnlySQLRejectsPhysicalMutationInput() async {
        await establishStandardOwner("sql-owner")
        let result = await ChatToolExecutor.execute(
            ToolCall(
                name: "execute_sql",
                arguments: [
                    "query": "UPDATE action_items SET completed = 1 WHERE id = 42",
                    "read_only": true,
                ],
                thoughtSignature: nil
            ),
            expectedOwnerID: "sql-owner"
        )

        XCTAssertEqual(
            result,
            "Error: this SQL surface is read-only. Use SELECT or read-only WITH queries."
        )
    }

    private func establishStandardOwner(_ ownerID: String?) async {
        let bootstrapOwner = "chat-tool-sql-owner-bootstrap"
        await transitionStandardOwner(to: ownerID == bootstrapOwner ? nil : bootstrapOwner)
        await transitionStandardOwner(to: ownerID)
    }

    private func transitionStandardOwner(to ownerID: String?) async {
        await RuntimeOwnerIdentity.performEffectiveOwnerTransition(
            defaults: .standard,
            allowAutomationOverride: false,
            plannedNextOwner: { _, _ in ownerID },
            quiesceVoice: { _, _ in },
            revokeKernelOwner: { _, _ in },
            retargetLocalStorage: { _, _ in },
            ownerDidChange: {}
        ) { defaults in
            defaults.removeObject(forKey: .automationOwnerOverride)
            defaults.removeObject(forKey: .automationOwnerABackup)
            if let ownerID {
                defaults.set(ownerID, forKey: .authUserId)
            } else {
                defaults.removeObject(forKey: .authUserId)
            }
        }
    }

    private func restoreOriginalOwnerDefaults() async {
        let authOwner = originalAuthOwner
        let ownerOverride = originalOwnerOverride
        let ownerBackup = originalOwnerBackup
        let effectiveOwner = ownerOverride?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
            ? ownerOverride
            : authOwner
        await transitionStandardOwner(to: "chat-tool-sql-owner-restore")
        await RuntimeOwnerIdentity.performEffectiveOwnerTransition(
            defaults: .standard,
            allowAutomationOverride: true,
            plannedNextOwner: { _, _ in effectiveOwner },
            quiesceVoice: { _, _ in },
            revokeKernelOwner: { _, _ in },
            retargetLocalStorage: { _, _ in },
            ownerDidChange: {}
        ) { defaults in
            for (key, value) in [
                (DefaultsKey.authUserId, authOwner),
                (DefaultsKey.automationOwnerOverride, ownerOverride),
                (DefaultsKey.automationOwnerABackup, ownerBackup),
            ] {
                if let value {
                    defaults.set(value, forKey: key.rawValue)
                } else {
                    defaults.removeObject(forKey: key.rawValue)
                }
            }
        }
    }
}
