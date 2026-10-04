import OmiKit
import XCTest

@testable import OmiUI

// Tests for the mobile onboarding wave: the itinerary/rank helpers over the
// shared `MobileSetupStep` vocabulary, the step-commit rules, and the store
// persistence path (`recordMobileOnboarding` through a real `SettingsStore`
// over an in-memory key-value store).
@MainActor
final class MobileOnboardingTests: XCTestCase {
    private final class MemoryKeyValueStore: KeyValueStoring, @unchecked Sendable {
        private var values: [String: PreferenceValue] = [:]
        private let lock = NSLock()

        func value(forKey key: String) -> PreferenceValue? {
            lock.lock()
            defer { lock.unlock() }
            return values[key]
        }

        func set(_ value: PreferenceValue?, forKey key: String) {
            lock.lock()
            defer { lock.unlock() }
            values[key] = value
        }
    }

    private func makeStore() -> (AppStore, MemoryKeyValueStore) {
        let storage = MemoryKeyValueStore()
        let store = AppStore(
            services: AppServices(settings: SettingsStore(storage: storage)))
        return (store, storage)
    }

    // MARK: Itinerary

    /// Native phones skip the browser-only speech step (upstream
    /// `mobileItinerary(nativePhone:)`).
    func testItinerarySkipsSpeechOnPhones() {
        let shipped = mobileOnboardingItinerary()
        XCTAssertEqual(
            shipped,
            [.consent, .name, .language, .source, .permissions, .knowledge,
             .complete])
        XCTAssertFalse(shipped.contains(.speech))
        let withSpeech = mobileOnboardingItinerary(includesSpeech: true)
        XCTAssertEqual(withSpeech.count, MobileSetupStep.allCases.count)
    }

    /// Welcome sits before the setup steps; ranks follow itinerary order.
    func testRankFollowsItinerary() {
        let itinerary = mobileOnboardingItinerary()
        XCTAssertEqual(
            mobileOnboardingRank(.welcome, itinerary: itinerary), -1)
        XCTAssertEqual(
            mobileOnboardingRank(.setup(.consent), itinerary: itinerary), 0)
        XCTAssertEqual(
            mobileOnboardingRank(.setup(.complete), itinerary: itinerary),
            itinerary.count - 1)
    }

    /// Back/forward never leave the itinerary (and `complete` is last).
    func testNeighbors() {
        let itinerary = mobileOnboardingItinerary()
        XCTAssertNil(previousMobileSetupStep(.consent, itinerary: itinerary))
        XCTAssertEqual(
            previousMobileSetupStep(.complete, itinerary: itinerary),
            .knowledge)
        XCTAssertNil(nextMobileSetupStep(.complete, itinerary: itinerary))
        XCTAssertEqual(
            nextMobileSetupStep(.consent, itinerary: itinerary), .name)
    }

    // MARK: Commit rules

    /// Source: "Other" resolves to the typed detail; whitespace-only
    /// choices fail the commit and keep the card up.
    func testChosenSource() {
        XCTAssertNil(mobileChosenSource(selected: nil, otherDetail: ""))
        XCTAssertNil(mobileChosenSource(selected: "Other", otherDetail: "  "))
        XCTAssertNil(mobileChosenSource(selected: "   ", otherDetail: ""))
        XCTAssertEqual(
            mobileChosenSource(selected: "Friend", otherDetail: ""), "Friend")
        XCTAssertEqual(
            mobileChosenSource(selected: "Other", otherDetail: " Podcast "),
            "Podcast")
    }

    func testNameTrimming() {
        XCTAssertEqual(mobileOnboardingName("  Ada L. "), "Ada L.")
        XCTAssertEqual(mobileOnboardingName("   "), "")
    }

    // MARK: Store persistence (real SettingsStore over in-memory storage)

    /// Each step's answer lands in the real settings store under its
    /// additive mobile key, and the consent write carries a timestamp.
    func testRecordMobileOnboardingPersistsThroughSettingsStore() async {
        let (store, storage) = makeStore()
        await store.recordMobileOnboarding(.name, value: "Ada L.")
        await store.recordMobileOnboarding(.language, value: "pt-BR")
        await store.recordMobileOnboarding(.source, value: "Podcast")
        await store.recordMobileOnboarding(.knowledge, value: "off")
        await store.recordMobileOnboarding(.consent, value: "2026-09-29T00:00:00Z")
        XCTAssertEqual(
            storage.value(forKey: MobileOnboardingPreferenceKey.name.rawValue),
            .string("Ada L."))
        XCTAssertEqual(
            storage.value(forKey: MobileOnboardingPreferenceKey.language.rawValue),
            .string("pt-BR"))
        XCTAssertEqual(
            storage.value(forKey: MobileOnboardingPreferenceKey.source.rawValue),
            .string("Podcast"))
        XCTAssertEqual(
            storage.value(forKey: MobileOnboardingPreferenceKey.knowledge.rawValue),
            .string("off"))
        let consent = storage.value(
            forKey: MobileOnboardingPreferenceKey.consent.rawValue)
        XCTAssertEqual(consent, .string("2026-09-29T00:00:00Z"))
        XCTAssertEqual(
            MobileOnboardingPreferenceKey.allCases.count, 6)
    }
}
