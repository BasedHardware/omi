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
  func testCompatibleWireTitlesKeepOperatorPricesOffArchitectAndDisplayOperator() throws {
    let primary = [
      SubscriptionPlanOption(id: "operator", title: "Operator"),
      SubscriptionPlanOption(
        id: "architect", title: "Architect",
        prices: [SubscriptionPriceOption(id: "price_arch", title: "Monthly", description: nil, priceString: "$99")]),
    ]
    let fallback = try ["Monthly", "Annual"].map { interval in
      let id = try XCTUnwrap(SubscriptionPlanNames.planId(from: "Operator \(interval)"))
      return SubscriptionPlanOption(
        id: id, title: "Operator",
        prices: [
          SubscriptionPriceOption(id: "price_op_\(interval)", title: interval, description: nil, priceString: "$49")
        ])
    }
    // planCatalog groups the two prices into one fallback plan before merging.
    let grouped = SubscriptionPlanOption(id: "operator", title: "Operator", prices: fallback.flatMap { $0.prices })
    let merged = SubscriptionPlanCatalogMerger.merge(primary: primary, fallback: [grouped])
    let operatorPlan = try XCTUnwrap(merged.first { $0.id == "operator" })
    let architectPlan = try XCTUnwrap(merged.first { $0.id == "architect" })
    XCTAssertEqual(operatorPlan.title, "Operator")  // primary wire title stays compatible
    XCTAssertEqual(operatorPlan.displayTitle, "Operator")
    XCTAssertEqual(Set(operatorPlan.prices.map { $0.id }), ["price_op_Monthly", "price_op_Annual"])
    XCTAssertEqual(architectPlan.prices.map { $0.id }, ["price_arch"])
    XCTAssertEqual(
      SubscriptionPlanPresentation.selectionLabel(planTitle: operatorPlan.displayTitle, startingPrice: "$49"),
      "Select Operator · $49")
  }

}
