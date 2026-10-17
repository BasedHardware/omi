import Foundation

@main
struct NativeHomeContractTests {
    static func main() throws {
        let data = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
        let fixture = try JSONSerialization.jsonObject(with: data) as! [String: Any]
        let snapshot = try NativeHomeSnapshot.decode(fixture)
        precondition(snapshot.appearance == "system")
        precondition(snapshot.direction == "ltr")
        precondition(snapshot.conversation(id: "conversation-1")?.transcript?.count == 2)
        precondition(snapshot.conversation(id: "locked-1")?.locked == true)
        precondition(snapshot.conversation(id: "missing") == nil)
        precondition(snapshot.withoutContent().groups.isEmpty)
        precondition(snapshot.withoutContent().localRecordingCount == 0)
        precondition(snapshot.withoutContent().copy == snapshot.copy)

        var revision = NativeSnapshotRevision()
        precondition(revision.accept(2))
        precondition(!revision.accept(1))
        precondition(!revision.accept(2))
        precondition(revision.accept(3))
        precondition(revision.value == 3)

        for (key, invalid) in [("version", 2), ("revision", -1), ("localRecordingCount", -1)] {
            var malformed = fixture
            malformed[key] = invalid
            try rejects(malformed)
        }
        var unknownAppearance = fixture
        unknownAppearance["appearance"] = "purple"
        try rejects(unknownAppearance)

        var groups = fixture["groups"] as! [[String: Any]]
        var duplicateGroup = fixture
        duplicateGroup["groups"] = groups + groups
        try rejects(duplicateGroup)

        var rows = groups[0]["conversations"] as! [[String: Any]]
        var duplicateRow = fixture
        groups[0]["conversations"] = rows + [rows[0]]
        duplicateRow["groups"] = groups
        try rejects(duplicateRow)

        for key in ["summary", "externalText", "transcript"] {
            var leak = fixture
            var leakGroups = fixture["groups"] as! [[String: Any]]
            var leakRows = leakGroups[0]["conversations"] as! [[String: Any]]
            leakRows[1][key] = key == "transcript" ? rows[0][key] : "private content"
            leakGroups[0]["conversations"] = leakRows
            leak["groups"] = leakGroups
            try rejects(leak)
        }
        rows[0]["id"] = ""
        groups[0]["conversations"] = rows
        var emptyId = fixture
        emptyId["groups"] = groups
        try rejects(emptyId)
        print("Native home contract passed: decode, appearance, revisions, identities and locked-content rejection")
    }

    private static func rejects(_ value: Any) throws {
        do {
            _ = try NativeHomeSnapshot.decode(value)
        } catch {
            return
        }
        preconditionFailure("Unsafe native presentation snapshot accepted")
    }
}
