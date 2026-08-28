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

  /// A sign-up box is a password field plus an email box and nothing else worth filling.
  func testCredentialFormIsRefused() {
    let decision = FormAssistGate.decide(
      fields: [field("Email"), field("Password", secure: true), field("Confirm password", secure: true)],
      hasSubmitButton: true
    )
    XCTAssertEqual(decision, .credentialForm)
  }

  /// But a job application that ends in "create a password" is still an application. The
  /// password field is never offered; it just stops disqualifying everything around it.
  func testApplicationWithAPasswordFieldStaysEligible() {
    let decision = FormAssistGate.decide(
      fields: [
        field("Full name"), field("University"), field("Current employer"),
        field("Password", secure: true),
      ],
      hasSubmitButton: true
    )
    XCTAssertEqual(decision, .eligible)
  }

  func testSecureFieldsNeverCountTowardEligibility() {
    let decision = FormAssistGate.decide(
      fields: [field("Email"), field("Password", secure: true), field("PIN", secure: true)],
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
      windowFrame: nil,
      windowID: nil
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
      snapshot(labels: ["Email", "First name", "Cover letter"]).fingerprint
    )
  }

  /// A page reports its title after it reports its fields. Folding the title in made the
  /// same form look like two, and the card was torn down and rebuilt a second after the
  /// user first saw it.
  func testTitleArrivingLateDoesNotChangeIdentity() {
    XCTAssertEqual(
      snapshot(title: "", labels: ["Email", "First name"]).fingerprint,
      snapshot(title: "Apply — Acme", labels: ["Email", "First name"]).fingerprint
    )
  }
}

/// Values reach the user's clipboard and then a real submission, so a wrong one costs
/// far more than a missing one.
final class FormAssistFillPolicyTests: XCTestCase {
  private let labels = ["First name", "Email", "Portfolio URL"]

  private func rows(_ fills: [FormAssistFill]) -> [FormAssistRow] {
    FormAssistFillPolicy.rows(fills, forFields: labels, minConfidence: 0.6)
  }

  func testKeepsConfidentValuesForRealFields() {
    let rows = rows([FormAssistFill(label: "Email", value: "a@b.com", confidence: 0.9)])
    XCTAssertEqual(rows.compactMap(\.fill).map(\.value), ["a@b.com"])
  }

  /// The card is the whole form, so the user can see what Omi could not answer rather
  /// than guessing whether it even looked.
  func testEveryEmptyFieldGetsARowInFormOrder() {
    let rows = rows([FormAssistFill(label: "Email", value: "a@b.com", confidence: 0.9)])
    XCTAssertEqual(rows.map(\.label), labels)
    XCTAssertEqual(rows.map(\.hint), ["no memory", nil, "no memory"])
    XCTAssertEqual(rows[1].fill?.value, "a@b.com")
  }

  func testDropsFieldsTheScanNeverReported() {
    let rows = rows([FormAssistFill(label: "Salary expectation", value: "$200k", confidence: 0.99)])
    XCTAssertEqual(rows.map(\.label), labels)
    XCTAssertTrue(rows.compactMap(\.fill).isEmpty)
  }

  /// The two ways a field goes unanswered read differently on the card, because they
  /// tell the user different things to do about it.
  func testLowConfidenceReadsAsNotSureAndSilenceAsNoMemory() {
    let rows = rows([
      FormAssistFill(label: "First name", value: "Yash", confidence: 0.4),
      FormAssistFill(label: "Email", value: "   ", confidence: 0.95),
    ])
    XCTAssertEqual(rows.map(\.outcome), [.notSure, .noMemory, .noMemory])
    XCTAssertEqual(rows.map(\.hint), ["not sure", "no memory", "no memory"])
  }

  func testKeepsOnlyTheFirstAnswerPerField() {
    let rows = rows([
      FormAssistFill(label: "Email", value: "work@b.com", confidence: 0.9),
      FormAssistFill(label: "email", value: "old@b.com", confidence: 0.95),
    ])
    XCTAssertEqual(rows.compactMap(\.fill).map(\.value), ["work@b.com"])
  }

  /// Duplicate ids crash the card's `ForEach`, and two fields captioned the same get
  /// the same answer anyway.
  func testTwoFieldsWithTheSameLabelBecomeOneRow() {
    let rows = FormAssistFillPolicy.rows(
      [FormAssistFill(label: "Email", value: "a@b.com", confidence: 0.9)],
      forFields: ["Email", "email", " Email "],
      minConfidence: 0.6
    )
    XCTAssertEqual(rows.map(\.label), ["Email"])
  }

  /// Nothing bounds the row count any more: the card scrolls, so a long form is shown
  /// in full rather than truncated to whatever used to fit.
  func testEveryFieldOfALongFormIsShown() {
    let many = (1...40).map { "Field \($0)" }
    let rows = FormAssistFillPolicy.rows(
      many.map { FormAssistFill(label: $0, value: "x", confidence: 0.9) },
      forFields: many,
      minConfidence: 0.6
    )
    XCTAssertEqual(rows.count, 40)
    XCTAssertEqual(rows.compactMap(\.fill).count, 40)
  }
}

/// How much of the user's memory reaches the model, and in what order.
final class FormAssistRecallSelectionTests: XCTestCase {
  func testKeywordMatchesComeFirstAndDuplicatesCollapse() {
    let selected = FormAssistRecall.selected(
      matched: ["Works at Datasaur", "Works at Datasaur"],
      recent: ["Likes coffee", "Works at Datasaur"]
    )
    XCTAssertEqual(selected, ["Works at Datasaur", "Likes coffee"])
  }

  func testStopsAtTheCharacterBudget() {
    let long = String(repeating: "x", count: 60)
    let selected = FormAssistRecall.selected(
      matched: [], recent: [long, long + "y", "short"], budget: 123)
    XCTAssertEqual(selected, [long, long + "y"])
  }

  /// A memory too large for the remaining budget must not stop the smaller ones behind
  /// it from being included — truncating the list on the first oversized entry silently
  /// drops the facts most likely to answer a short field.
  func testAnOversizedMemoryDoesNotBlockLaterOnes() {
    let selected = FormAssistRecall.selected(
      matched: [], recent: [String(repeating: "x", count: 200), "Lives in San Jose"], budget: 100)
    XCTAssertEqual(selected, ["Lives in San Jose"])
  }

  func testDropsBlankMemories() {
    XCTAssertEqual(FormAssistRecall.selected(matched: ["   "], recent: ["Real"]), ["Real"])
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

/// The card follows a window, and windows keep their identity while their titles move.
final class FormWindowKeyTests: XCTestCase {
  private func key(_ title: String, id: CGWindowID? = 42, app: String = "Safari") -> FormWindowKey {
    FormWindowKey(appName: app, windowTitle: title, windowID: id)
  }

  func testTitleChangesDoNotChangeTheWindow() {
    XCTAssertEqual(key(""), key("Apply — Acme"))
  }

  func testADifferentWindowIsADifferentWindow() {
    XCTAssertNotEqual(key("Apply", id: 42), key("Apply", id: 43))
  }

  func testSameWindowIDInAnotherAppIsNotTheSameWindow() {
    XCTAssertNotEqual(key("Apply"), key("Apply", app: "Chrome"))
  }

  /// Windowless targets still need an identity, so the title is the fallback.
  func testFallsBackToTitleWithoutAWindowID() {
    XCTAssertEqual(key("Apply", id: nil), key("Apply", id: nil))
    XCTAssertNotEqual(key("Apply", id: nil), key("Settings", id: nil))
  }
}

final class FormFieldScannerChromeTests: XCTestCase {
  /// Safari's address bar reports two text fields of its own. Counting them inflates the
  /// tally the gate reads, and they are never something to fill from memory.
  func testBrowserSearchFieldsAreNotFormFields() {
    let elements = [
      FormElement(role: "AXTextField", title: "smart search field"),
      FormElement(role: "AXTextField", title: "Search"),
      FormElement(role: "AXTextField", title: "Full name"),
    ]
    XCTAssertEqual(FormFieldScanner.fields(in: elements).map(\.label), ["Full name"])
  }
}

/// A real login page is not one password box in isolation: Hacker News shows a login
/// form and a create-account form side by side, which is two username fields, two
/// password fields, and a submit button — enough non-secure fields to pass a plain count.
final class FormAssistCredentialRatioTests: XCTestCase {
  private func field(_ label: String, secure: Bool = false) -> FormField {
    FormField(label: label, isEmpty: true, isSecure: secure)
  }

  func testLoginAndSignupSideBySideIsACredentialForm() {
    let decision = FormAssistGate.decide(
      fields: [
        field("username"), field("password", secure: true),
        field("username"), field("password", secure: true),
      ],
      hasSubmitButton: true
    )
    XCTAssertEqual(decision, .credentialForm)
  }

  func testOnePasswordAmongManyRealFieldsIsStillAnApplication() {
    let decision = FormAssistGate.decide(
      fields: [
        field("Full name"), field("University"), field("Current employer"),
        field("Portfolio URL"), field("Password", secure: true),
      ],
      hasSubmitButton: true
    )
    XCTAssertEqual(decision, .eligible)
  }
}

/// The card is about the fields underneath it, so it goes where no form puts them —
/// the top-right corner of the window it answers, and of the display when there is no
/// window to anchor to.
final class FormAssistCardPlacementTests: XCTestCase {
  private let screen = CGRect(x: 0, y: 0, width: 1512, height: 950)
  private let card = CGSize(width: 460, height: 216)

  /// The remembered position is the user's, so it is honoured; anything that no longer
  /// lands on the display is not a position and the default corner takes over.
  func testARememberedOffsetMovesTheCard() {
    let frame = FormAssistCardPlacement.frame(
      cardSize: card, visibleFrame: screen, offset: CGSize(width: -300, height: -200))
    let corner = FormAssistCardPlacement.frame(cardSize: card, visibleFrame: screen)
    XCTAssertEqual(frame.maxX, corner.maxX - 300)
    XCTAssertEqual(frame.maxY, corner.maxY - 200)
    XCTAssertTrue(screen.contains(frame))
  }

  func testASmallOffsetIsClampedInsteadOfLeavingTheScreen() {
    let frame = FormAssistCardPlacement.frame(
      cardSize: card, visibleFrame: screen, offset: CGSize(width: 60, height: 60))
    XCTAssertTrue(screen.contains(frame))
  }

  func testAnOffsetForABiggerDisplayFallsBackToTheCorner() {
    let frame = FormAssistCardPlacement.frame(
      cardSize: card, visibleFrame: screen, offset: CGSize(width: -2_400, height: -1_400))
    XCTAssertEqual(frame, FormAssistCardPlacement.frame(cardSize: card, visibleFrame: screen))
  }

  func testNoOffsetIsTheTopRightCorner() {
    XCTAssertEqual(
      FormAssistCardPlacement.frame(cardSize: card, visibleFrame: screen, offset: nil),
      FormAssistCardPlacement.frame(cardSize: card, visibleFrame: screen))
  }

  func testSitsInTheTopRightCorner() {
    let frame = FormAssistCardPlacement.frame(cardSize: card, visibleFrame: screen)
    XCTAssertEqual(frame.maxX, screen.maxX - FormAssistCardPlacement.margin)
    XCTAssertEqual(frame.maxY, screen.maxY - FormAssistCardPlacement.margin)
  }

  func testHonoursAScreenOffsetFromTheOrigin() {
    let secondary = CGRect(x: -1728, y: 300, width: 1728, height: 1080)
    let frame = FormAssistCardPlacement.frame(cardSize: card, visibleFrame: secondary)
    XCTAssertTrue(secondary.contains(frame))
  }

  /// A tiny screen must still get a card that fits on it.
  func testShrinksToFitASmallScreen() {
    let small = CGRect(x: 0, y: 0, width: 400, height: 200)
    let frame = FormAssistCardPlacement.frame(cardSize: card, visibleFrame: small)
    XCTAssertTrue(small.contains(frame))
  }

  /// The card sits over the form the user is reading, so a long one scrolls at half the
  /// display rather than growing down it.
  @MainActor
  func testALongFormStopsAtHalfTheScreenAndScrolls() {
    let subtitle = "3 of 40 fields from your memories."
    let short = CGRect(x: 0, y: 0, width: 1512, height: 900)
    let size = CloudConnectorGuidanceOverlay.fieldCopyCardSize(
      title: "Omi can fill this", subtitle: subtitle, fieldCount: 40,
      maxHeight: FormAssistCardPlacement.maxCardHeight(visibleFrame: short))

    XCTAssertEqual(size.height, 450)
    XCTAssertTrue(short.contains(FormAssistCardPlacement.frame(cardSize: size, visibleFrame: short)))

    // A form that already fits inside half the screen is not padded out to it.
    XCTAssertEqual(
      CloudConnectorGuidanceOverlay.fieldCopyCardSize(
        title: "Omi can fill this", subtitle: subtitle, fieldCount: 5,
        maxHeight: FormAssistCardPlacement.maxCardHeight(visibleFrame: short)
      ).height,
      96 + 5 * 30)
  }
}

/// Which model call a field is routed to. Getting this wrong is what made a real
/// application come back with two names and no drafts.
final class FormAssistFieldRoutingTests: XCTestCase {
  private func field(_ label: String, multiline: Bool = false) -> FormField {
    FormField(label: label, isEmpty: true, isSecure: false, isMultiline: multiline)
  }

  func testABigBoxWantsProseEvenWithAFlatLabel() {
    XCTAssertTrue(field("Additional Information", multiline: true).wantsProse)
    XCTAssertFalse(field("Additional Information").wantsProse)
  }

  /// The signal that survives below the fold, where the screenshot cannot see the field.
  func testAQuestionWantsProseEvenInAOneLineBox() {
    XCTAssertTrue(field("Why Anthropic?").wantsProse)
    XCTAssertFalse(field("First Name").wantsProse)
  }

  /// Nothing Omi stores can consent on the user's behalf, and a list padded with
  /// boilerplate nothing can answer is what pulled the whole response conservative.
  func testConsentFieldsAreRefusedLikeProtectedOnes() {
    XCTAssertEqual(
      FormAssistSensitiveFields.answerable([
        "First Name", "Please read the arbitration agreement below",
        "Agreement to Arbitrate", "AI Policy for Application", "Why Anthropic?",
      ]),
      ["First Name", "Why Anthropic?"])
  }
}

/// Drafted answers are held higher than copied facts, and some fields are never
/// answered from memory at all.
final class FormAssistDraftPolicyTests: XCTestCase {
  private let labels = ["Full name", "Why Anthropic?", "Gender", "Desired salary"]

  private func fills(_ fills: [FormAssistFill]) -> [FormAssistFill] {
    FormAssistFillPolicy.rows(
      fills, forFields: labels, minConfidence: 0.6, minDraftConfidence: 0.75
    ).compactMap(\.fill)
  }

  func testDraftsClearAHigherBarThanFacts() {
    let kept = fills([
      FormAssistFill(label: "Full name", value: "Yashwanth", confidence: 0.65, kind: .fact),
      FormAssistFill(label: "Why Anthropic?", value: "Because…", confidence: 0.65, kind: .draft),
    ])
    XCTAssertEqual(kept.map(\.label), ["Full name"])
  }

  func testAConfidentDraftIsKept() {
    let kept = fills([
      FormAssistFill(label: "Why Anthropic?", value: "I have shipped…", confidence: 0.8, kind: .draft)
    ])
    XCTAssertEqual(kept.map(\.kind), [.draft])
  }

  /// Protected characteristics and negotiated terms are filtered before the model sees
  /// them; this pins that a model answering them anyway still cannot reach the card —
  /// the row appears, saying Omi skipped it, and carries no value to copy.
  func testProtectedAndNegotiatedFieldsAreShownAsSkippedAndNeverAnswered() {
    let rows = FormAssistFillPolicy.rows(
      [
        FormAssistFill(label: "Gender", value: "Male", confidence: 0.99, kind: .fact),
        FormAssistFill(label: "Desired salary", value: "$200k", confidence: 0.99, kind: .fact),
      ],
      forFields: labels,
      minConfidence: 0.6
    )
    let sensitive = rows.filter { ["Gender", "Desired salary"].contains($0.label) }
    XCTAssertEqual(sensitive.map(\.outcome), [.skipped, .skipped])
    XCTAssertEqual(sensitive.map(\.hint), ["skipped", "skipped"])
    XCTAssertTrue(sensitive.compactMap(\.fill).isEmpty)
  }

  func testSensitiveLabelsAreStrippedBeforeTheModelSeesThem() {
    let answerable = FormAssistSensitiveFields.answerable([
      "Full name", "Race / Ethnicity", "Veteran status", "Are you 18 years of age or older?",
      "Current employer",
    ])
    XCTAssertEqual(answerable, ["Full name", "Current employer"])
  }

  func testARunawayDraftIsDropped() {
    let long = String(repeating: "a", count: FormAssistFillPolicy.maxDraftLength + 1)
    let kept = fills([
      FormAssistFill(label: "Why Anthropic?", value: long, confidence: 0.9, kind: .draft)
    ])
    XCTAssertTrue(kept.isEmpty)
  }
}
