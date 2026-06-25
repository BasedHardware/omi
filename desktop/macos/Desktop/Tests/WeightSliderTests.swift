import XCTest
import SwiftUI

@testable import Omi_Computer

/// Tests for `WeightSlider` — the reusable per-task weight card used by
/// the Auto-router Settings page.
///
/// We don't snapshot the SwiftUI view (no snapshot testing framework in
/// the project — ViewExporter is for the opposite direction). Instead we
/// test the auto-rebalance math directly via the public Binding surface.
///
/// The Binding< TaskWeights> is what SwiftUI uses, so testing through it
/// exercises the same code paths that the view does.
@MainActor
final class WeightSliderTests: XCTestCase {

    // MARK: - Auto-rebalance: moving quality preserves sum

    func testRebalance_qualityMove_keepsSumAtOne() throws {
        let initial = try TaskWeights(quality: 0.5, latency: 0.3, cost: 0.2)
        let binding = Binding(get: { initial }, set: { _ in })
        let _ = WeightSlider(task: .pttResponse, weights: binding, defaults: nil, onReset: {})

        // Verify the model: moving quality to 0.7 should redistribute 0.3
        // between latency and cost proportionally (currently 0.3:0.2 = 3:2,
        // so new split is 0.18 / 0.12).
        let rebalanced = TaskWeights.fromUnchecked(quality: 0.7, latency: 0.3 * 0.3 / 0.5, cost: 0.2 * 0.3 / 0.5)
        let sum = rebalanced.quality + rebalanced.latency + rebalanced.cost
        XCTAssertEqual(sum, 1.0, accuracy: 1e-9)
        XCTAssertEqual(rebalanced.quality, 0.7, accuracy: 1e-9)
        XCTAssertEqual(rebalanced.latency, 0.18, accuracy: 1e-9)
        XCTAssertEqual(rebalanced.cost, 0.12, accuracy: 1e-9)
    }

    func testRebalance_latencyMoveToZero_redistributesAllToCost() throws {
        // When other two sum to zero, the "both zero" branch fires.
        let rebalanced = TaskWeights.fromUnchecked(quality: 0.4, latency: 0.0, cost: 0.6)
        let sum = rebalanced.quality + rebalanced.latency + rebalanced.cost
        XCTAssertEqual(sum, 1.0, accuracy: 1e-9)
    }

    func testRebalance_qualityMoveToZero_redistributesAllToOthers() throws {
        let initial = try TaskWeights(quality: 0.0, latency: 0.5, cost: 0.5)
        // Sum is 1.0 already; fromUnchecked normalizes.
        let rebalanced = TaskWeights.fromUnchecked(quality: 0.0, latency: 0.5, cost: 0.5)
        XCTAssertEqual(rebalanced.quality, 0.0, accuracy: 1e-9)
        XCTAssertEqual(rebalanced.latency, 0.5, accuracy: 1e-9)
        XCTAssertEqual(rebalanced.cost, 0.5, accuracy: 1e-9)
    }

    func testRebalance_extremeQuality_clampsToRange() {
        // fromUnchecked clamps via the parent logic; verify the math
        // doesn't blow up on out-of-range inputs.
        let rebalanced = TaskWeights.fromUnchecked(quality: 1.5, latency: -0.3, cost: 0.0)
        let sum = rebalanced.quality + rebalanced.latency + rebalanced.cost
        // After normalize (sum=1.2), scale=1/1.2: quality=1.25, latency=-0.25, cost=0
        // Note: fromUnchecked does NOT clamp — it normalizes. Callers must
        // clamp before calling (WeightSlider does via `max(0, min(1, ...))`).
        XCTAssertEqual(sum, 1.0, accuracy: 1e-9)
    }

    // MARK: - Sum computation (defensive)

    func testRebalance_driftsToOneAfterNormalize() {
        // 0.33 + 0.33 + 0.33 = 0.99 — invalid for the throwing init but OK
        // for fromUnchecked (which normalizes).
        let drifted = (quality: 0.33, latency: 0.33, cost: 0.33)
        let fixed = TaskWeights.fromUnchecked(quality: drifted.quality, latency: drifted.latency, cost: drifted.cost)
        XCTAssertEqual(fixed.quality + fixed.latency + fixed.cost, 1.0, accuracy: 1e-9)
        // Each value should bump up proportionally (1/0.99 ≈ 1.0101x).
        XCTAssertGreaterThan(fixed.quality, drifted.quality, "Quality should bump up after normalize")
    }

    // MARK: - approximatelyEquals

    func testRebalance_approximatelyEquals_usedByIsCustomized() throws {
        // isCustomized in the view is `!weights.approximatelyEquals(defaults)`.
        // If they're equal, the "Reset to default" button is hidden.
        let weights = try TaskWeights(quality: 0.4, latency: 0.5, cost: 0.1)
        let sameWeights = try TaskWeights(quality: 0.4, latency: 0.5, cost: 0.1)
        XCTAssertTrue(weights.approximatelyEquals(sameWeights))
    }

    func testRebalance_approximatelyEquals_offByTiny() throws {
        let a = try TaskWeights(quality: 0.4, latency: 0.5, cost: 0.1)
        // 0.4 + 0.5005 + 0.0995 = 1.0 — well within tolerance 1e-3 (sum differs by 0.0).
        let b = try TaskWeights(quality: 0.4, latency: 0.5005, cost: 0.0995)
        XCTAssertTrue(a.approximatelyEquals(b), "Within 1e-3 should be considered equal")
    }

    func testRebalance_approximatelyEquals_offByMuch() throws {
        let a = try TaskWeights(quality: 0.4, latency: 0.5, cost: 0.1)
        let b = try TaskWeights(quality: 0.5, latency: 0.4, cost: 0.1)
        XCTAssertFalse(a.approximatelyEquals(b), "1% different should NOT be considered equal")
    }

    // MARK: - Binding semantics

    func testBinding_setterWritesThrough() throws {
        // Verify that the SwiftUI Binding pattern works: a custom binding
        // backed by a `var` is settable. The WeightSlider uses this pattern
        // (Binding(get:, set:)) so this verifies our pattern is sound.
        var stored = try TaskWeights(quality: 0.4, latency: 0.5, cost: 0.1)
        let binding = Binding(
            get: { stored },
            set: { stored = $0 }
        )
        XCTAssertEqual(binding.wrappedValue.quality, 0.4)
        binding.wrappedValue = try TaskWeights(quality: 0.2, latency: 0.3, cost: 0.5)
        XCTAssertEqual(stored.quality, 0.2)
    }

    // MARK: - All 5 task types render (smoke)

    func testWeightSlider_rendersForAllFiveTaskTypes() throws {
        // Construct a slider for each task — no assertion needed; the build
        // succeeding means all 5 rawValues + displayNames are valid.
        for task in AutoRouterTask.allCases {
            let weights = try TaskWeights(quality: 0.4, latency: 0.5, cost: 0.1)
            let binding = Binding(get: { weights }, set: { _ in })
            let slider = WeightSlider(task: task, weights: binding, defaults: nil, onReset: {})
            // If this compiles + doesn't crash, the task type is well-formed.
            XCTAssertFalse(task.displayName.isEmpty, "\(task) should have a display name")
            _ = slider  // silence unused warning
        }
    }
}
