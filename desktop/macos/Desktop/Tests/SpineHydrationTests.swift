//
//  SpineHydrationTests.swift — the two rules that decide whether the spine is the whole account.
//
//  Both are keyed against a defect that shipped. The first is the end-of-list inference: the backend
//  post-filters every page it returns, so a request for 100 memories answering with 97 is a *full*
//  page, and the client reading that as "the end" made five thousand memories unreachable with no
//  error anywhere. The second is the loop that walks the rest of the corpus in — it must finish, it
//  must not hot-loop on a broken source, and it must say plainly when it gave up.
//

import Combine
import XCTest

@testable import Omi_Computer

final class ServerPagingTests: XCTestCase {
  /// The exact shape observed live: `GET /v3/memories?limit=100` answered with 97 rows because the
  /// backend drops rejected/superseded documents in Python after the Firestore `limit`.
  func testAPageShorterThanRequestedIsStillNotTheEnd() {
    XCTAssertTrue(ServerPaging.hasMore(received: 97))
    XCTAssertTrue(ServerPaging.hasMore(received: 1))
  }

  func testOnlyAnEmptyPageEndsTheList() {
    XCTAssertFalse(ServerPaging.hasMore(received: 0))
    XCTAssertFalse(ServerPaging.hasMore(received: 0, loaded: 10, total: 995))
  }

  func testAnAuthoritativeTotalStopsPagingEarly() {
    XCTAssertTrue(ServerPaging.hasMore(received: 50, loaded: 50, total: 995))
    XCTAssertFalse(ServerPaging.hasMore(received: 50, loaded: 995, total: 995))
  }

  /// A count that disagrees with the list must not leave a caller paging forever; the empty page is
  /// still the authority.
  func testAnUnknownTotalNeverStopsPaging() {
    XCTAssertTrue(ServerPaging.hasMore(received: 3, loaded: 10_000, total: nil))
  }

  // MARK: - Merging a page

  /// The memories query orders by a mutable `scoring`, so a row can move between two pages fetched
  /// seconds apart and arrive in both. Appending blind puts it in the list twice.
  func testAPageThatOverlapsTheOneBeforeItAddsOnlyWhatIsNew() {
    let held = ["a", "b", "c"]
    XCTAssertEqual(
      ServerPaging.appending(["c", "d", "e"], to: held, by: \.self), ["a", "b", "c", "d", "e"])
  }

  func testMergingKeepsTheRowsAlreadyHeldAndTheirOrder() {
    XCTAssertEqual(ServerPaging.appending(["b", "a"], to: ["a", "b"], by: \.self), ["a", "b"])
    XCTAssertEqual(ServerPaging.appending([], to: ["a"], by: \.self), ["a"])
    XCTAssertEqual(ServerPaging.appending(["a", "a", "b"], to: [], by: \.self), ["a", "b"])
  }
}

// MARK: - What the end of the list is allowed to say

final class SpineFootTests: XCTestCase {
  /// **The property under test is the signature, not the body.** The footer used to be gated on
  /// `!request.isFiltering` and withdrew entirely under a filter — taking with it the only thing on
  /// screen admitting the account went further back. `resolve` has no filter parameter, so a
  /// filtered spine and an unfiltered one report the same corpus by construction.
  func testTheFootIsResolvedWithoutAnyKnowledgeOfTheFilter() {
    XCTAssertEqual(SpineFoot.resolve(corpus: .whole, canLoadMore: false), .nothing)
    XCTAssertEqual(
      SpineFoot.resolve(corpus: .whole, canLoadMore: true), .nothing,
      "a whole corpus ends, even if a stale cursor still claims a page")
    XCTAssertEqual(SpineFoot.resolve(corpus: .partial, canLoadMore: true), .loadMore)
    XCTAssertEqual(SpineFoot.resolve(corpus: .partial, canLoadMore: false), .nothing)
  }

  func testFillingSaysHowFarAlongItIs() {
    XCTAssertEqual(
      SpineFoot.resolve(corpus: .filling(conversations: 250, of: 995), canLoadMore: true),
      .note("Loading your history… 250 of 995 conversations"))
  }

  /// Without a credible total the sentence drops the numbers rather than inventing a denominator —
  /// including the case where the count is stale and smaller than what is already loaded.
  func testFillingNeverInventsADenominator() {
    XCTAssertEqual(
      SpineFoot.fillingNote(conversations: 250, of: nil), "Loading the rest of your history…")
    XCTAssertEqual(
      SpineFoot.fillingNote(conversations: 995, of: 995), "Loading the rest of your history…")
  }
}

// MARK: - What an empty spine says

final class SpineEmptyCopyTests: XCTestCase {
  private func request(_ text: String = "", kind: QueryShellKind = .all) -> QueryShellRequest {
    QueryShellRequest(text: text, kind: kind)
  }

  /// The worse half of the same lie: a filter narrow enough to match nothing in the pages loaded so
  /// far empties the list, which takes the footer off screen with it — so the surface answered
  /// "nothing matches" while pages that might match were still arriving.
  func testAnEmptySpineDoesNotClaimNothingMatchedWhilePagesAreStillArriving() {
    let copy = SpineEmptyCopy.resolve(
      isPreparing: false,
      request: request("charlie", kind: .memories),
      kind: .memories,
      foot: .note("Loading your history… 250 of 995 conversations")
    )
    XCTAssertEqual(copy.headline, "Nothing here yet — still loading.")
    XCTAssertEqual(copy.detail, "Loading your history… 250 of 995 conversations")
  }

  /// When nothing is fetching and pages remain, the empty state has to admit the answer is partial.
  /// The footer rendered beneath it is the way out.
  func testAnEmptySpineAdmitsAPartialAnswerWhenPagesRemain() {
    let copy = SpineEmptyCopy.resolve(
      isPreparing: false, request: request("charlie"), kind: .everything, foot: .loadMore)
    XCTAssertEqual(copy.headline, "Nothing captured matches “charlie”.")
    XCTAssertEqual(copy.detail, "Some of your history isn’t loaded yet.")
  }

  /// Only once the corpus is whole may the surface make a claim about the account.
  func testOnlyAWholeCorpusMayClaimNothingMatched() {
    let searched = SpineEmptyCopy.resolve(
      isPreparing: false, request: request("charlie"), kind: .everything, foot: .nothing)
    XCTAssertEqual(searched.headline, "Nothing captured matches “charlie”.")
    XCTAssertEqual(searched.detail, "Press ⌘⏎ to ask Omi instead.")

    let resting = SpineEmptyCopy.resolve(
      isPreparing: false, request: request(), kind: .memories, foot: .nothing)
    XCTAssertEqual(resting.headline, "Nothing captured in this window yet.")
    XCTAssertEqual(resting.detail, "Memories appear here as Omi learns things worth keeping.")
  }

  func testTheFirstReadOffersNoExplanationBecauseThereIsNothingToExplainYet() {
    let copy = SpineEmptyCopy.resolve(
      isPreparing: true, request: request(), kind: .everything, foot: .note("…"))
    XCTAssertEqual(copy.headline, "Reading your day…")
    XCTAssertNil(copy.detail)
  }
}

// MARK: - The loop

/// A paged store with a known corpus behind it, so a test can assert what the loop asked for.
@MainActor
private final class FakeCorpus {
  let corpus: Int
  let pageSize: Int
  /// Pages that answer with nothing and do not advance — a failing endpoint, not an empty one.
  let failing: Bool
  private(set) var loaded = 0
  private(set) var requests = 0
  private(set) var reachedEnd = false

  init(corpus: Int, pageSize: Int, failing: Bool = false) {
    self.corpus = corpus
    self.pageSize = pageSize
    self.failing = failing
  }

  /// What an activation refresh does to a hydrated list: replaces it with a clamped page.
  func truncate(to rows: Int) {
    loaded = rows
    reachedEnd = false
  }

  var source: SpinePageSource {
    SpinePageSource(
      hasMore: { [unowned self] in !self.reachedEnd },
      loadedCount: { [unowned self] in self.loaded },
      total: { [unowned self] in self.corpus },
      loadMore: { [unowned self] in
        self.requests += 1
        guard !self.failing else { return }
        let page = min(self.pageSize, self.corpus - self.loaded)
        self.loaded += page
        // The store's own end-of-list rule, which is the one under test everywhere else.
        self.reachedEnd = !ServerPaging.hasMore(received: page)
      }
    )
  }
}

/// The order pages were asked for in, recorded across both sources.
@MainActor
private final class PageLogbook {
  private(set) var order: [String] = []
  func append(_ name: String) { order.append(name) }
}

/// Counts calls without a corpus behind them, for the ordering assertion.
@MainActor
private final class PageCounter {
  private(set) var remaining: Int
  private(set) var served = 0
  private let name: String
  private let log: PageLogbook

  init(name: String, pages: Int, log: PageLogbook) {
    self.name = name
    self.remaining = pages
    self.log = log
  }

  var source: SpinePageSource {
    SpinePageSource(
      hasMore: { [unowned self] in self.remaining > 0 },
      loadedCount: { [unowned self] in self.served },
      loadMore: { [unowned self] in
        self.log.append(self.name)
        self.remaining -= 1
        self.served += 1
      }
    )
  }
}

@MainActor
final class SpineHydrationTests: XCTestCase {
  func testHydrationPagesASourceAllTheWayToTheEnd() async {
    let conversations = FakeCorpus(corpus: 995, pageSize: 50)
    let memories = FakeCorpus(corpus: 5_849, pageSize: 100)
    let hydrator = SpineHydrator()

    await hydrator.hydrate([conversations.source, memories.source])

    XCTAssertEqual(conversations.loaded, 995)
    XCTAssertEqual(memories.loaded, 5_849)
    XCTAssertEqual(hydrator.state, .whole)
  }

  /// The price of the honest end-of-list rule, stated so nobody "optimises" it back into the bug:
  /// twenty full pages plus one empty page that proves there is nothing behind them.
  func testTheEndCostsExactlyOneExtraRequestPerList() async {
    let conversations = FakeCorpus(corpus: 1_000, pageSize: 50)

    await SpineHydrator().hydrate([conversations.source])

    XCTAssertEqual(conversations.requests, 21)
  }

  /// Conversations decide which days exist and memories decide how deep each day is. Draining one
  /// before touching the other would leave the spine reaching back a year with nothing under the
  /// headers, or one deep day and no history.
  func testHydrationInterleavesItsSourcesRatherThanDrainingOne() async {
    let log = PageLogbook()
    let conversations = PageCounter(name: "conversation", pages: 3, log: log)
    let memories = PageCounter(name: "memory", pages: 3, log: log)

    await SpineHydrator().hydrate([conversations.source, memories.source])

    XCTAssertEqual(
      log.order, ["conversation", "memory", "conversation", "memory", "conversation", "memory"])
  }

  /// A source that answers an error forever reports it only by not growing. Without the stall
  /// detector that is an unbounded retry loop against a failing endpoint.
  func testAFailingSourceIsAbandonedAfterTheStallLimitRatherThanRetriedForever() async {
    let broken = FakeCorpus(corpus: 995, pageSize: 50, failing: true)
    let hydrator = SpineHydrator()

    await hydrator.hydrate([broken.source])

    XCTAssertEqual(broken.requests, SpineHydrator.stallLimit)
    XCTAssertEqual(broken.loaded, 0)
    XCTAssertEqual(
      hydrator.state, .partial,
      "giving up with pages remaining is a partial spine, and the footer has to be able to say so")
  }

  /// The state the panel renders: filling while it runs, whole only when nothing is outstanding.
  func testStateReportsProgressWhileFillingAndWholeOnlyAtTheEnd() async {
    let conversations = FakeCorpus(corpus: 120, pageSize: 50)
    let hydrator = SpineHydrator()
    XCTAssertEqual(hydrator.state, .partial, "before hydration runs, nothing is known to be whole")

    var seen: [SpineCorpusState] = []
    let observer = hydrator.$state.sink { seen.append($0) }
    defer { observer.cancel() }

    await hydrator.hydrate([conversations.source])

    XCTAssertEqual(hydrator.state, .whole)
    XCTAssertTrue(
      seen.contains(.filling(conversations: 50, of: 120)),
      "the footer counts conversations, because they are what the spine's reach in days is made of")
  }

  /// The stream re-evaluates its body constantly; a second `start` must not run the cursors twice.
  func testStartIsIdempotentSoTheCursorsAreNeverPagedTwice() async {
    let conversations = FakeCorpus(corpus: 100, pageSize: 50)
    let memories = FakeCorpus(corpus: 0, pageSize: 100)
    let hydrator = SpineHydrator()

    hydrator.start(conversations: conversations.source, memories: memories.source)
    hydrator.start(conversations: conversations.source, memories: memories.source)
    for _ in 0..<1_000 where !conversations.reachedEnd {
      await Task.yield()
    }
    hydrator.stop()

    XCTAssertTrue(conversations.reachedEnd, "the background run reached the end of the corpus")
    XCTAssertEqual(conversations.requests, 3, "two full pages plus the empty one, asked for once each")
    XCTAssertEqual(conversations.loaded, 100)
  }

  /// A finished hydration is not permanent: the Memories page's activation refresh replaces its
  /// whole loaded window with a server-clamped page and reopens `hasMore`. Without a resume, the
  /// spine silently shortens for the rest of the session.
  func testHydrationResumesWhenAStoreIsTruncatedUnderIt() async {
    let conversations = FakeCorpus(corpus: 100, pageSize: 50)
    let hydrator = SpineHydrator()

    hydrator.start(conversations: conversations.source, memories: conversations.source)
    for _ in 0..<1_000 where !conversations.reachedEnd { await Task.yield() }
    XCTAssertEqual(conversations.loaded, 100)

    conversations.truncate(to: 20)
    hydrator.resume()
    for _ in 0..<1_000 where !conversations.reachedEnd { await Task.yield() }

    XCTAssertEqual(conversations.loaded, 100, "the spine refills itself instead of staying short")
    XCTAssertEqual(hydrator.state, .whole)
  }

  /// The counterpart: a source abandoned for stalling must not be picked back up on every ingest,
  /// which would turn a broken endpoint into a request per keystroke.
  func testAnAbandonedSourceIsNeverResumed() async {
    let broken = FakeCorpus(corpus: 995, pageSize: 50, failing: true)
    let hydrator = SpineHydrator()

    await hydrator.hydrate([broken.source, broken.source])
    let afterFirstRun = broken.requests
    XCTAssertEqual(afterFirstRun, 2 * SpineHydrator.stallLimit)
    hydrator.resume()
    hydrator.resume()
    await Task.yield()

    XCTAssertEqual(broken.requests, afterFirstRun)
    XCTAssertEqual(hydrator.state, .partial)
  }
}
