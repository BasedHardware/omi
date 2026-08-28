import XCTest

@testable import Omi_Computer

/// The gate is the cost contract and the safety contract at once: no model call, and no
/// card, until the window really is a form the user is filling in by hand.
final class FormAssistGateTests: XCTestCase {
  private func field(_ label: String, empty: Bool = true, secure: Bool = false) -> FormField {
    FormField(label: label, isEmpty: empty, isSecure: secure)
  }

  func testThreeEmptyFieldsAreAForm() {
    let decision = FormAssistGate.decide(
      fields: [field("First name"), field("Last name"), field("Email")],
      hasSubmitButton: false
    )
    XCTAssertEqual(decision, .eligible)
  }

  func testTwoEmptyFieldsNeedASubmitButton() {
    let fields = [field("First name"), field("Email")]
    XCTAssertEqual(FormAssistGate.decide(fields: fields, hasSubmitButton: false), .notAForm)
    XCTAssertEqual(FormAssistGate.decide(fields: fields, hasSubmitButton: true), .eligible)
  }

  func testSearchBarIsNotAForm() {
    XCTAssertEqual(
      FormAssistGate.decide(fields: [field("Search")], hasSubmitButton: true), .notAForm)
  }

  /// A password box means sign-in or sign-up, and Omi has nothing to paste there.
  func testCredentialFormIsRefusedEvenWhenItLooksLikeAForm() {
    let decision = FormAssistGate.decide(
      fields: [field("Email"), field("Password", secure: true), field("Confirm password", secure: true)],
      hasSubmitButton: true
    )
    XCTAssertEqual(decision, .credentialForm)
  }

  func testAlreadyFilledFormIsLeftAlone() {
    let decision = FormAssistGate.decide(
      fields: [field("First name", empty: false), field("Email", empty: false)],
      hasSubmitButton: true
    )
    XCTAssertEqual(decision, .nothingLeftToFill)
  }
}

/// Two forms are "the same form" only if they are in the same window with the same
/// fields — that identity is what keeps the card from reappearing on every glance back.
final class FormSnapshotFingerprintTests: XCTestCase {
  private func snapshot(app: String = "Chrome", title: String = "Apply", labels: [String]) -> FormSnapshot {
    FormSnapshot(
      appName: app,
      windowTitle: title,
      fields: labels.map { FormField(label: $0, isEmpty: true, isSecure: false) },
      hasSubmitButton: true,
      windowFrame: nil
    )
  }

  func testFieldOrderDoesNotChangeIdentity() {
    XCTAssertEqual(
      snapshot(labels: ["Email", "First name"]).fingerprint,
      snapshot(labels: ["First name", "Email"]).fingerprint
    )
  }

  func testADifferentFormIsADifferentIdentity() {
    XCTAssertNotEqual(
      snapshot(labels: ["Email", "First name"]).fingerprint,
      snapshot(title: "Apply — step 2", labels: ["Email", "First name"]).fingerprint
    )
  }
}

/// Values reach the user's clipboard and then a real submission, so a wrong one costs
/// far more than a missing one.
final class FormAssistFillPolicyTests: XCTestCase {
  private let labels = ["First name", "Email", "Portfolio URL"]

  private func accepted(_ fills: [FormAssistFill]) -> [FormAssistFill] {
    FormAssistFillPolicy.accepted(fills, forLabels: labels, minConfidence: 0.6, limit: 8)
  }

  func testKeepsConfidentValuesForRealFields() {
    let fills = accepted([FormAssistFill(label: "Email", value: "a@b.com", confidence: 0.9)])
    XCTAssertEqual(fills.map(\.value), ["a@b.com"])
  }

  func testDropsFieldsTheScanNeverReported() {
    XCTAssertTrue(
      accepted([FormAssistFill(label: "Salary expectation", value: "$200k", confidence: 0.99)]).isEmpty)
  }

  func testDropsLowConfidenceAndEmptyValues() {
    let fills = accepted([
      FormAssistFill(label: "First name", value: "Yash", confidence: 0.4),
      FormAssistFill(label: "Email", value: "   ", confidence: 0.95),
    ])
    XCTAssertTrue(fills.isEmpty)
  }

  func testKeepsOnlyTheFirstAnswerPerField() {
    let fills = accepted([
      FormAssistFill(label: "Email", value: "work@b.com", confidence: 0.9),
      FormAssistFill(label: "email", value: "old@b.com", confidence: 0.95),
    ])
    XCTAssertEqual(fills.map(\.value), ["work@b.com"])
  }

  func testHonoursTheRowLimit() {
    let fills = FormAssistFillPolicy.accepted(
      labels.map { FormAssistFill(label: $0, value: "x", confidence: 0.9) },
      forLabels: labels,
      minConfidence: 0.6,
      limit: 2
    )
    XCTAssertEqual(fills.count, 2)
  }
}

final class FormAssistRecallTests: XCTestCase {
  func testDerivesSearchTermsFromFieldLabels() {
    let terms = FormAssistRecall.searchTerms(for: ["Current employer", "GitHub profile", "Email"])
    XCTAssertEqual(terms, ["current", "employer", "github", "profile", "email"])
  }

  func testDropsNoiseWordsAndShortWords() {
    XCTAssertEqual(FormAssistRecall.searchTerms(for: ["Your name", "Street address"]), ["street"])
  }

  func testBoundsTheNumberOfSearches() {
    let labels = ["alpha bravo", "charlie delta", "echo foxtrot", "golf hotel"]
    XCTAssertEqual(FormAssistRecall.searchTerms(for: labels, limit: 3).count, 3)
  }
}

/// Web forms rarely expose a label on the field itself; the caption sitting above or to
/// the left of it is the only thing that names the field for the user, and therefore the
/// only thing worth handing the model.
final class FormFieldScannerTests: XCTestCase {
  private func caption(_ text: String, _ frame: CGRect) -> FormElement {
    FormElement(role: "AXStaticText", value: text, frame: frame)
  }

  func testPrefersTheElementsOwnMetadata() {
    let field = FormElement(role: "AXTextField", title: "Email", frame: CGRect(x: 0, y: 100, width: 200, height: 24))
    XCTAssertEqual(
      FormFieldScanner.label(for: field, captions: [caption("Phone", CGRect(x: 0, y: 70, width: 80, height: 16))]),
      "Email")
  }

  func testFallsBackToPlaceholderThenCaptionAbove() {
    let frame = CGRect(x: 0, y: 100, width: 200, height: 24)
    let placeholderOnly = FormElement(role: "AXTextField", placeholder: "you@example.com", frame: frame)
    XCTAssertEqual(FormFieldScanner.label(for: placeholderOnly, captions: []), "you@example.com")

    let bare = FormElement(role: "AXTextField", frame: frame)
    let captions = [
      caption("Email address", CGRect(x: 0, y: 78, width: 90, height: 16)),
      caption("Unrelated heading", CGRect(x: 0, y: 10, width: 90, height: 16)),
    ]
    XCTAssertEqual(FormFieldScanner.label(for: bare, captions: captions), "Email address")
  }

  func testIgnoresCaptionsBelowOrTooFarAway() {
    let bare = FormElement(role: "AXTextField", frame: CGRect(x: 0, y: 100, width: 200, height: 24))
    let captions = [
      caption("Helper text under the box", CGRect(x: 0, y: 130, width: 90, height: 16)),
      caption("Section from way above", CGRect(x: 0, y: 20, width: 90, height: 16)),
    ]
    XCTAssertEqual(FormFieldScanner.label(for: bare, captions: captions), "")
  }

  func testFieldsCarryEmptinessAndSecrecy() {
    let elements = [
      FormElement(role: "AXTextField", title: "First name", frame: CGRect(x: 0, y: 0, width: 200, height: 24)),
      FormElement(
        role: "AXTextField", title: "Email", value: "a@b.com", frame: CGRect(x: 0, y: 40, width: 200, height: 24)),
      FormElement(role: "AXSecureTextField", title: "Password", frame: CGRect(x: 0, y: 80, width: 200, height: 24)),
      FormElement(role: "AXStaticText", value: "Apply now", frame: CGRect(x: 0, y: 120, width: 200, height: 16)),
    ]
    let fields = FormFieldScanner.fields(in: elements)
    XCTAssertEqual(fields.map(\.label), ["First name", "Email", "Password"])
    XCTAssertEqual(fields.map(\.isEmpty), [true, false, true])
    XCTAssertEqual(fields.map(\.isSecure), [false, false, true])
  }

  func testSubmitButtonDetection() {
    XCTAssertTrue(
      FormFieldScanner.hasSubmitButton(in: [FormElement(role: "AXButton", title: "Submit application")]))
    XCTAssertFalse(
      FormFieldScanner.hasSubmitButton(in: [FormElement(role: "AXButton", title: "Cancel")]))
  }
}
