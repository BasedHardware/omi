import CryptoKit
import Foundation

/// The accessibility tree of a window, captured as content-addressed nodes.
///
/// OCR is a photograph of text: it guesses characters from pixels, and it guesses wrong on small
/// type, low contrast, ligatures and punctuation-heavy code. The accessibility tree *is* the text —
/// the application handing over its own strings, exactly, with the structure they sit in. It costs
/// no model and no inference; it is already on the machine.
///
/// Two properties make it affordable to store one of these beside every frame:
///
/// - **Content addressing.** A node's identity is the hash of what it contains, children included,
///   so two identical subtrees are one row. Consecutive frames of the same window share almost
///   everything, and a window where one label changed re-stores that label and its ancestors and
///   nothing else.
/// - **Bounds on every axis.** Depth, node count, per-node text, total text and wall-clock time all
///   have ceilings, because an unresponsive application can answer accessibility queries slowly and
///   claim any number of children. Capture must degrade, never stall.
public enum AccessibilityTree {

    // MARK: - Capture

    /// Walks `element` into a bounded tree, or nil when the window carried no text worth storing.
    ///
    /// `clock` is injected so the time budget is a fact about the walker rather than about how busy
    /// the machine running it happens to be.
    public static func capture(
        _ element: any AXElementSource,
        limits: AXCaptureLimits = .default,
        clock: @escaping @Sendable () -> TimeInterval = { Date().timeIntervalSinceReferenceDate }
    ) -> AXNode? {
        var state = WalkState(limits: limits, clock: clock, deadline: clock() + limits.budget)
        let node = walk(element, depth: 1, state: &state)
        // Structure with nothing in it costs rows and answers no question — the same rule the screen
        // watcher already applies to a frame whose OCR came back empty.
        guard let node, isWorthKeeping(node) else { return nil }
        return node
    }

    private struct WalkState {
        let limits: AXCaptureLimits
        let clock: @Sendable () -> TimeInterval
        let deadline: TimeInterval
        var nodesRemaining: Int
        var textRemaining: Int

        init(limits: AXCaptureLimits, clock: @escaping @Sendable () -> TimeInterval, deadline: TimeInterval) {
            self.limits = limits
            self.clock = clock
            self.deadline = deadline
            nodesRemaining = limits.maxNodes
            textRemaining = limits.maxTotalTextCharacters
        }

        var isOutOfTime: Bool { clock() >= deadline }
    }

    private static func walk(
        _ element: any AXElementSource,
        depth: Int,
        state: inout WalkState
    ) -> AXNode? {
        guard state.nodesRemaining > 0 else { return nil }
        state.nodesRemaining -= 1

        let role = element.axRole ?? "AXUnknown"
        let subrole = element.axSubrole
        let ownText = text(of: element, state: &state)

        // Checked after this node is built: a spent budget must still yield the window itself, or a
        // slow application produces nothing at all rather than a shallow answer.
        guard depth < state.limits.maxDepth, !state.isOutOfTime else {
            return AXNode(role: role, subrole: subrole, text: ownText, children: [])
        }

        var children: [AXNode] = []
        for child in element.axChildren {
            guard state.nodesRemaining > 0, !state.isOutOfTime else { break }
            if let walked = walk(child, depth: depth + 1, state: &state) {
                children.append(walked)
            }
        }
        return AXNode(role: role, subrole: subrole, text: ownText, children: children)
    }

    /// The strings a node contributes, scrubbed *before* anything else happens to them.
    ///
    /// Redaction runs here rather than at the storage layer because the content address is taken
    /// over the payload: a credential that reaches the payload is in the hash, in the database, and
    /// in every backup, permanently. There is no later place to remove it from.
    private static func text(of element: any AXElementSource, state: inout WalkState) -> String? {
        guard state.textRemaining > 0 else { return nil }

        // The one node in a window that exists to hold a secret, and macOS names it for us. The
        // field is still described — the record says a password field was on screen — but its value
        // never enters the walk. Redaction is a net with holes; this is a hole that need not exist.
        let isSecure = element.axSubrole == AXElementSubrole.secureTextField
        let candidates = [element.axTitle, isSecure ? nil : element.axValue, element.axDescription]

        var parts: [String] = []
        for candidate in candidates {
            guard let candidate else { continue }
            let scrubbed = Redaction.scrub(candidate).trimmingCharacters(in: .whitespacesAndNewlines)
            // A whitespace-only label is the same absence as a missing one, and must hash the same:
            // otherwise a node that merely lost its text reads as a different node.
            guard !scrubbed.isEmpty else { continue }
            parts.append(scrubbed)
        }
        guard !parts.isEmpty else { return nil }

        var joined = parts.joined(separator: "\n")
        // A text view holding a whole file is one node, so the node ceiling does not protect against
        // it. This does.
        if joined.count > state.limits.maxTextCharacters {
            joined = String(joined.prefix(state.limits.maxTextCharacters))
        }
        if joined.count > state.textRemaining {
            joined = String(joined.prefix(state.textRemaining))
        }
        guard !joined.isEmpty else { return nil }
        state.textRemaining -= joined.count
        return joined
    }

    /// Whether the tree says anything at all.
    ///
    /// Text is the obvious signal, but not the only one: a text element with an empty label is
    /// still a place text lives, and a window that has one differs from a window that is pure
    /// scaffolding. So a bare nest of groups is dropped — it costs rows and answers no question —
    /// while an empty field is kept, because "the field was there and was blank" is information.
    private static func isWorthKeeping(_ node: AXNode) -> Bool {
        if node.text?.isEmpty == false { return true }
        if textBearingRoles.contains(node.role) { return true }
        return node.children.contains(where: isWorthKeeping)
    }

    private static let textBearingRoles: Set<String> = [
        "AXStaticText", "AXTextField", "AXTextArea", "AXValueIndicator", "AXLink",
    ]

    // MARK: - Content addressing

    /// Every distinct subtree in `node`, children before parents, root last.
    ///
    /// The order is the insert order: a row never references a hash that is not in the table yet.
    /// Repeats are dropped, which is the whole point — a list of forty identical rows is one row.
    public static func records(of node: AXNode) -> [AXNodeRecord] {
        var seen = Set<Data>()
        var records: [AXNodeRecord] = []
        _ = collect(node, seen: &seen, into: &records)
        return records
    }

    /// The content address of `node`, identical to the hash carried by its record.
    public static func rootHash(of node: AXNode) -> Data {
        var seen = Set<Data>()
        var records: [AXNodeRecord] = []
        return collect(node, seen: &seen, into: &records)
    }

    @discardableResult
    private static func collect(
        _ node: AXNode,
        seen: inout Set<Data>,
        into records: inout [AXNodeRecord]
    ) -> Data {
        let childHashes = node.children.map { collect($0, seen: &seen, into: &records) }
        let bytes = payload(of: node, childHashes: childHashes)
        let hash = Data(SHA256.hash(data: bytes))
        if seen.insert(hash).inserted {
            records.append(AXNodeRecord(hash: hash, payload: bytes))
        }
        return hash
    }

    /// The bytes the hash is taken over.
    ///
    /// Role and subrole are part of the address, not decoration: a button labelled "Send" and a
    /// label reading "Send" are different things on screen, and collapsing them into one row would
    /// lose that difference everywhere it matters.
    private static func payload(of node: AXNode, childHashes: [Data]) -> Data {
        var out = Data()
        func field(_ value: String?) {
            out.append(0x1F)
            if let value { out.append(contentsOf: Array(value.utf8)) }
        }
        field(node.role)
        field(node.subrole)
        field(node.text)
        for hash in childHashes {
            out.append(0x1E)
            out.append(hash)
        }
        return out
    }

    // MARK: - Reading

    /// The tree's text in reading order, bounded.
    ///
    /// Depth-first, so a bound cuts the tail of the window rather than its detail — the top of a
    /// document is what the reader was looking at.
    public static func flattenedText(of node: AXNode, limit: Int) -> String {
        var out = ""
        append(node, limit: limit, into: &out)
        return out
    }

    private static func append(_ node: AXNode, limit: Int, into out: inout String) {
        if let text = node.text, !text.isEmpty {
            let addition = out.isEmpty ? text : "\n" + text
            if out.count + addition.count <= limit { out += addition }
        }
        for child in node.children { append(child, limit: limit, into: &out) }
    }
}

// MARK: - The seam

/// Everything the walker asks of an accessibility element, and nothing else.
///
/// A protocol rather than `AXUIElement` directly because none of this can be exercised against a
/// real window in CI: there is no GUI, no focused application, and no Accessibility grant, and
/// depending on one would make the suite depend on a TCC database a machine either has or does not.
/// The walker is ordinary production code either way; only its input changes.
public protocol AXElementSource {
    var axRole: String? { get }
    var axSubrole: String? { get }
    var axTitle: String? { get }
    var axValue: String? { get }
    var axDescription: String? { get }
    var axChildren: [any AXElementSource] { get }
}

public enum AXElementSubrole {
    public static let secureTextField = "AXSecureTextField"
}

// MARK: - Values

/// Ceilings on a walk. Every one exists because an application can violate the axis it bounds:
/// report thousands of children, nest without end, hold a whole file in one text view, or simply
/// answer slowly.
public struct AXCaptureLimits: Sendable {
    public var maxDepth: Int
    public var maxNodes: Int
    public var maxTextCharacters: Int
    public var maxTotalTextCharacters: Int
    public var budget: TimeInterval

    public init(
        maxDepth: Int = 24,
        maxNodes: Int = 600,
        maxTextCharacters: Int = 2_000,
        maxTotalTextCharacters: Int = 20_000,
        budget: TimeInterval = 0.25
    ) {
        self.maxDepth = maxDepth
        self.maxNodes = maxNodes
        self.maxTextCharacters = maxTextCharacters
        self.maxTotalTextCharacters = maxTotalTextCharacters
        self.budget = budget
    }

    public static let `default` = AXCaptureLimits()
}

/// One captured element: what it is, what it said, and what was inside it.
public struct AXNode: Sendable, Equatable {
    public let role: String
    public let subrole: String?
    public let text: String?
    public let children: [AXNode]

    public init(role: String, subrole: String?, text: String?, children: [AXNode]) {
        self.role = role
        self.subrole = subrole
        self.text = text
        self.children = children
    }
}

/// A distinct subtree, ready to store: its content address and the bytes that address was taken of.
public struct AXNodeRecord: Sendable, Equatable {
    public let hash: Data
    public let payload: Data

    public init(hash: Data, payload: Data) {
        self.hash = hash
        self.payload = payload
    }
}
