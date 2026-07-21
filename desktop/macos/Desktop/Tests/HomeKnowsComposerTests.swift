import XCTest

@testable import Omi_Computer

final class HomeKnowsComposerTests: XCTestCase {
  private let tasks = [
    HomeKnowsTaskCandidate(id: "t1", text: "Submit the Design PR by 7pm"),
    HomeKnowsTaskCandidate(id: "t2", text: "Reply to Sarah"),
  ]
  private let insights = [
    HomeKnowsInsightCandidate(id: "i1", text: "Deepgram spend is pacing 18% over last week"),
    HomeKnowsInsightCandidate(id: "i2", text: "Two meetings overlap on Thursday"),
  ]
  private let questions = ["What should I do today?", "What did I spend my time on this week?"]

  func testComposePicksTaskInsightQuestionWhenAllAvailable() {
    let rows = HomeKnowsListComposer.compose(tasks: tasks, insights: insights, questions: questions)

    XCTAssertEqual(rows.count, 3)
    XCTAssertEqual(rows[0].kind, .task(id: "t1"))
    XCTAssertEqual(rows[0].text, "Submit the Design PR by 7pm")
    XCTAssertEqual(rows[1].kind, .insight(id: "i1"))
    XCTAssertEqual(rows[2].kind, .question)
    XCTAssertEqual(rows[2].text, "What should I do today?")
  }

  func testDismissedTaskFallsThroughToNextTask() {
    let rows = HomeKnowsListComposer.compose(
      tasks: tasks, insights: insights, questions: questions, dismissedTaskIDs: ["t1"])

    XCTAssertEqual(rows[0].kind, .task(id: "t2"))
  }

  func testAllTasksDismissedFillsWithInsightsAndQuestion() {
    let rows = HomeKnowsListComposer.compose(
      tasks: tasks, insights: insights, questions: questions, dismissedTaskIDs: ["t1", "t2"])

    XCTAssertEqual(rows.count, 3)
    XCTAssertEqual(rows[0].kind, .insight(id: "i1"))
    XCTAssertEqual(rows[1].kind, .insight(id: "i2"))
    XCTAssertEqual(rows[2].kind, .question)
  }

  func testQuestionsFillAllSlotsWhenNoTasksOrInsights() {
    let rows = HomeKnowsListComposer.compose(
      tasks: [], insights: [], questions: questions + ["Third question?"])

    XCTAssertEqual(rows.count, 3)
    XCTAssertTrue(rows.allSatisfy { $0.kind == .question })
  }

  func testInsightsMayFillLastSlotOnlyWhenNoQuestionExists() {
    let rows = HomeKnowsListComposer.compose(tasks: tasks, insights: insights, questions: [])

    XCTAssertEqual(rows.count, 3)
    XCTAssertEqual(rows[1].kind, .insight(id: "i1"))
    XCTAssertEqual(rows[2].kind, .insight(id: "i2"))
  }

  func testEmptyAndWhitespaceEntriesAreSkipped() {
    let rows = HomeKnowsListComposer.compose(
      tasks: [HomeKnowsTaskCandidate(id: "t0", text: "   ")],
      insights: [HomeKnowsInsightCandidate(id: "i0", text: "")],
      questions: ["  ", "Real question?"])

    XCTAssertEqual(rows.count, 1)
    XCTAssertEqual(rows[0].kind, .question)
    XCTAssertEqual(rows[0].text, "Real question?")
  }

  func testEverythingEmptyProducesNoRows() {
    XCTAssertTrue(HomeKnowsListComposer.compose(tasks: [], insights: [], questions: []).isEmpty)
  }
}
