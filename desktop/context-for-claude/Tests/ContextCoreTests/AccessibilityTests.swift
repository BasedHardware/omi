import ContextCore
import Foundation
import XCTest

/// The accessibility tree, read through the seam that makes it testable at all.
///
/// None of this can be exercised against a real window in CI: there is no GUI, no focused
/// application, and no Accessibility grant — and asking for one would make the suite depend on a
/// TCC database that a machine either has or does not. So `AXElementSource` is a protocol, the
/// bounded walk that turns it into an `AXNode` is ordinary production code, and these tests drive
/// that code with elements built in memory. What is under test is the real walker, not a
/// re-implementation of it.
final class AccessibilityTests: XCTestCase {

    // MARK: - Content addressing

    func testTwoIdenticalSubtreesAreStoredOnce() {
        // The whole reason the table is content-addressed: a window with two identical rows, or two
        // consecutive frames of the same window, must not pay twice for the same UI.
        let row = FakeElement(role: "AXRow", title: "Inbox", children: [
            FakeElement(role: "AXStaticText", value: "unread"),
        ])
        let tree = try! capture(FakeElement(role: "AXWindow", title: "Mail", children: [row, row]))

        let records = AccessibilityTree.records(of: tree)

        // window + row + text = 3 distinct subtrees, from 5 walked elements.
        XCTAssertEqual(records.count, 3)
        XCTAssertEqual(Set(records.map(\.hash)).count, 3, "a hash was issued twice")
        // Children before parents, root last: an insert in this order never references a row that
        // is not there yet.
        XCTAssertEqual(records.last?.hash, AccessibilityTree.rootHash(of: tree))
    }

    func testChangingOneLeafReusesEverySubtreeThatDidNotChange() {
        // This is the measurement the design turns on. Consecutive frames differ by one label; if
        // anything but that label and its ancestors changes hash, dedup is not working and every
        // frame costs a whole tree.
        let before = try! capture(window(status: "2 unread"))
        let after = try! capture(window(status: "3 unread"))

        let hashesBefore = Set(AccessibilityTree.records(of: before).map(\.hash))
        let hashesAfter = Set(AccessibilityTree.records(of: after).map(\.hash))

        XCTAssertNotEqual(
            AccessibilityTree.rootHash(of: before), AccessibilityTree.rootHash(of: after),
            "a changed screen must produce a changed root")
        // window → sidebar → status text: three nodes on the path from the change to the root.
        XCTAssertEqual(
            hashesAfter.subtracting(hashesBefore).count, 3,
            "more than the changed leaf and its ancestors were re-stored")
        XCTAssertFalse(
            hashesAfter.intersection(hashesBefore).isEmpty,
            "nothing at all was shared between two nearly identical screens")
    }

    func testRoleAndTextAreBothPartOfTheContentAddress() {
        let button = try! capture(FakeElement(role: "AXButton", title: "Send"))
        let text = try! capture(FakeElement(role: "AXStaticText", title: "Send"))
        let other = try! capture(FakeElement(role: "AXButton", title: "Cancel"))

        XCTAssertNotEqual(
            AccessibilityTree.rootHash(of: button), AccessibilityTree.rootHash(of: text),
            "two different controls collapsed into one row because only their text was hashed")
        XCTAssertNotEqual(AccessibilityTree.rootHash(of: button), AccessibilityTree.rootHash(of: other))
    }

    func testAnAbsentLabelIsNotTheSameAsAnEmptyOne() {
        // `nil` and `""` have to encode differently or a node that lost its label would silently
        // keep the hash of one that never had one.
        let absent = try! capture(FakeElement(role: "AXGroup", children: [labelled(nil)]))
        let empty = try! capture(FakeElement(role: "AXGroup", children: [labelled("")]))

        XCTAssertEqual(
            AccessibilityTree.rootHash(of: absent), AccessibilityTree.rootHash(of: empty),
            "a whitespace-only label is the same absence as a missing one")
    }

    // MARK: - Reading the graph back

    /// The edges of this graph live inside the payload, so retention cannot ask SQL which subtrees
    /// are still in use — it has to reverse the encoding. Every child has to come back, in order,
    /// from a payload that was never designed to be parsed.
    func testEveryChildAddressCanBeReadBackOutOfAPayload() {
        let tree = try! capture(
            FakeElement(role: "AXWindow", title: "Mail", children: [
                FakeElement(role: "AXToolbar", title: "Send"),
                FakeElement(role: "AXStaticText", value: "Inbox"),
                FakeElement(role: "AXRow", title: "Draft", children: [
                    FakeElement(role: "AXStaticText", value: "To:")
                ]),
            ]))
        let records = AccessibilityTree.records(of: tree)
        let payloads = Dictionary(uniqueKeysWithValues: records.map { ($0.hash, $0.payload) })

        let root = try! XCTUnwrap(payloads[AccessibilityTree.rootHash(of: tree)])
        XCTAssertEqual(
            AccessibilityTree.childHashes(inPayload: root),
            tree.children.map(AccessibilityTree.rootHash(of:)),
            "the window's children did not come back in the order they were written")

        // A leaf claims nothing, or reachability would walk into the text it stores.
        let leaf = try! XCTUnwrap(payloads[AccessibilityTree.rootHash(of: tree.children[1])])
        XCTAssertEqual(AccessibilityTree.childHashes(inPayload: leaf), [])
    }

    /// **The one direction this decoder may not fail in.**
    ///
    /// The encoding is not self-delimiting: a node's text is whatever an application handed over,
    /// and nothing stops it containing the 0x1E that separates child addresses. A decoder that
    /// scanned forward would stop at that byte and report fewer children than the node has — and a
    /// child nobody reports is a live subtree the sweep is then free to delete. Reading from the end
    /// cannot make that mistake, because the children are always the payload's suffix.
    func testTextThatLooksLikeAChildSeparatorCannotHideARealChild() {
        // 0x1E followed by 32 bytes: a whole counterfeit child address, sitting in the text.
        let counterfeit = "label\u{1E}" + String(repeating: "x", count: 32) + "\u{1F}tail"
        let child = AXNode(role: "AXStaticText", subrole: nil, text: "Inbox", children: [])
        let tree = AXNode(
            role: "AXWindow", subrole: nil, text: counterfeit, children: [child])
        let records = AccessibilityTree.records(of: tree)
        let root = records.first { $0.hash == AccessibilityTree.rootHash(of: tree) }

        let children = AccessibilityTree.childHashes(inPayload: try! XCTUnwrap(root).payload)

        XCTAssertEqual(
            children, [AccessibilityTree.rootHash(of: child)],
            "the counterfeit separator in the node's own text was read as part of the child list")
    }

    // MARK: - Bounds
    //
    // A runaway tree must never stall capture. Every ceiling below is proved to hold on a tree
    // built specifically to blow past it.

    func testCaptureStopsAtTheDepthCeiling() {
        var deep = FakeElement(role: "AXStaticText", value: "bottom")
        for level in 0..<60 {
            deep = FakeElement(role: "AXGroup", title: "level \(level)", children: [deep])
        }

        let limits = AXCaptureLimits(maxDepth: 5)
        let tree = try! capture(deep, limits: limits)

        XCTAssertEqual(depth(of: tree), 5)
    }

    func testCaptureStopsAtTheNodeCeiling() {
        let wide = FakeElement(
            role: "AXList", title: "everything",
            children: (0..<5_000).map { FakeElement(role: "AXStaticText", value: "row \($0)") })

        let tree = try! capture(wide, limits: AXCaptureLimits(maxNodes: 40))

        XCTAssertEqual(count(of: tree), 40)
    }

    func testCaptureTruncatesOneEnormousValue() {
        // A text view holding a whole file is a single node, so the node ceiling does not protect
        // against it — this one does.
        let novel = String(repeating: "a", count: 200_000)
        let tree = try! capture(
            FakeElement(role: "AXTextArea", value: novel), limits: AXCaptureLimits(maxTextCharacters: 64))

        XCTAssertEqual(tree.text?.count, 64)
    }

    func testCaptureStopsSpendingTextBudgetOnceItIsGone() {
        let chatty = FakeElement(
            role: "AXList", title: "conversation",
            children: (0..<100).map { FakeElement(role: "AXStaticText", value: "line \($0) of noise") })

        let tree = try! capture(chatty, limits: AXCaptureLimits(maxTotalTextCharacters: 120))

        let total = texts(of: tree).reduce(0) { $0 + $1.count }
        XCTAssertLessThanOrEqual(total, 120)
        // Structure survives the text budget: the nodes are still there, they are just silent, so
        // the shape of the window is not lost along with its words.
        XCTAssertEqual(count(of: tree), 101)
    }

    func testCaptureStopsWhenTheTimeBudgetIsSpent() {
        // An unresponsive app answers accessibility messages slowly, and there is no ceiling on how
        // many nodes it can claim to have. The clock is injected so this is a fact about the walker
        // rather than about how fast the machine running the test happens to be.
        let wide = FakeElement(
            role: "AXList", title: "slow",
            children: (0..<500).map { FakeElement(role: "AXStaticText", value: "row \($0)") })
        var ticks = 0.0
        let clock: @Sendable () -> TimeInterval = {
            ticks += 1
            return ticks
        }

        let tree = try! capture(wide, limits: AXCaptureLimits(budget: 4), clock: clock)

        XCTAssertLessThan(count(of: tree), 20, "the walk ran past its deadline")
        XCTAssertGreaterThan(count(of: tree), 0, "a spent budget must still yield the window itself")
    }

    func testACyclicTreeTerminates() {
        // Some applications report a child that is its own ancestor. Depth and node ceilings are
        // what make that survivable, and this is the test that says so.
        let cycle = CyclicElement(role: "AXGroup", title: "loop")

        let tree = try! capture(cycle, limits: AXCaptureLimits(maxDepth: 8, maxNodes: 50))

        XCTAssertLessThanOrEqual(count(of: tree), 50)
    }

    // MARK: - Nothing sensitive is hashed

    func testASecureTextFieldContributesNoText() {
        // The one node in a window that exists to hold a secret. Redaction is a net with holes in
        // it; this is a hole that does not have to exist, because macOS names the field for us.
        let form = FakeElement(role: "AXWindow", title: "Account", children: [
            FakeElement(role: "AXTextField", title: "Email", value: "ada@example.com"),
            FakeElement(role: "AXTextField", subrole: "AXSecureTextField", title: "Password",
                        value: "hunter2-the-real-one"),
        ])

        let tree = try! capture(form)

        let all = texts(of: tree).joined(separator: " ")
        XCTAssertTrue(all.contains("ada@example.com"), "an ordinary field was dropped")
        XCTAssertFalse(all.contains("hunter2"), "a secure field's value reached the tree")
        // The field itself is still described, so the record says a password field was on screen.
        XCTAssertTrue(all.contains("Password"))
    }

    func testCredentialsAreScrubbedBeforeTheyCanBeHashed() {
        // Redaction has to happen *before* the content address is computed, or the plaintext is in
        // the payload blob that the hash is taken over — permanently, and in every backup.
        let terminal = FakeElement(role: "AXWindow", title: "zsh", children: [
            FakeElement(role: "AXStaticText",
                        value: "export OPENAI_API_KEY=sk-proj-abcdefghijklmnop"),
        ])

        let tree = try! capture(terminal)
        let records = AccessibilityTree.records(of: tree)

        let text = texts(of: tree).joined(separator: " ")
        XCTAssertFalse(text.contains("sk-proj-abcdefghijklmnop"))
        XCTAssertTrue(text.contains(Redaction.marker))
        for record in records {
            XCTAssertNil(
                String(data: record.payload, encoding: .utf8)?.range(of: "sk-proj-abcdefghij"),
                "the credential survived into the hashed payload")
        }
    }

    // MARK: - Flattening

    func testFlattenedTextIsReadingOrderAndBounded() {
        let window = FakeElement(role: "AXWindow", title: "Notes", children: [
            FakeElement(role: "AXStaticText", value: "first"),
            FakeElement(role: "AXGroup", children: [
                FakeElement(role: "AXStaticText", value: "second"),
                FakeElement(role: "AXStaticText", value: "third"),
            ]),
            FakeElement(role: "AXStaticText", value: "fourth"),
        ])
        let tree = try! capture(window)

        let all = AccessibilityTree.flattenedText(of: tree, limit: 1_000)

        XCTAssertEqual(all, "Notes\nfirst\nsecond\nthird\nfourth")
        // Depth-first, so a bound cuts the tail of the window rather than its detail.
        XCTAssertEqual(AccessibilityTree.flattenedText(of: tree, limit: 12), "Notes\nfirst")
    }

    func testAWindowWithNoTextAtAllIsNotWorthCapturing() {
        // Structure with nothing in it costs rows and answers no question. The same rule the screen
        // watcher already applies to a text-free frame.
        let empty = FakeElement(role: "AXWindow", children: [
            FakeElement(role: "AXGroup", children: [FakeElement(role: "AXGroup")]),
        ])

        XCTAssertNil(AccessibilityTree.capture(empty, limits: .default))
    }

    // MARK: - Helpers

    private func capture(
        _ element: any AXElementSource,
        limits: AXCaptureLimits = .default,
        clock: (@Sendable () -> TimeInterval)? = nil
    ) throws -> AXNode {
        let node = clock.map { AccessibilityTree.capture(element, limits: limits, clock: $0) }
            ?? AccessibilityTree.capture(element, limits: limits)
        return try XCTUnwrap(node)
    }

    /// A sidebar whose status line is the only thing that changes between two frames.
    private func window(status: String) -> FakeElement {
        FakeElement(role: "AXWindow", title: "Mail", children: [
            FakeElement(role: "AXGroup", title: "Sidebar", children: [
                FakeElement(role: "AXStaticText", value: "Inbox"),
                FakeElement(role: "AXStaticText", value: status),
            ]),
            FakeElement(role: "AXGroup", title: "Message", children: [
                FakeElement(role: "AXStaticText", value: "the body never changes"),
            ]),
        ])
    }

    private func labelled(_ title: String?) -> FakeElement {
        FakeElement(role: "AXStaticText", title: title)
    }

    private func depth(of node: AXNode) -> Int {
        1 + (node.children.map(depth(of:)).max() ?? 0)
    }

    private func count(of node: AXNode) -> Int {
        1 + node.children.reduce(0) { $0 + count(of: $1) }
    }

    private func texts(of node: AXNode) -> [String] {
        (node.text.map { [$0] } ?? []) + node.children.flatMap(texts(of:))
    }
}

// MARK: - Fakes

/// An accessibility element built in memory. Everything the walker asks a real `AXUIElement` for,
/// and nothing else.
private struct FakeElement: AXElementSource {
    var axRole: String?
    var axSubrole: String?
    var axTitle: String?
    var axValue: String?
    var axDescription: String?
    var kids: [FakeElement] = []

    var axChildren: [any AXElementSource] { kids }

    init(
        role: String?,
        subrole: String? = nil,
        title: String? = nil,
        value: String? = nil,
        description: String? = nil,
        children: [FakeElement] = []
    ) {
        axRole = role
        axSubrole = subrole
        axTitle = title
        axValue = value
        axDescription = description
        kids = children
    }
}

/// An element that reports itself as its own child, which real applications do.
private struct CyclicElement: AXElementSource {
    var axRole: String?
    var axSubrole: String? { nil }
    var axTitle: String?
    var axValue: String? { "round and round" }
    var axDescription: String? { nil }
    var axChildren: [any AXElementSource] { [self] }

    init(role: String, title: String) {
        axRole = role
        axTitle = title
    }
}
