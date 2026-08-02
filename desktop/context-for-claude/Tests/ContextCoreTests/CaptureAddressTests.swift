import CoreGraphics
import Foundation
import XCTest

@testable import ContextCore

/// Whether "exclude this website" excludes anything, judged on the evidence capture really has.
///
/// This file exists because the test that was supposed to cover it was green and worthless. It
/// asserted a browser window titled `Barclays | barclays.co.uk` — a shape that occurs **0 times in
/// 955 real browser frames** on this machine's database, because a browser titles its window with
/// the *page* title (`LinkedIn`, `Anthropic`, `Apple Inc.`). Meanwhile 133 of those frames carried a
/// host in their accessibility text, which the gate never saw. So the pane offered the user domains
/// it could not hide, the test agreed with the pane, and neither of them agreed with the machine.
///
/// Every window built here is therefore shaped like one that was actually recorded: the title is a
/// page title with no host in it, and the address lives where a browser really puts it — on the
/// `AXWebArea`, which is present 236 times in the stored trees, so the walk demonstrably reaches it.
final class CaptureAddressTests: XCTestCase {

    private var root: URL!

    override func setUpWithError() throws {
        root = FileManager.default.temporaryDirectory
            .appendingPathComponent("capture-address-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: root)
    }

    // MARK: - 1. The bug, stated as the two subjects capture can build

    /// The regression. A real browser window on an excluded domain, judged the way capture judged it
    /// before the address was read and the way it judges it now.
    ///
    /// The first assertion is the defect preserved: with only the title — the *real* title, not an
    /// invented one — the gate admits a bank. If a future change stops putting the address on the
    /// subject, the second assertion is what fails, and this one explains why it matters.
    func testABankIsRefusedFromTheAddressAndNotFromTheTitleARealBrowserWrites() throws {
        let engine = makeEngine()
        engine.setCategory(.banks, excluded: true)

        // What the window server and the front application give you: a page title.
        let titleOnly = CaptureSubject(
            bundleID: "company.thebrowser.Browser", appName: "Arc", windowTitle: "Barclays")
        XCTAssertNil(
            engine.exclusionReason(for: titleOnly),
            "the title is not evidence — this is the hole the address closes, kept here so it "
                + "cannot be mistaken for coverage")

        // What the accessibility tree gives you, read through the production walker.
        let window = arcWindow(title: "Barclays", pageURL: "https://www.barclays.co.uk/mortgages/")
        let address = try XCTUnwrap(
            AccessibilityTree.pageHost(of: window), "no address was read from a browser window")

        var judged = titleOnly
        judged.url = address
        XCTAssertEqual(
            engine.exclusionReason(for: judged), .excludedWebsite(pattern: "barclays.co.uk"),
            "an excluded bank was captured with its address in hand")
    }

    /// The address is read from where browsers put it, not from where the window title is.
    func testTheAddressIsReadFromTheWebAreaOfAWindowWhoseTitleNamesNoHost() throws {
        let window = arcWindow(title: "Anthropic", pageURL: "https://www.anthropic.com/news")

        XCTAssertTrue(
            DomainMatcher.hostCandidates(in: "Anthropic").isEmpty,
            "the fixture must be a title that really yields nothing, or this proves nothing")
        XCTAssertEqual(AccessibilityTree.pageHost(of: window), "www.anthropic.com")
    }

    /// The host, and nothing after it.
    ///
    /// The gate normalises to a host as its first act, so the path and the query were only ever
    /// carried — and what they carry is a password-reset token, a document id, a search term, on a
    /// `Codable` subject that travels with the capture all the way to the write barrier. Data that
    /// is never read cannot be leaked if it is never taken.
    func testTheAddressCarriesNothingAfterTheHost() {
        let window = arcWindow(
            title: "Reset your password",
            pageURL: "https://accounts.example.com/reset?token=super-secret-value#step2")

        XCTAssertEqual(AccessibilityTree.pageHost(of: window), "accounts.example.com")
    }

    /// Safari puts it on the window itself, and the window is the shallowest element there is.
    ///
    /// Shallowest-wins is the rule rather than an accident of traversal order: an embedded frame,
    /// an ad, or a preview pane is deeper than the page containing it, and the page is what the
    /// user is on.
    func testTheShallowestAddressWinsSoAnEmbeddedFrameCannotImpersonateThePage() {
        let window = FakeElement(
            role: "AXWindow", title: "Reading", url: "https://example.com/article",
            children: [
                FakeElement(
                    role: "AXGroup",
                    children: [
                        FakeElement(role: "AXWebArea", url: "https://ads.elsewhere.net/frame")
                    ])
            ])

        XCTAssertEqual(AccessibilityTree.pageHost(of: window), "example.com")
    }

    /// Only a website is an answer. Everything else has to read as *no* address.
    ///
    /// Not pedantry: a subject that carries a URL suppresses the weaker evidence beneath it, so
    /// answering `file:///…` or `about:blank` here would silence the gate on exactly the frames
    /// where the fallback is the only protection there is.
    func testNonWebAddressesAreNotAnswers() {
        for raw in [
            "file:///Users/someone/Documents/statement.pdf",
            "about:blank",
            "chrome://settings/passwords",
            "https://",
            "   ",
        ] {
            let window = FakeElement(role: "AXWindow", title: "Something", url: raw)
            XCTAssertNil(
                AccessibilityTree.pageHost(of: window),
                "\(raw.debugDescription) was treated as the address of a website")
        }
    }

    /// The probe runs against another process on every browser tick, so it must degrade rather than
    /// stall. A tree that answers forever costs a missing URL, not a wedged pipeline.
    func testTheProbeIsBoundedByNodesAndByTheClock() {
        XCTAssertNil(
            AccessibilityTree.pageHost(of: CyclicElement(), limits: .urlProbe),
            "a tree with no end must terminate without an address rather than not terminate")

        // A clock that runs a second per question, so the 0.1 s budget is spent before the first
        // element is looked at. Injected for the same reason the walker's is: this must be a fact
        // about the probe rather than about how fast the machine running the test happens to be.
        var ticks = 0.0
        let clock: @Sendable () -> TimeInterval = {
            ticks += 1
            return ticks
        }
        XCTAssertNil(
            AccessibilityTree.pageHost(
                of: FakeElement(role: "AXWindow", url: "https://example.com/"),
                limits: .urlProbe, clock: clock),
            "a spent time budget must stop the walk")
    }

    // MARK: - 2. What `emit` re-judges, and what it must not

    /// The second half of the same bug. The accessibility text arrives *after* admission, so the
    /// gate has never seen it — and it was written to a permanent, searchable database unexamined.
    func testTextArrivingAfterAdmissionIsStillJudged() throws {
        let engine = makeEngine()
        engine.excludeWebsite("mail.proton.me")

        // Admitted with nothing that names the site: the address could not be read this tick.
        let ticket = try XCTUnwrap(
            engine.admit(
                CaptureSubject(
                    bundleID: "company.thebrowser.Browser", appName: "Arc", windowTitle: "Inbox")
            ).ticket)
        XCTAssertNil(engine.revalidate(ticket), "nothing has changed and nothing new has arrived")

        XCTAssertEqual(
            engine.revalidate(ticket, pageText: "Inbox\nmail.proton.me\nDrafts\nSent"),
            .excludedWebsite(pattern: "mail.proton.me"),
            "text naming an excluded site reached the database without ever being judged")
    }

    /// …and the limit on that, which is what keeps it from being a wrecking ball.
    ///
    /// Page text names hosts constantly — a `t.co` link in a quoted tweet, a sidebar listing every
    /// other open tab. Those are mentions, not destinations. When the address *was* read, it is the
    /// answer, and the mentions underneath it are ignored.
    func testAMentionInThePageIsNotADestinationWhenTheAddressIsKnown() throws {
        let engine = makeEngine()
        engine.excludeWebsite("chase.com")

        var subject = CaptureSubject(
            bundleID: "company.thebrowser.Browser", appName: "Arc", windowTitle: "Hacker News")
        subject.url = "https://news.ycombinator.com/item?id=1"
        subject.pageText = "Comments about chase.com and its outage"
        XCTAssertNil(
            engine.exclusionReason(for: subject),
            "an article mentioning a bank is not the bank, and losing it would make the whole "
                + "control unusable")

        // With no address, the same text is all there is, and refusing is the right direction.
        subject.url = nil
        XCTAssertEqual(
            engine.exclusionReason(for: subject), .excludedWebsite(pattern: "chase.com"))
    }

    /// Page text is browsers only, for the same reason the title is: a domain in an editor is a
    /// filename, and a domain in a chat window is something someone typed.
    func testPageTextIsOnlyEvidenceInsideABrowser() {
        let engine = makeEngine()
        engine.excludeWebsite("barclays.co.uk")

        let editor = CaptureSubject(
            bundleID: "com.apple.dt.Xcode", appName: "Xcode", windowTitle: "Statement.swift",
            pageText: "let host = \"barclays.co.uk\"")

        XCTAssertNil(engine.exclusionReason(for: editor))
    }

    // MARK: - 3. Which window the address was read from

    /// The defect this section exists for, and it is worse than the one above.
    ///
    /// The pixels are the largest window of the frontmost application. The address was read from
    /// whichever window that application said was *focused*. A large browser window on a bank behind
    /// a small focused window on something else is all it takes for those to disagree — and the
    /// disagreement did not merely fail to exclude the bank. Because an address outranks the page
    /// text beneath it, the *unexcluded* window's address switched off the one tier that fires on
    /// real frames (133 of 955, against 0 from titles), so the bank was captured with its own name
    /// sitting unread in its own accessibility text.
    func testTheAddressIsReadFromTheWindowThePixelsCameFromAndNotFromTheFocusedOne() throws {
        let engine = makeEngine()
        engine.setCategory(.banks, excluded: true)

        let bank = arcWindow(
            title: "Barclays", pageURL: "https://www.barclays.co.uk/mortgages/",
            frame: CGRect(x: 0, y: 0, width: 1_600, height: 1_000))
        let focused = arcWindow(
            title: "Pull requests", pageURL: "https://github.com/omi/omi/pulls",
            frame: CGRect(x: 1_600, y: 40, width: 620, height: 420))
        // What the capture filter was built from: the larger window. Its title and its frame are
        // the only two things the window-server snapshot knows about it.
        let captured = CapturedWindow(
            frame: try XCTUnwrap(bank.axFrame), title: "Barclays")

        // The shipped behaviour, preserved so the regression stays legible: the focused window's
        // address, attached to the captured window's frame, admits a bank whose own text names it.
        var asShipped = CaptureSubject(
            bundleID: "company.thebrowser.Browser", appName: "Arc", windowTitle: "Barclays")
        asShipped.url = AccessibilityTree.pageHost(of: focused)
        asShipped.pageText = "Barclays\nbarclays.co.uk\nYour accounts\nPay someone"
        XCTAssertNil(
            engine.exclusionReason(for: asShipped),
            "an address from another window silenced the window's own text — the frame this "
                + "describes was written")

        // What happens now: the window is identified before it is read, and reading the right
        // window is what produces the right address.
        let matched = try XCTUnwrap(
            AXWindowMatch.window(matching: captured, in: [focused, bank]),
            "the captured window was unambiguous and still could not be identified")
        var judged = asShipped
        judged.url = AccessibilityTree.pageHost(of: matched)
        XCTAssertEqual(
            engine.exclusionReason(for: judged), .excludedWebsite(pattern: "barclays.co.uk"))
    }

    /// Geometry decides when the title cannot, because a title is the thing that changes.
    ///
    /// The snapshot the frame comes from lives for seconds, and in those seconds a browser tab
    /// switch rewrites the title. The window has not moved, so the rectangle still identifies it.
    func testAWindowWhoseTitleMovedOnIsStillIdentifiedByWhereItIs() throws {
        let frame = CGRect(x: 12, y: 44, width: 1_200, height: 800)
        let renamed = arcWindow(
            title: "barclays.co.uk/mortgages", pageURL: "https://www.barclays.co.uk/mortgages/",
            frame: frame)
        let other = arcWindow(
            title: "Anthropic", pageURL: "https://www.anthropic.com/",
            frame: CGRect(x: 1_400, y: 44, width: 600, height: 400))

        let matched = AXWindowMatch.window(
            matching: CapturedWindow(frame: frame, title: "Barclays"), in: [renamed, other])

        XCTAssertEqual(AccessibilityTree.pageHost(of: try XCTUnwrap(matched)), "www.barclays.co.uk")
    }

    /// Two candidates is not a coin toss. Nothing is read at all.
    ///
    /// Two identically sized, identically titled windows — a tiled pair, a duplicated document — can
    /// be told apart by nothing the snapshot carries, and guessing has a fifty percent chance of
    /// attaching one window's address to the other's picture. That is the failure this whole
    /// mechanism exists to prevent, so ambiguity resolves to no evidence rather than to half of it.
    func testAmbiguityYieldsNoWindowRatherThanAGuess() {
        let frame = CGRect(x: 0, y: 0, width: 900, height: 700)
        let left = arcWindow(title: "Untitled", pageURL: "https://one.example.com/", frame: frame)
        let right = arcWindow(title: "Untitled", pageURL: "https://two.example.com/", frame: frame)

        XCTAssertNil(
            AXWindowMatch.window(
                matching: CapturedWindow(frame: frame, title: "Untitled"), in: [left, right]))
        // And a window that answers neither question is not the captured one either.
        XCTAssertNil(
            AXWindowMatch.window(
                matching: CapturedWindow(frame: frame, title: "Untitled"),
                in: [arcWindow(title: nil, pageURL: "https://three.example.com/", frame: nil)]))
    }

    /// One window needs no proof, and this clause is why the fix is not a regression.
    ///
    /// Measured live on this machine (macOS 26): `AXFocusedWindow` answers the **application
    /// element** for Warp and for Arc — no frame, no window title, children that are the application
    /// again and a menu bar. The same degeneracy is documented in this app's onboarding code for
    /// System Settings' `AXWindows`. Demanding identity unconditionally would therefore have
    /// converted "the gate reads the wrong window" into "the gate reads nothing", which is the
    /// larger of the two failures and lands on more machines.
    ///
    /// The distinction the rule draws is exact: the wrong window is only *reachable* when there is
    /// more than one window.
    func testOneWindowNeedsNoProofAndTwoWindowsAlwaysDo() {
        // What macOS actually handed back for a browser: the application element.
        let opaque = FakeElement(role: "AXApplication", title: "Arc")
        var captured = CapturedWindow(
            frame: CGRect(x: 0, y: 0, width: 1_440, height: 900), title: "Barclays",
            wasOnlyWindow: true)

        XCTAssertTrue(
            AXWindowMatch.isCapturedWindow(opaque, matching: captured),
            "with one window on screen there is nothing else this could have been, and refusing "
                + "here costs the address on every application that will not name its windows")

        captured.wasOnlyWindow = false
        XCTAssertFalse(
            AXWindowMatch.isCapturedWindow(opaque, matching: captured),
            "an answer that names no window proves nothing once there are two windows to choose "
                + "between — which is the only case where reading the wrong one is possible")
    }

    /// An address the gate cannot match on must not silence the text beneath it.
    ///
    /// Suppression is earned by a host, never by the mere presence of a string in the field. A
    /// `file://` URL, a stray fragment, whitespace: none of them can ever match a pattern, so
    /// treating them as an authoritative answer switched off the window's own text at exactly the
    /// moment that text was the only evidence left.
    func testAnAddressThatNamesNoHostCannotSilenceTheWindowsOwnText() {
        let engine = makeEngine()
        engine.excludeWebsite("mail.proton.me")

        var subject = CaptureSubject(
            bundleID: "company.thebrowser.Browser", appName: "Arc", windowTitle: "Inbox")
        subject.pageText = "Inbox\nmail.proton.me\nDrafts\nSent"

        for unusable in ["file:///Users/someone/statement.pdf", "   ", "://"] {
            subject.url = unusable
            XCTAssertEqual(
                engine.exclusionReason(for: subject),
                .excludedWebsite(pattern: "mail.proton.me"),
                "\(unusable.debugDescription) names no host and still silenced the page text")
        }
    }

    // MARK: - Helpers

    private func makeEngine() -> ExclusionEngine {
        ExclusionEngine(
            configurationURL: root.appendingPathComponent("exclusions.json"),
            framesRoot: root.appendingPathComponent("Frames", isDirectory: true))
    }

    /// A window shaped like the ones in this machine's database: a page title, chrome above, and the
    /// address on the web area rather than anywhere a title-based rule could find it.
    private func arcWindow(
        title: String?, pageURL: String, frame: CGRect? = CGRect(x: 0, y: 0, width: 1_440, height: 900)
    ) -> FakeElement {
        FakeElement(
            role: "AXWindow", title: title, frame: frame,
            children: [
                FakeElement(
                    role: "AXGroup", title: "Toolbar",
                    children: [FakeElement(role: "AXButton", title: "Back")]),
                FakeElement(
                    role: "AXSplitGroup",
                    children: [
                        FakeElement(
                            role: "AXGroup", title: "Sidebar",
                            children: [FakeElement(role: "AXStaticText", value: "Gmail")]),
                        FakeElement(
                            role: "AXWebArea", url: pageURL,
                            children: [FakeElement(role: "AXStaticText", value: title)]),
                    ]),
            ])
    }
}

// MARK: - Fakes

/// An accessibility element built in memory, including the address and the place a real one can
/// answer.
private struct FakeElement: AXElementSource {
    var axRole: String?
    var axSubrole: String?
    var axTitle: String?
    var axValue: String?
    var axDescription: String?
    var axURL: String?
    var axFrame: CGRect?
    var kids: [FakeElement] = []

    var axChildren: [any AXElementSource] { kids }

    init(
        role: String?,
        subrole: String? = nil,
        title: String? = nil,
        value: String? = nil,
        url: String? = nil,
        frame: CGRect? = nil,
        children: [FakeElement] = []
    ) {
        axFrame = frame
        axRole = role
        axSubrole = subrole
        axTitle = title
        axValue = value
        axURL = url
        kids = children
    }
}

/// An element that is its own child, which a real accessibility tree can be. It answers no address,
/// so the only thing that can end the walk is a ceiling.
private struct CyclicElement: AXElementSource {
    var axRole: String? { "AXGroup" }
    var axSubrole: String? { nil }
    var axTitle: String? { nil }
    var axValue: String? { nil }
    var axDescription: String? { nil }

    var axChildren: [any AXElementSource] { [self] }
}
