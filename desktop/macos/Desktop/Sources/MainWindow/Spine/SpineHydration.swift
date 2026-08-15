//
//  SpineHydration.swift — how the spine gets the *whole* account instead of the last few days.
//
//  The spine is a projection over three paged stores, and every one of them handed it a first page
//  and stopped: fifty conversations, one page of memories, and screen capture only for the days
//  those two happened to name. On an account with ~1,000 conversations that is a spine that ends on
//  Tuesday, which is exactly what it looked like.
//
//  **Scroll-triggered paging cannot fix that.** It only ever gets what the user has already scrolled
//  past, it stops dead the moment a filter is on — and a filter is precisely when the unloaded pages
//  matter most — and twenty presses of "load earlier days" is not an answer to "I want all". So this
//  keeps paging in the background after first paint until the corpus is in, and the spine grows
//  underneath whatever the user is doing.
//
//  Three properties make that safe rather than merely eager:
//
//  - **It never blocks first paint.** Hydration starts *after* the first composed spine is on
//    screen; the first page of each store is still the initial load's job.
//  - **It always terminates.** Each source has a page budget and a stall detector, so a failing or
//    misbehaving endpoint costs a bounded number of requests rather than a hot loop. A source that
//    answers an error forever stops after three attempts, not three thousand.
//  - **It is interruptible.** One `Task`, cancelled when the surface goes away, checked after every
//    page.
//
//  It is deliberately *not* concurrent. One page at a time, round-robin between the sources, is what
//  keeps the SQLite writes each page triggers from arriving as a burst, and keeps the main-actor
//  recomposition between pages to one list rebuild rather than several racing ones.
//

import Combine
import Foundation

// MARK: - What the foot of the spine is allowed to claim

/// How much of the account the spine is currently made of.
///
/// The panel has to be able to say this out loud. A spine holding one page of a thousand
/// conversations while showing no footer at all — which is what a filtered spine used to do — is a
/// surface that answers "is that everything?" with a confident, wrong yes.
enum SpineCorpusState: Equatable, Sendable {
  /// Every page the account holds is composed in. The foot of the spine says nothing.
  case whole
  /// Pages are still arriving. `conversations` of `total` is the reach of the spine in days, which
  /// is the part of the progress a person can actually feel.
  case filling(conversations: Int, of: Int?)
  /// Pages remain and nothing is fetching them — hydration finished early, or never ran.
  case partial
}

// MARK: - What the foot of the spine renders

/// The end of the list, as a value.
///
/// **Read the signature of `resolve` before the body: there is no filter in it.** The defect this
/// replaces was a footer gated on `!request.isFiltering`, which withdrew the only thing on screen
/// admitting the account went further back — precisely when the unloaded pages mattered most. A
/// filtered spine and an unfiltered one now report the same corpus, because the corpus is the same
/// corpus, and a parameter that is absent cannot be reintroduced by accident.
enum SpineFoot: Equatable, Sendable {
  /// Everything is loaded. The list simply ends.
  case nothing
  /// Pages are arriving. The line says how far along.
  case note(String)
  /// Pages remain and nothing is fetching them. The manual door.
  case loadMore

  static func resolve(corpus: SpineCorpusState, canLoadMore: Bool) -> SpineFoot {
    switch corpus {
    case .whole:
      return .nothing
    case .filling(let conversations, let total):
      return .note(fillingNote(conversations: conversations, of: total))
    case .partial:
      return canLoadMore ? .loadMore : .nothing
    }
  }

  /// "Loading your history… 250 of 995 conversations".
  ///
  /// It counts conversations rather than everything because conversations are what the spine's
  /// reach in *days* is made of, which is the part of the wait a person can actually feel. Without a
  /// credible total the sentence drops the numbers rather than inventing a denominator.
  static func fillingNote(conversations: Int, of total: Int?) -> String {
    guard let total, total > conversations else { return "Loading the rest of your history…" }
    let loaded = total.formatted(.number.grouping(.automatic))
    let done = conversations.formatted(.number.grouping(.automatic))
    return "Loading your history… \(done) of \(loaded) conversations"
  }
}

// MARK: - A paged store, as the hydrator needs it

/// One of the spine's paged sources, reduced to the four questions hydration asks.
///
/// Closures rather than a protocol so this file depends on neither `AppState` nor
/// `MemoriesViewModel`: the loop is then a value a test can drive against a fake corpus without a
/// network, a database or a view.
struct SpinePageSource {
  /// Whether the store believes another page exists.
  let hasMore: @MainActor () -> Bool
  /// How many rows the store is holding. The hydrator's only progress signal.
  let loadedCount: @MainActor () -> Int
  /// The account's own total for this store, when it knows one.
  let total: @MainActor () -> Int?
  /// Fetch exactly one more page. Must not throw — a source reports failure by not growing.
  let loadMore: @MainActor () async -> Void

  init(
    hasMore: @escaping @MainActor () -> Bool,
    loadedCount: @escaping @MainActor () -> Int,
    total: @escaping @MainActor () -> Int? = { nil },
    loadMore: @escaping @MainActor () async -> Void
  ) {
    self.hasMore = hasMore
    self.loadedCount = loadedCount
    self.total = total
    self.loadMore = loadMore
  }
}

// MARK: - The loop

@MainActor
final class SpineHydrator: ObservableObject {
  /// What the footer renders. Starts `.partial` rather than `.whole` because "we have not looked
  /// yet" and "there is nothing more" are different claims and only one of them is honest.
  @Published private(set) var state: SpineCorpusState = .partial

  /// Pages one source may ask for in a session. 400 pages is 20,000 conversations or 40,000
  /// memories — well past any real account, and a hard stop for a server that pages forever.
  static let maximumPagesPerSource = 400

  /// Consecutive pages that grew the store by nothing before that source is abandoned. Three
  /// because a page can legitimately be all rows the layer filter drops; four in a row is a stuck
  /// cursor or a failing request, and neither improves by asking again.
  static let stallLimit = 3

  private var task: Task<Void, Never>?
  /// The sources of the run in flight, in the order they were handed over. The first is the one the
  /// footer counts, because conversations are what decide how far back in days the spine reaches.
  private var sources: [SpinePageSource] = []
  private var isRunning = false
  /// A source hit its stall limit or its page budget. Nothing restarts after that: whatever is
  /// wrong with it is not fixed by a fresh loop, and the footer already says the spine is partial.
  private var didAbandon = false

  private struct Progress {
    let source: SpinePageSource
    var pages = 0
    var stalls = 0
    var isFinished = false
  }

  /// Begin hydration behind the already-painted spine.
  ///
  /// Idempotent: the stream re-evaluates its body constantly, and a second call must not start a
  /// second loop paging the same cursors.
  func start(conversations: SpinePageSource, memories: SpinePageSource) {
    sources = [conversations, memories]
    resume()
  }

  /// Pick the corpus back up if a store has grown a cursor since the last run finished.
  ///
  /// Necessary because a completed hydration is not permanent: the Memories page's activation
  /// refresh re-requests its whole loaded window and the backend clamps that request, which
  /// replaces a hydrated list with the clamped page and reopens `hasMore`. Without this, visiting
  /// Memories and coming back would silently shorten the spine for the rest of the session.
  func resume() {
    guard !isRunning, !didAbandon, !sources.isEmpty else { return }
    guard sources.contains(where: { $0.hasMore() }) else {
      publish()
      return
    }
    // Claimed synchronously, before the task exists: `start` is called from a view body that can
    // run twice in the same turn, and a flag the loop only raises once it is scheduled would let
    // the second call spawn a second loop over the same cursors.
    isRunning = true
    publish()
    let pending = sources
    task = Task { [weak self] in
      await self?.hydrate(pending)
    }
  }

  /// Explicitly try an abandoned corpus again after the person asks for earlier days.
  ///
  /// Automatic `resume()` deliberately refuses to revive an abandoned source: otherwise every
  /// store update and every keystroke would turn a broken endpoint into another request. A direct
  /// click is different evidence. It is permission to spend one more bounded hydration run, across
  /// every source rather than one conversation page, and to show progress immediately.
  func retry() {
    guard !isRunning, !sources.isEmpty else { return }
    didAbandon = false
    resume()
  }

  /// Stop paging. Leaves the state describing what actually landed.
  func stop() {
    task?.cancel()
    task = nil
    isRunning = false
    publish()
  }

  /// The loop itself, exposed so a test can await it rather than poll a background task.
  ///
  /// - Parameter sources: conversations first — see `sources`.
  func hydrate(_ sources: [SpinePageSource]) async {
    self.sources = sources
    isRunning = true
    publish()
    defer {
      isRunning = false
      publish()
    }

    var progress = sources.map { Progress(source: $0) }
    while !Task.isCancelled {
      var didWork = false
      for index in progress.indices where !progress[index].isFinished {
        let source = progress[index].source
        guard source.hasMore() else {
          progress[index].isFinished = true
          continue
        }
        guard progress[index].pages < Self.maximumPagesPerSource else {
          progress[index].isFinished = true
          didAbandon = true
          continue
        }

        let before = source.loadedCount()
        progress[index].pages += 1
        await source.loadMore()
        if Task.isCancelled { return }
        didWork = true

        // Progress is measured by the store growing, never by the request succeeding: both of these
        // sources swallow their own errors, so a failure reports only as a page that added nothing.
        if source.loadedCount() > before {
          progress[index].stalls = 0
        } else {
          progress[index].stalls += 1
          if progress[index].stalls >= Self.stallLimit {
            progress[index].isFinished = true
            didAbandon = true
          }
        }
        publish()
      }
      guard didWork else { break }
    }
  }

  private func publish() {
    guard let counted = sources.first else { return }
    if isRunning {
      state = .filling(conversations: counted.loadedCount(), of: counted.total())
      return
    }
    state = sources.contains { $0.hasMore() } ? .partial : .whole
  }
}
