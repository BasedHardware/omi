import XCTest

@testable import Omi_Computer

final class SubscriptionPlanCatalogMergerTests: XCTestCase {

  func testMergeDeduplicatesDuplicatePriceIDsWithoutCrashing() throws {
    let fallback = [
      SubscriptionPlanOption(
        id: "architect",
        title: "Architect",
        features: ["Fallback Feature"],
        prices: [
          SubscriptionPriceOption(
            id: "price_monthly",
            title: "Monthly",
            description: "Fallback monthly",
            priceString: "$20"
          ),
          SubscriptionPriceOption(
            id: "price_annual",
            title: "Annual",
            description: "Fallback annual",
            priceString: "$200"
          ),
        ]
      )
    ]

    let primary = [
      SubscriptionPlanOption(
        id: "architect",
        title: "Architect",
        features: ["Primary Feature"],
        prices: [
          SubscriptionPriceOption(
            id: "price_monthly",
            title: "Monthly",
            description: "Primary monthly",
            priceString: "$19"
          )
        ]
      )
    ]

    let merged = SubscriptionPlanCatalogMerger.merge(primary: primary, fallback: fallback)

    XCTAssertEqual(merged.count, 1)
    XCTAssertEqual(merged[0].features, ["Primary Feature"])
    XCTAssertEqual(merged[0].prices.count, 2)

    let monthly = try XCTUnwrap(merged[0].prices.first(where: { $0.id == "price_monthly" }))
    XCTAssertEqual(monthly.priceString, "$19")

    let annual = try XCTUnwrap(merged[0].prices.first(where: { $0.id == "price_annual" }))
    XCTAssertEqual(annual.priceString, "$200")
  }
}
