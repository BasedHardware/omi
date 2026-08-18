import CoreGraphics
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

    // MARK: - The address of what is on screen

    /// The host of the page the window is showing, or nil when nothing in it claims one.
    ///
    /// This exists because the exclusion gate had no honest evidence to work with. "Exclude this
    /// website" was decided from the **window title**, and a browser's title is the page's title:
    /// measured against this machine's database, **0 of 955 browser frames** yielded a host from the
    /// title (Arc titles them `LinkedIn`, `Anthropic`, `Context for Claude`) while 133 yielded one
    /// from the accessibility text the gate never saw. So a user who excluded their bank was
    /// protected by nothing at all, and the Settings pane — which builds its "Recently Recorded"
    /// list from that same accessibility text — offered them exactly the domains it would then fail
    /// to hide.
    ///
    /// Breadth-first, and that ordering is the policy: the element nearest the window is the window
    /// itself (Safari and every document-based app answer `AXDocument` there), then its web area
    /// (`AXWebArea`, which WebKit and Chromium both answer `AXURL` on — 236 of them are in this
    /// machine's stored trees, so the walk does reach them). An iframe or an embedded preview is
    /// deeper than the page containing it, so the shallowest address is the page the user is on.
    ///
    /// **Ask this of the window whose pixels were captured, and of no other window.** The address
    /// and the picture have to be the same window: an address read from a *different* window of the
    /// same application is not weaker evidence about this frame, it is evidence about something
    /// else, and the gate treats an address it is given as authoritative. ``AXWindowMatch`` is what
    /// establishes that they are the same window; no proof there means no address here.
    ///
    /// Bounded on every axis the walker is, and for the same reason: this runs against another
    /// process on every capture tick, and an application that is beachballing must cost a missing
    /// URL rather than a stalled pipeline. The per-message half of that bound is the caller's — see
    /// `AXElement.messagingTimeout`, without which the clock below cannot interrupt a read that
    /// never returns.
    public static func pageHost(
        of element: any AXElementSource,
        limits: AXCaptureLimits = .urlProbe,
        clock: @escaping @Sendable () -> TimeInterval = { Date().timeIntervalSinceReferenceDate }
    ) -> String? {
        let deadline = clock() + limits.budget
        var remaining = limits.maxNodes
        // An index rather than `removeFirst`, which is O(n) on an Array and would make the probe
        // quadratic in the number of elements a window claims to have.
        var frontier: [(element: any AXElementSource, depth: Int)] = [(element, 1)]
        var cursor = 0

        while cursor < frontier.count {
            guard remaining > 0, clock() < deadline else { return nil }
            let (current, depth) = frontier[cursor]
            cursor += 1
            remaining -= 1

            if let raw = current.axURL, let host = webHost(raw) { return host }
            guard depth < limits.maxDepth else { continue }
            for child in current.axChildren { frontier.append((child, depth + 1)) }
        }
        return nil
    }

    /// The **host** of a *website* URL, and nil for everything else an element can answer.
    ///
    /// Two narrowings, both load-bearing:
    ///
    /// - **Websites only.** `subject.url` is the authoritative tier of the website gate, so
    ///   answering `file:///Users/…`, `chrome://settings` or `about:blank` here would not widen the
    ///   gate, it would push a value the gate cannot match into the one field that outranks the
    ///   evidence beneath it.
    /// - **The host only.** The sole consumer normalises to a host as its first act, so the path,
    ///   the query and the fragment are carried no further — and what they carry is a password-reset
    ///   token, a document identifier, a search term. `CaptureSubject` is `Codable` and travels with
    ///   the capture to the write; returning the host is what makes carrying the rest structurally
    ///   impossible rather than merely currently unused.
    private static func webHost(_ raw: String) -> String? {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        let scheme = trimmed.lowercased()
        guard scheme.hasPrefix("http://") || scheme.hasPrefix("https://") else { return nil }
        // A URL whose authority is not host-shaped tells the gate nothing it can match on.
        return DomainMatcher.normalize(trimmed)
    }

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
            out.append(fieldSeparator)
            if let value { out.append(contentsOf: Array(value.utf8)) }
        }
        field(node.role)
        field(node.subrole)
        field(node.text)
        for hash in childHashes {
            out.append(childSeparator)
            out.append(hash)
        }
        return out
    }

    /// A content address is a SHA-256 digest.
    static let hashLength = 32
    /// Precedes each of the three scalar fields, so a payload always opens with three of them.
    private static let fieldSeparator: UInt8 = 0x1F
    /// Precedes each child address, and the child list is always the payload's suffix.
    private static let childSeparator: UInt8 = 0x1E

    /// The addresses of `payload`'s children, read back out of the bytes the hash was taken over.
    ///
    /// The edges of this graph live *inside* the blob — there is no child table to join against —
    /// so anything that needs to know which subtrees are still in use has to reverse the encoding.
    /// That makes this the inverse of ``payload(of:childHashes:)`` and, because its only caller is
    /// a delete, it must be wrong in exactly one direction.
    ///
    /// **Read from the end, never from the front.** The encoding is not self-delimiting: a node's
    /// own text is whatever an application handed over, and nothing stops it containing a 0x1E. A
    /// forward scan would take that byte for the start of the child list and stop reporting real
    /// children — and an unreported child is a live subtree a sweep is then free to delete. Every
    /// child is a fixed 33-byte suffix element, so walking backwards reaches all of them before it
    /// can reach the text, and the worst a hostile string can do is contribute a *phantom* address
    /// that names no row. Over-reporting keeps a node that could have gone; under-reporting deletes
    /// one that could not.
    public static func childHashes(inPayload payload: Data) -> [Data] {
        let bytes = [UInt8](payload)
        // Three field separators open every payload, so nothing at or below this offset is a child.
        let floor = 3
        var end = bytes.count
        var hashes: [Data] = []
        while end - floor >= hashLength + 1 {
            let start = end - hashLength - 1
            guard bytes[start] == childSeparator else { break }
            hashes.append(Data(bytes[(start + 1)..<end]))
            end = start
        }
        return hashes.reversed()
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

// MARK: - Which window the pixels came from

/// The window a capture's pixels came from, in the only terms both sides of the question can answer.
///
/// Assembled from the window-server snapshot the capture is filtered on, so that the accessibility
/// side can be asked to produce *that* window rather than whichever one happens to be focused.
public struct CapturedWindow: Sendable, Equatable {
    /// Where the window server said the window was, in points.
    public var frame: CGRect
    /// The window's own title, exactly as the window server reported it.
    ///
    /// Unscrubbed on purpose, and never stored: this is an identity being compared against another
    /// unscrubbed copy of the same string, not text on its way to a database. Redaction happens to
    /// the copy that is stored, in ``ScreenWatcher``.
    public var title: String?

    /// Whether the window server listed exactly one capturable window for this application.
    ///
    /// The escape hatch, and it is not a shortcut — it is the only case in which identity needs no
    /// evidence, because there is nothing the captured window could be confused *with*. It exists
    /// because the accessibility API cannot always answer the question at all: measured live on
    /// macOS 26, `AXFocusedWindow` on Warp and on Arc both answered the **application element**
    /// rather than a window, with no frame and no window title, and the same is documented in this
    /// app's onboarding code for System Settings' `AXWindows`. Requiring proof unconditionally would
    /// therefore have turned "the exclusion reads the wrong window" into "the exclusion reads
    /// nothing", which is a worse product on more machines.
    ///
    /// So the rule is: with one window, read what the application offers, exactly as before. With
    /// two or more — the only shape in which one window's address can be attached to another's
    /// picture — the evidence has to say which.
    public var wasOnlyWindow: Bool

    public init(frame: CGRect, title: String?, wasOnlyWindow: Bool = false) {
        self.frame = frame
        self.title = title
        self.wasOnlyWindow = wasOnlyWindow
    }
}

/// Picking the accessibility window that *is* the window whose pixels were captured.
///
/// The two halves of a capture used to come from two different places. The **pixels** are the
/// largest on-screen window of the frontmost application, taken from a window-server snapshot that
/// may be seconds old. The **address** and the **text** were read from whatever window that
/// application says is *focused*, now. Those are the same window on almost every tick and not on all
/// of them — a large browser window on a bank sitting behind a small focused window on something
/// else is enough — and when they differed the consequences were not symmetrical:
///
/// - the stored row mixed two windows: one window's picture and OCR beside another's text;
/// - and the *wrong* address silenced the tier of the website gate that measurably works. An address
///   outranks the page text beneath it, so a URL belonging to an unexcluded window was enough to
///   admit a frame of an excluded one — worse than reading no address at all.
///
/// So an address is read only from a window that can be shown to be the captured one. Failing to
/// prove it costs a tier of evidence for one tick; reading the wrong window costs the exclusion.
///
/// **Identity is proven by uniqueness, never by resemblance.** A candidate is accepted only when it
/// is the *only* window of that application answering to one of the two things the snapshot knows,
/// and neither signal is a fallback for the other:
///
/// 1. **The title**, first, because it is the application's own statement of what a window is, and
///    two windows sharing one is rarer than two windows sharing a rectangle — tiled or maximised
///    windows have byte-identical frames.
/// 2. **The frame**, when no single window claims the title. A title changes as the user types in an
///    address bar or switches a tab, and the snapshot's copy of it cannot follow that; geometry
///    outlives it.
///
/// Ambiguity is refused rather than resolved: two candidates matching, or none, yields nil. An
/// application that does not list a window, a window moved inside the snapshot's lifetime, a
/// coordinate space that does not line up — every one of them degrades to "no address, no text",
/// which is the only direction that cannot store the wrong thing.
public enum AXWindowMatch {

    /// Points of slack allowed on each edge. The window server and the accessibility API both report
    /// window geometry in points from the same top-left origin, so an exact match is the ordinary
    /// case and this absorbs rounding rather than disagreement.
    public static let frameTolerance: CGFloat = 2

    public static func window<Element: AXElementSource>(
        matching captured: CapturedWindow,
        in windows: [Element],
        tolerance: CGFloat = frameTolerance
    ) -> Element? {
        if let title = captured.title?.trimmingCharacters(in: .whitespacesAndNewlines), !title.isEmpty
        {
            let named = windows.filter { candidate in
                guard
                    let candidateTitle = candidate.axTitle?
                        .trimmingCharacters(in: .whitespacesAndNewlines), !candidateTitle.isEmpty
                else { return false }
                return candidateTitle == title
            }
            if named.count == 1 { return named[0] }
        }

        let placed = windows.filter { candidate in
            guard let frame = candidate.axFrame else { return false }
            return isSameFrame(frame, captured.frame, tolerance: tolerance)
        }
        return placed.count == 1 ? placed[0] : nil
    }

    /// Whether `element` may be read as the captured window.
    ///
    /// Two ways to answer yes, and they are different kinds of answer. Either the element says which
    /// window it is and it is the captured one — the ordinary proof — or the window server listed no
    /// other window this application could have been showing, in which case there is nothing to
    /// prove: one window is its own identity, whatever the accessibility API is willing to say about
    /// it. See ``CapturedWindow/wasOnlyWindow`` for why the second clause is load-bearing rather
    /// than a loophole.
    public static func isCapturedWindow(
        _ element: some AXElementSource,
        matching captured: CapturedWindow,
        tolerance: CGFloat = frameTolerance
    ) -> Bool {
        if window(matching: captured, in: [element], tolerance: tolerance) != nil { return true }
        return captured.wasOnlyWindow
    }

    /// The same rectangle, within `tolerance` on every edge.
    ///
    /// A window with no geometry is a window with no identity, so an empty rectangle never matches —
    /// and a NaN cannot match anything, because every comparison against one is false. Both are the
    /// answer wanted here.
    static func isSameFrame(_ lhs: CGRect, _ rhs: CGRect, tolerance: CGFloat) -> Bool {
        guard !lhs.isEmpty, !rhs.isEmpty else { return false }
        return abs(lhs.origin.x - rhs.origin.x) <= tolerance
            && abs(lhs.origin.y - rhs.origin.y) <= tolerance
            && abs(lhs.size.width - rhs.size.width) <= tolerance
            && abs(lhs.size.height - rhs.size.height) <= tolerance
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
    /// The address of the document this element is showing, when it is showing one.
    ///
    /// Separate from ``axValue`` because it is not text a person read: it is the application saying
    /// what the window's subject *is*. That distinction is the whole reason the exclusion gate can
    /// trust it — a host in a page's body is a mention, a host in this attribute is the page.
    var axURL: String? { get }
    /// Where this element is on screen, in points, when it is the kind of element that has a place.
    ///
    /// Read for exactly one purpose: telling one window of an application from another, so that the
    /// window being *read* is provably the window that was *captured*. See ``AXWindowMatch``.
    var axFrame: CGRect? { get }
    var axChildren: [any AXElementSource] { get }
}

extension AXElementSource {
    /// Almost nothing on screen has an address, so not answering is the ordinary case rather than a
    /// gap to be filled at every conformance.
    public var axURL: String? { nil }

    /// Only windows are ever asked where they are, so every other element answers the same absence
    /// rather than each conformance restating it.
    public var axFrame: CGRect? { nil }
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

    /// Ceilings for ``AccessibilityTree/pageHost(of:limits:clock:)``.
    ///
    /// Tighter than ``default`` because this walk runs *before* the gate decides anything, so its
    /// cost is paid on every browser tick including the ones that are about to be refused — and
    /// because it stops at the first address it finds, which is normally within a handful of
    /// elements of the window. The text ceilings are zero: nothing here reads text.
    public static let urlProbe = AXCaptureLimits(
        maxDepth: 24,
        maxNodes: 400,
        maxTextCharacters: 0,
        maxTotalTextCharacters: 0,
        budget: 0.1)
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
