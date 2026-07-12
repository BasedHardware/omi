import XCTest
@testable import Omi_Computer

final class ChatToolExecutorSQLTests: XCTestCase {
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

    @MainActor
    func testKernelStampedReadOnlySQLRejectsPhysicalMutationInput() async {
        let previousOwner = UserDefaults.standard.object(forKey: DefaultsKey.authUserId.rawValue)
        defer {
            if let previousOwner {
                UserDefaults.standard.set(previousOwner, forKey: DefaultsKey.authUserId.rawValue)
            } else {
                UserDefaults.standard.removeObject(forKey: DefaultsKey.authUserId.rawValue)
            }
        }
        UserDefaults.standard.set("sql-owner", forKey: DefaultsKey.authUserId.rawValue)
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
}
