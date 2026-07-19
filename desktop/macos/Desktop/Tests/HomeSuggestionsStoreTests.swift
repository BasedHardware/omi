import XCTest

@testable import Omi_Computer

// MARK: - Composer

final class HomeSuggestionComposerTests: XCTestCase {
  func testComposeUsesPersonalizedPairAfterUniversalFirst() {
    let chips = HomeSuggestionComposer.compose(
      personalized: ["How do I unblock the Atlas launch?", "Is the hiring loop for EE on track?"],
      onboarding: ["What email follow-ups matter most today?"]
    )

    XCTAssertEqual(
      chips,
      [
        "What should I do today?",
        "How do I unblock the Atlas launch?",
        "Is the hiring loop for EE on track?",
      ]
    )
  }

  func testComposeFallsBackToOnboardingThenStatic() {
    let onboardingSaved = [
      "What should I focus on today to achieve my goals?",
      "What email follow-ups matter most today?",
      "Where can I find focus time this week?",
    ]
    XCTAssertEqual(
      HomeSuggestionComposer.compose(personalized: [], onboarding: onboardingSaved),
      [
        "What should I do today?",
        "What email follow-ups matter most today?",
        "Where can I find focus time this week?",
      ]
    )

    XCTAssertEqual(
      HomeSuggestionComposer.compose(personalized: [], onboarding: []),
      [
        "What should I do today?",
        "What did I spend my time on this week?",
        "What's the highest-leverage thing I can do next?",
      ]
    )
  }

  func testComposeTopsUpSinglePersonalizedQuestionFromFallbacks() {
    let chips = HomeSuggestionComposer.compose(
      personalized: ["How do I unblock the Atlas launch?"],
      onboarding: []
    )

    XCTAssertEqual(
      chips,
      [
        "What should I do today?",
        "How do I unblock the Atlas launch?",
        "What did I spend my time on this week?",
      ]
    )
  }

  func testSanitizeDropsLongDuplicateUniversalAndEmptyQuestions() {
    let sanitized = HomeSuggestionComposer.sanitize([
      "  How do I unblock the Atlas launch?  ",
      "how do i unblock the atlas launch?",
      "What should I do today?",
      "WHAT SHOULD I FOCUS ON TODAY TO ACHIEVE MY GOALS?",
      "",
      "   ",
      String(repeating: "x", count: HomeSuggestionComposer.maxPersonalizedLength + 1),
    ])

    XCTAssertEqual(sanitized, ["How do I unblock the Atlas launch?"])
  }
}

// MARK: - Store

private final class StubSuggestionGenerator: HomeSuggestionGenerating, @unchecked Sendable {
  enum Behavior {
    case respond([String])
    case fail
  }

  private let lock = NSLock()
  private var _behavior: Behavior
  private var _callCount = 0
  private var pendingContinuation: CheckedContinuation<Void, Never>?
  private var gateNextCall = false

  init(behavior: Behavior) {
    _behavior = behavior
  }

  var callCount: Int {
    lock.withLock { _callCount }
  }

  func setBehavior(_ behavior: Behavior) {
    lock.withLock { _behavior = behavior }
  }

  /// Make the next generation call suspend until `resumeGatedCall()`.
  func gateNext() {
    lock.withLock { gateNextCall = true }
  }

  func resumeGatedCall() {
    let continuation = lock.withLock { () -> CheckedContinuation<Void, Never>? in
      let pending = pendingContinuation
      pendingContinuation = nil
      return pending
    }
    continuation?.resume()
  }

  func generatePersonalizedQuestions(
    snapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> [String] {
    let (behavior, gated) = lock.withLock { () -> (Behavior, Bool) in
      _callCount += 1
      let gated = gateNextCall
      gateNextCall = false
      return (_behavior, gated)
    }

    if gated {
      await withCheckedContinuation { continuation in
        lock.withLock { pendingContinuation = continuation }
      }
    }

    switch behavior {
    case .respond(let questions): return questions
    case .fail: throw URLError(.notConnectedToInternet)
    }
  }
}

@MainActor
final class HomeSuggestionsStoreTests: XCTestCase {
  private let ownerFixture = RuntimeOwnerAuthorityTestFixture()

  override func tearDown() async throws {
    await ownerFixture.restore()
  }

  private func makeDefaults() throws -> (UserDefaults, () -> Void) {
    let suite = "HomeSuggestionsStoreTests.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
    return (defaults, { defaults.removePersistentDomain(forName: suite) })
  }

  func testRefreshGeneratesOncePerDayAndRepublishesFromCache() async throws {
    await ownerFixture.establish(authOwnerID: "owner-a")
    let (defaults, cleanup) = try makeDefaults()
    defer { cleanup() }
    let generator = StubSuggestionGenerator(
      behavior: .respond(["How do I unblock the Atlas launch?", "Is the EE hiring loop on track?"]))
    let day = Date(timeIntervalSince1970: 1_700_000_000)
    let store = HomeSuggestionsStore(defaults: defaults, generator: generator, now: { day })

    await store.refreshIfNeeded()
    XCTAssertEqual(generator.callCount, 1)
    XCTAssertEqual(
      store.personalizedQuestions,
      ["How do I unblock the Atlas launch?", "Is the EE hiring loop on track?"]
    )

    await store.refreshIfNeeded()
    XCTAssertEqual(generator.callCount, 1, "same-day refresh must not regenerate")

    // A fresh store over the same defaults publishes from cache without generating.
    let rehydrated = HomeSuggestionsStore(defaults: defaults, generator: generator, now: { day })
    XCTAssertEqual(
      rehydrated.personalizedQuestions,
      ["How do I unblock the Atlas launch?", "Is the EE hiring loop on track?"]
    )
    await rehydrated.refreshIfNeeded()
    XCTAssertEqual(generator.callCount, 1)
  }

  func testRefreshRegeneratesOnNextDay() async throws {
    await ownerFixture.establish(authOwnerID: "owner-a")
    let (defaults, cleanup) = try makeDefaults()
    defer { cleanup() }
    let generator = StubSuggestionGenerator(behavior: .respond(["Day one question?"]))
    var currentDay = Date(timeIntervalSince1970: 1_700_000_000)
    let store = HomeSuggestionsStore(defaults: defaults, generator: generator, now: { currentDay })

    await store.refreshIfNeeded()
    XCTAssertEqual(generator.callCount, 1)

    generator.setBehavior(.respond(["Day two question?"]))
    currentDay = currentDay.addingTimeInterval(60 * 60 * 24)
    await store.refreshIfNeeded()
    XCTAssertEqual(generator.callCount, 2)
    XCTAssertEqual(store.personalizedQuestions, ["Day two question?"])
  }

  func testRefreshSkipsWhenSignedOut() async throws {
    await ownerFixture.establish(authOwnerID: nil)
    let (defaults, cleanup) = try makeDefaults()
    defer { cleanup() }
    let generator = StubSuggestionGenerator(behavior: .respond(["Should not appear?"]))
    let store = HomeSuggestionsStore(defaults: defaults, generator: generator)

    await store.refreshIfNeeded()

    XCTAssertEqual(generator.callCount, 0)
    XCTAssertEqual(store.personalizedQuestions, [])
  }

  func testTransportFailureRetriesButEmptySuccessHoldsForTheDay() async throws {
    await ownerFixture.establish(authOwnerID: "owner-a")
    let (defaults, cleanup) = try makeDefaults()
    defer { cleanup() }
    let generator = StubSuggestionGenerator(behavior: .fail)
    let day = Date(timeIntervalSince1970: 1_700_000_000)
    let store = HomeSuggestionsStore(defaults: defaults, generator: generator, now: { day })

    await store.refreshIfNeeded()
    XCTAssertEqual(generator.callCount, 1)

    // Failure left no cache entry, so the next refresh retries.
    await store.refreshIfNeeded()
    XCTAssertEqual(generator.callCount, 2)

    // A successful-but-empty generation is cached and holds until tomorrow.
    generator.setBehavior(.respond([]))
    await store.refreshIfNeeded()
    XCTAssertEqual(generator.callCount, 3)
    await store.refreshIfNeeded()
    XCTAssertEqual(generator.callCount, 3)
    XCTAssertEqual(store.personalizedQuestions, [])
  }

  func testOwnerSwitchDuringGenerationDropsResultEntirely() async throws {
    await ownerFixture.establish(authOwnerID: "owner-a")
    let (defaults, cleanup) = try makeDefaults()
    defer { cleanup() }
    let generator = StubSuggestionGenerator(behavior: .respond(["Owner A's private question?"]))
    let store = HomeSuggestionsStore(defaults: defaults, generator: generator)

    generator.gateNext()
    let refreshTask = Task { await store.refreshIfNeeded() }

    // Switch accounts while owner A's generation is in flight. The transition
    // revokes the authorization snapshot captured at refresh start.
    while generator.callCount == 0 {
      await Task.yield()
    }
    await ownerFixture.establish(authOwnerID: "owner-b")
    generator.resumeGatedCall()
    await refreshTask.value

    XCTAssertEqual(
      store.personalizedQuestions, [],
      "a result finishing after an account switch must not be published"
    )
    XCTAssertNil(
      defaults.data(forKey: HomeSuggestionsStore.cacheKey(ownerID: "owner-a")),
      "a result finishing after an account switch must not be cached under the original owner"
    )
    XCTAssertNil(
      defaults.data(forKey: HomeSuggestionsStore.cacheKey(ownerID: "owner-b")),
      "a result finishing after an account switch must not be cached under the new owner"
    )

    // The dropped attempt burned nothing: owner A regenerates on return.
    await ownerFixture.establish(authOwnerID: "owner-a")
    await store.refreshIfNeeded()
    XCTAssertEqual(generator.callCount, 2)
    XCTAssertEqual(store.personalizedQuestions, ["Owner A's private question?"])
  }
}
