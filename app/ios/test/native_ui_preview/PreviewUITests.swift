import XCTest

final class PreviewUITests: XCTestCase {
    func testMainTabsUseSystemGlassAndAcknowledgeEveryDestination() {
        let app = start(["navigation", "chrome"])
        for title in ["Tasks", "Memories", "Apps", "Settings", "Home"] {
            let tab = app.tabBars.buttons[title]
            XCTAssertTrue(tab.waitForExistence(timeout: 10))
            XCTAssertTrue(tab.isHittable)
            XCTAssertGreaterThanOrEqual(tab.frame.height, 44)
            tab.tap()
            let acknowledged = NSPredicate { _, _ in
                app.staticTexts["preview-last-action"].label == "main_destination:\(title.lowercased())" && tab.isSelected
            }
            expectation(for: acknowledged, evaluatedWith: nil)
            waitForExpectations(timeout: 5)
        }
        capture(app, "native-liquid-glass-main-tabs")
    }

    func testPasswordInputIsSecureAndClearsWhenTheOwnerWithdrawsIt() {
        let app = start(["surface", "secure-input"])
        let input = app.secureTextFields["draft"]
        XCTAssertTrue(input.waitForExistence(timeout: 10))
        input.tap()
        input.typeText("fixture-key")
        let typed = NSPredicate { _, _ in app.staticTexts["preview-last-action"].label == "draft:fixture-key" }
        expectation(for: typed, evaluatedWith: nil)
        waitForExpectations(timeout: 10)
        app.buttons["reset_key"].tap()
        let replacement = app.secureTextFields["replacement_key"]
        XCTAssertTrue(replacement.waitForExistence(timeout: 5))
        XCTAssertEqual(replacement.value as? String, "API key")
        XCTAssertFalse(input.exists)
        app.buttons["save"].tap()
        XCTAssertTrue(app.staticTexts["saved:"].waitForExistence(timeout: 5))
        capture(app, "native-secure-transcription-input")
    }

    func testPhotoSupportsDoubleTapPinchPanAndReset() {
        let app = start(["surface", "photo"])
        let photo = app.scrollViews["photo"]
        XCTAssertTrue(photo.waitForExistence(timeout: 10))
        XCTAssertEqual(photo.value as? String, "100%")
        photo.doubleTap()
        let zoomed = NSPredicate { _, _ in (photo.value as? String) == "200%" }
        expectation(for: zoomed, evaluatedWith: nil)
        waitForExpectations(timeout: 5)
        photo.swipeLeft()
        capture(app, "native-photo-zoom-pan")
        photo.doubleTap()
        let reset = NSPredicate { _, _ in (photo.value as? String) == "100%" }
        expectation(for: reset, evaluatedWith: nil)
        waitForExpectations(timeout: 5)
        photo.pinch(withScale: 1.5, velocity: 1)
        XCTAssertNotEqual(photo.value as? String, "100%")
        photo.doubleTap()
        expectation(for: reset, evaluatedWith: nil)
        waitForExpectations(timeout: 5)
        XCTAssertTrue(app.buttons["save"].isHittable)
    }

    func testReaderPlaybackScrubAndTranscriptContextMenu() {
        let app = start(["surface", "reader"])
        let slider = app.sliders["position"]
        XCTAssertTrue(slider.waitForExistence(timeout: 10))
        slider.adjust(toNormalizedSliderPosition: 0.5)
        XCTAssertTrue(app.staticTexts["preview-last-action"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["preview-last-action"].label.hasPrefix("position:"))
        app.buttons["play"].tap()
        XCTAssertTrue(app.staticTexts["play:"].waitForExistence(timeout: 5))
        XCTAssertEqual(app.buttons["play"].label, "Pause")
        let line = app.buttons["segment:0"]
        XCTAssertTrue(line.isHittable)
        line.press(forDuration: 0.8)
        app.buttons["Edit"].tap()
        XCTAssertTrue(app.staticTexts["segment:0:edit"].waitForExistence(timeout: 5))
        capture(app, "native-conversation-reader-player")
    }

    func testReaderLargeTextKeepsFooterAndBackReachable() {
        let app = start(["surface", "reader", "large"])
        XCTAssertTrue(app.buttons["play"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["play"].isHittable)
        XCTAssertTrue(app.buttons["ask"].isHittable)
        XCTAssertTrue(app.buttons["back"].isHittable)
        app.buttons["ask"].tap()
        XCTAssertTrue(app.staticTexts["ask:"].waitForExistence(timeout: 5))
        capture(app, "native-conversation-reader-large-text")
    }

    func testDialerHoldPlusAndClearDoNotAlsoTap() {
        let app = start(["surface", "keypad"])
        let zero = app.buttons["keypad_key_0"]
        XCTAssertTrue(zero.waitForExistence(timeout: 10))
        zero.press(forDuration: 0.8)
        XCTAssertTrue(app.staticTexts["keypad:+"].waitForExistence(timeout: 5))
        XCTAssertEqual(app.staticTexts["keypad"].label, "+")
        app.buttons["keypad_key_1"].tap()
        XCTAssertTrue(app.staticTexts["keypad:1"].waitForExistence(timeout: 5))
        XCTAssertEqual(app.staticTexts["keypad"].label, "+1")
        app.buttons["keypad"].press(forDuration: 0.8)
        XCTAssertTrue(app.staticTexts["keypad:clear"].waitForExistence(timeout: 5))
        XCTAssertEqual(app.staticTexts["keypad"].label, "Enter number")
        capture(app, "native-phone-keypad")
    }

    func testDtmfKeepsEveryRapidDigitInOrderBeforeAction() {
        let app = start(["surface", "keypad", "dtmf"])
        app.buttons["preview-burst-keys"].tap()
        XCTAssertTrue(app.staticTexts["keys:1,2,3,*,#,"].waitForExistence(timeout: 10))
        XCTAssertEqual(app.staticTexts["keypad"].label, "123*#")
        XCTAssertFalse(app.buttons["keypad"].exists)
        app.buttons["keypad_key_0"].press(forDuration: 0.8)
        XCTAssertTrue(app.staticTexts["keypad:0"].waitForExistence(timeout: 5))
        XCTAssertEqual(app.staticTexts["keypad"].label, "123*#0")
        capture(app, "native-dtmf-ordered-keys")
    }

    func testFailedKeypadStopsQueuedCommandsAndPreventsFollowingAction() {
        let app = start(["surface", "keypad", "dtmf", "failed-key"])
        app.buttons["preview-burst-keys"].tap()
        XCTAssertTrue(app.staticTexts["native-surface-error"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.staticTexts["keys:1,2,3,*,#,"].exists)
        XCTAssertEqual(app.staticTexts["keypad"].label, "Enter number")
    }

    func testCallTranscriptIsPlainTextRatherThanMarkdown() {
        let app = start(["surface", "plain-transcript"])
        XCTAssertTrue(app.staticTexts["Say **two stars** and [a link](https://example.com)"].waitForExistence(timeout: 10))
    }

    func testLargeTextKeypadKeepsLastRowAndNavigationReachable() {
        let app = start(["surface", "keypad", "large"])
        XCTAssertTrue(app.buttons["keypad_key_1"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["keypad_key_1"].isHittable)
        for _ in 0..<4 where !app.buttons["keypad_key_#"].isHittable { app.swipeUp() }
        XCTAssertTrue(app.buttons["keypad_key_#"].isHittable)
        app.buttons["keypad_key_#"].tap()
        XCTAssertTrue(app.staticTexts["keypad:#"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["save"].isHittable)
        capture(app, "native-keypad-large-text")
    }

    func testCountryChoiceFitsAbovePhoneAndPreservesSearch() {
        let app = start(["surface", "country"])
        let country = app.buttons["country"]
        let phone = app.textFields["phone"]
        XCTAssertTrue(country.waitForExistence(timeout: 10))
        XCTAssertTrue(country.isHittable)
        XCTAssertLessThanOrEqual(country.frame.maxY, phone.frame.minY)
        capture(app, "native-country-choice")
        country.tap()
        let search = app.searchFields.firstMatch
        XCTAssertTrue(search.waitForExistence(timeout: 5))
        search.tap()
        search.typeText("372")
        XCTAssertFalse(app.buttons["country_option_US"].exists)
        app.buttons["country_option_EE"].tap()
        XCTAssertTrue(app.staticTexts["country:EE"].waitForExistence(timeout: 5))
        XCTAssertFalse(search.exists)
    }

    func testOnboardingBackAppearsWhenNavigationChromeArrivesAfterMount() {
        let app = start(["surface", "late-toolbar"])
        let back = app.buttons["onboarding_back"]
        XCTAssertTrue(back.waitForExistence(timeout: 10))
        XCTAssertTrue(back.isHittable)
        capture(app, "native-onboarding-late-back")
        back.tap()
        XCTAssertTrue(app.staticTexts["onboarding_back:"].waitForExistence(timeout: 5))
    }

    func testNativeModalReturnsOnlyExplicitSaveAndLatestText() {
        let app = start(["modal"])
        app.buttons["modal-open"].tap()
        let field = app.textFields["draft"]
        XCTAssertTrue(field.waitForExistence(timeout: 10))
        field.tap()
        field.typeText("Avery final edit")
        app.buttons["save"].tap()
        XCTAssertTrue(app.staticTexts["saved:Avery final edit:false"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["reason:action"].exists)
        XCTAssertFalse(field.exists)
        capture(app, "native-modal-explicit-save")
    }

    func testNativeModalCancelGuardsDirtyInput() {
        let app = start(["modal"])
        app.buttons["modal-open"].tap()
        let field = app.textFields["draft"]
        XCTAssertTrue(field.waitForExistence(timeout: 10))
        field.tap()
        field.typeText("Unsaved person")
        app.buttons["cancel"].tap()
        XCTAssertTrue(app.alerts["Discard Changes?"].waitForExistence(timeout: 5))
        app.alerts.buttons["Keep Editing"].tap()
        XCTAssertEqual(field.value as? String, "Unsaved person")
        app.buttons["cancel"].tap()
        app.alerts.buttons["Discard"].tap()
        XCTAssertTrue(app.staticTexts["Cancelled without saving"].waitForExistence(timeout: 10))
        XCTAssertFalse(field.exists)
        capture(app, "native-modal-discard")
    }

    func testNativeModalSessionEndDismissesPrivateInput() {
        let app = start(["modal", "expire"])
        app.buttons["modal-open"].tap()
        XCTAssertTrue(app.textFields["draft"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["Cancelled without saving"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.textFields["draft"].exists)
        XCTAssertFalse(app.buttons["save"].exists)
    }

    func testNativeConfirmationUsesSystemAlertAndCancels() {
        let app = start(["modal", "alert"])
        app.buttons["modal-open"].tap()
        XCTAssertTrue(app.alerts["Edit Person"].waitForExistence(timeout: 5))
        app.alerts.buttons["Cancel"].tap()
        XCTAssertTrue(app.staticTexts["Cancelled without saving"].waitForExistence(timeout: 10))
    }

    func testNativeModalSaveIncludesLatestSwitchChoice() {
        let app = start(["modal"])
        app.buttons["modal-open"].tap()
        let toggle = app.switches["opt_out"]
        XCTAssertTrue(toggle.waitForExistence(timeout: 10))
        toggle.switches.firstMatch.tap()
        app.buttons["save"].tap()
        XCTAssertTrue(app.staticTexts["saved::true"].waitForExistence(timeout: 10))
    }
    func testLabelRowRendersSymbol() {
        let app = start(["surface", "rows"])
        let symbol = app.images.matching(identifier: "label_symbol").firstMatch
        XCTAssertTrue(symbol.waitForExistence(timeout: 10))
        let row = app.staticTexts["label_symbol"]
        XCTAssertEqual(row.label, "Bluetooth connected")
        // The symbol leads the title inside its own row; a label without a symbol draws none.
        XCTAssertTrue(row.frame.contains(CGPoint(x: symbol.frame.midX, y: symbol.frame.midY)))
        XCTAssertLessThan(symbol.frame.minX - row.frame.minX, 40)
        XCTAssertEqual(app.images.matching(identifier: "label_plain").count, 0)
        let warning = app.images.matching(identifier: "label_warning").firstMatch
        XCTAssertTrue(warning.exists)
        let screenshot = app.screenshot().image
        XCTAssertTrue(containsRed(screenshot, in: warning.frame), "A destructive label's symbol is red")
        XCTAssertFalse(containsRed(screenshot, in: symbol.frame))
        capture(app, "native-label-symbols")
    }

    func testTaskTitleWithoutOpenOptionSendsNothing() {
        let app = start(["surface", "rows"])
        let title = app.staticTexts["task_static"]
        XCTAssertTrue(title.waitForExistence(timeout: 10))
        // Only the checkbox is a button when the owner offers no 'open'; an 'open' task's title is one too.
        XCTAssertEqual(app.buttons.matching(identifier: "task_static").count, 1)
        XCTAssertEqual(app.buttons.matching(identifier: "task_open").count, 2)
        title.tap()
        Thread.sleep(forTimeInterval: 1.5)
        XCTAssertEqual(app.staticTexts["preview-last-action"].label, "Preview fixture")
        app.buttons["task_static"].tap()
        XCTAssertTrue(app.staticTexts["task_static:true"].waitForExistence(timeout: 5))
        title.press(forDuration: 0.8)
        app.buttons["Delete"].tap()
        XCTAssertTrue(app.staticTexts["task_static:delete"].waitForExistence(timeout: 5))
        app.buttons.matching(identifier: "task_open").element(boundBy: 1).tap()
        XCTAssertTrue(app.staticTexts["task_open:open"].waitForExistence(timeout: 5))
    }

    func testSelectionTogglesOptimisticallyAndSendsTheSortedSet() {
        let app = start(["surface", "selection", "slow-selection"])
        let row = app.staticTexts["conv_3"]
        XCTAssertTrue(row.waitForExistence(timeout: 10))
        let cell = listCell(app, "conv_3")
        XCTAssertFalse(cell.isSelected)
        XCTAssertTrue(listCell(app, "conv_1").isSelected)
        row.tap()
        // The circle fills at once, before the owner answers the slow (8 s) command.
        expectation(for: NSPredicate(format: "isSelected == true"), evaluatedWith: cell)
        waitForExpectations(timeout: 4)
        XCTAssertFalse(app.staticTexts["_selection:conv_1,conv_3"].exists)
        XCTAssertTrue(app.staticTexts["_selection:conv_1,conv_3"].waitForExistence(timeout: 20))
        XCTAssertTrue(app.staticTexts["2 selected"].waitForExistence(timeout: 5))
        XCTAssertTrue(cell.isSelected)
        capture(app, "native-list-selection")
    }

    func testBottomBarDeleteWaitsForThePendingSelection() {
        let app = start(["surface", "selection", "slow-selection"])
        XCTAssertTrue(app.staticTexts["conv_2"].waitForExistence(timeout: 10))
        app.staticTexts["conv_2"].tap()
        // Delete is tapped while the selection command is still pending; it acts on the new set.
        XCTAssertFalse(app.staticTexts["_selection:conv_1,conv_2"].exists)
        app.buttons["bulk_delete"].tap()
        XCTAssertTrue(app.staticTexts["bulk_delete:conv_1,conv_2"].waitForExistence(timeout: 20))
    }

    func testBottomBarDeleteStopsWhenThePendingSelectionFails() {
        let app = start(["surface", "selection", "slow-selection", "failed-selection"])
        XCTAssertTrue(app.staticTexts["conv_2"].waitForExistence(timeout: 10))
        app.staticTexts["conv_2"].tap()
        app.buttons["bulk_delete"].tap()
        // The refused selection reverts, so Delete must not act on a set the user never saw.
        XCTAssertTrue(app.staticTexts["native-surface-error"].waitForExistence(timeout: 20))
        XCTAssertFalse(app.staticTexts["bulk_delete:conv_1"].waitForExistence(timeout: 3))
        XCTAssertFalse(listCell(app, "conv_2").isSelected)
    }

    func testSelectionKeepsOtherRowsUsableAndSuppressesSwipes() {
        let app = start(["surface", "selection"])
        let more = app.buttons["more"]
        XCTAssertTrue(more.waitForExistence(timeout: 10))
        XCTAssertFalse(listCell(app, "more").isSelected)
        // iOS 16 has no selectionDisabled, so a non-selectable row is disabled while selecting there.
        if #available(iOS 17.0, *) {
            more.tap()
            XCTAssertTrue(app.staticTexts["more:"].waitForExistence(timeout: 5))
            XCTAssertFalse(listCell(app, "more").isSelected)
        }
        listCell(app, "conv_2").swipeLeft()
        listCell(app, "conv_locked").swipeLeft()
        // Only the bottom bar's Delete exists: no row offers its swipe action while selecting.
        let deletes = app.buttons.matching(NSPredicate(format: "label == %@", "Delete"))
        XCTAssertFalse(app.buttons["conv_locked_swipe_delete"].waitForExistence(timeout: 2), "No swipe action while selecting")
        XCTAssertEqual(deletes.count, 1)
        XCTAssertFalse(app.staticTexts["conv_locked:delete"].exists, "A full swipe sends nothing while selecting")
        XCTAssertFalse(app.staticTexts["_selection:conv_1,conv_2"].exists)
    }

    func testSelectionLargeTextKeepsTheBottomBarReachable() {
        let app = start(["surface", "selection", "large"])
        let delete = app.buttons["bulk_delete"]
        XCTAssertTrue(delete.waitForExistence(timeout: 10))
        XCTAssertTrue(delete.isHittable)
        XCTAssertTrue(app.buttons["bulk_move"].isHittable)
        XCTAssertTrue(app.staticTexts["1 selected"].exists)
        capture(app, "native-list-selection-large-text")
        delete.tap()
        XCTAssertTrue(app.staticTexts["bulk_delete:conv_1"].waitForExistence(timeout: 5))
    }

    func testQueuedSelectionSurvivesANewerSnapshot() {
        let app = start(["surface", "selection"])
        XCTAssertTrue(app.buttons["preview-burst-list"].waitForExistence(timeout: 10))
        app.buttons["preview-burst-list"].tap()
        XCTAssertTrue(app.staticTexts["list:conv_1,conv_2|conv_1,conv_2,conv_3|"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["3 selected"].waitForExistence(timeout: 5))
    }

    func testQueuedSelectionDropsRowsNoLongerSelectable() {
        let app = start(["surface", "selection", "stale-selection"])
        XCTAssertTrue(app.buttons["preview-burst-list"].waitForExistence(timeout: 10))
        app.buttons["preview-burst-list"].tap()
        // conv_3 stopped being selectable while the second selection was queued.
        XCTAssertTrue(app.staticTexts["list:conv_1,conv_2|conv_1,conv_2|"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.staticTexts["native-surface-error"].exists)
    }

    func testReorderSendsTheFullPermutation() {
        let app = start(["surface", "reorder"])
        XCTAssertTrue(app.staticTexts["task_c"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.buttons.matching(identifier: "task_a").firstMatch.exists, "Reordered rows are static")
        drag(app, "task_c", to: "task_a")
        XCTAssertTrue(app.staticTexts["_reorder:tasks:task_c,task_a,task_b"].waitForExistence(timeout: 10))
        XCTAssertLessThan(app.staticTexts["task_c"].frame.minY, app.staticTexts["task_a"].frame.minY)
        capture(app, "native-list-reorder")
    }

    func testFailedReorderRevertsToTheSnapshotOrder() {
        let app = start(["surface", "reorder", "failed-reorder"])
        XCTAssertTrue(app.staticTexts["task_c"].waitForExistence(timeout: 10))
        drag(app, "task_c", to: "task_a")
        XCTAssertTrue(app.staticTexts["native-surface-error"].waitForExistence(timeout: 10))
        let reverted = NSPredicate { _, _ in
            app.staticTexts["task_a"].frame.minY < app.staticTexts["task_c"].frame.minY
        }
        expectation(for: reverted, evaluatedWith: nil)
        waitForExpectations(timeout: 5)
        // The refused order is not a pending draft: leaving reorder mode still reaches the owner.
        app.buttons["reorder_done"].tap()
        XCTAssertTrue(app.staticTexts["reorder_done:"].waitForExistence(timeout: 5))
    }

    func testQueuedReorderSurvivesANewerSnapshot() {
        let app = start(["surface", "reorder"])
        XCTAssertTrue(app.buttons["preview-burst-list"].waitForExistence(timeout: 10))
        app.buttons["preview-burst-list"].tap()
        XCTAssertTrue(app.staticTexts["list:task_b,task_a,task_c|task_c,task_b,task_a|"].waitForExistence(timeout: 10))
        let ordered = NSPredicate { _, _ in
            app.staticTexts["task_c"].frame.minY < app.staticTexts["task_b"].frame.minY
                && app.staticTexts["task_b"].frame.minY < app.staticTexts["task_a"].frame.minY
        }
        expectation(for: ordered, evaluatedWith: nil)
        waitForExpectations(timeout: 5)
    }

    func testCollapsibleSectionHidesRowsAndExplainsTheToggle() {
        let app = start(["surface", "collapsible"])
        // XCUITest cannot read accessibility hints; the Expand/Collapse hint needs a VoiceOver check.
        let header = app.descendants(matching: .any)["overdue_header"]
        XCTAssertTrue(header.waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["late_1"].exists)
        header.tap()
        expectation(for: NSPredicate(format: "exists == false"), evaluatedWith: app.staticTexts["late_1"])
        waitForExpectations(timeout: 5)
        XCTAssertFalse(app.staticTexts["late_2"].exists)
        XCTAssertTrue(app.staticTexts["today_1"].exists)
        capture(app, "native-list-collapsed")
        header.tap()
        XCTAssertTrue(app.staticTexts["late_1"].waitForExistence(timeout: 5))
        XCTAssertEqual(app.staticTexts["preview-last-action"].label, "Preview fixture", "Collapsing sends nothing")
    }

    func testSwipeSendsTheOptionId() {
        let app = start(["surface", "swipe"])
        let task = listCell(app, "swipe_task")
        XCTAssertTrue(task.waitForExistence(timeout: 10))
        reveal(task, leading: false)
        let delete = app.buttons["Delete"]
        XCTAssertTrue(delete.waitForExistence(timeout: 5))
        capture(app, "native-list-swipe")
        delete.tap()
        XCTAssertTrue(app.staticTexts["swipe_task:delete"].waitForExistence(timeout: 5))
        reveal(task, leading: true)
        XCTAssertTrue(app.buttons["Complete"].waitForExistence(timeout: 5))
        app.buttons["Complete"].tap()
        XCTAssertTrue(app.staticTexts["swipe_task:complete"].waitForExistence(timeout: 5))
        reveal(listCell(app, "swipe_person"), leading: false)
        XCTAssertTrue(app.buttons["Pin"].waitForExistence(timeout: 5))
        app.buttons["Rename"].tap()
        XCTAssertTrue(app.staticTexts["swipe_person:rename"].waitForExistence(timeout: 5))
    }

    func testIndentDrawsARuleWithoutChangingRowHeight() {
        let app = start(["surface", "indent"])
        let root = app.staticTexts["indent_0"]
        XCTAssertTrue(root.waitForExistence(timeout: 10))
        let rootCell = listCell(app, "indent_0"), childCell = listCell(app, "indent_1")
        let grandchildCell = listCell(app, "indent_2")
        XCTAssertEqual(rootCell.frame.height, grandchildCell.frame.height, accuracy: 0.5)
        // A label row's accessibility frame spans its whole list cell, so measure where the text is drawn:
        // the high-contrast pixels across the middle of each cell, which the faint indent rule never reaches.
        let screenshot = app.screenshot().image
        func text(_ cell: XCUIElement) -> CGRect {
            inkBounds(screenshot, in: cell.frame.insetBy(dx: 0, dy: cell.frame.height / 3)) ?? .zero
        }
        let rootText = text(rootCell), childText = text(childCell), grandchildText = text(grandchildCell)
        XCTAssertGreaterThan(rootText.width, 0, "The row's text is drawn")
        XCTAssertEqual(childText.minX - rootText.minX, 20, accuracy: 1)
        XCTAssertEqual(grandchildText.minX - rootText.minX, 40, accuracy: 1)
        func gutter(_ cell: XCUIElement, _ text: CGRect) -> CGRect {
            CGRect(x: cell.frame.minX + 4, y: cell.frame.midY - 4, width: text.minX - cell.frame.minX - 8, height: 8)
        }
        XCTAssertFalse(varies(screenshot, in: gutter(rootCell, rootText)), "An unindented row draws no rule")
        XCTAssertTrue(varies(screenshot, in: gutter(childCell, childText)), "The indent rule is visible")
        XCTAssertTrue(varies(screenshot, in: gutter(grandchildCell, grandchildText)))
        capture(app, "native-list-indent")
    }

    /// The list cell that holds the element [id].
    func listCell(_ app: XCUIApplication, _ id: String) -> XCUIElement {
        app.cells.containing(NSPredicate(format: "identifier == %@", id)).firstMatch
    }

    /// Drags the system reorder control of [source]'s row onto [target]'s row.
    func drag(_ app: XCUIApplication, _ source: String, to target: String) {
        let from = listCell(app, source), to = listCell(app, target)
        let handle = from.buttons.matching(NSPredicate(format: "label CONTAINS[c] 'reorder'")).firstMatch
        let start = handle.exists ? handle.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5))
            : from.coordinate(withNormalizedOffset: CGVector(dx: 0.95, dy: 0.5))
        start.press(forDuration: 0.6, thenDragTo: to.coordinate(withNormalizedOffset: CGVector(dx: 0.95, dy: 0.2)))
    }

    /// Reveals a row's swipe actions with a slow partial drag; a fast full swipe would run the first action.
    func reveal(_ cell: XCUIElement, leading: Bool) {
        let start = cell.coordinate(withNormalizedOffset: CGVector(dx: leading ? 0.1 : 0.9, dy: 0.5))
        start.press(forDuration: 0.1, thenDragTo: cell.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)))
    }

    /// Whether the brightness inside [frame] (screen points) varies, so something is drawn there.
    func varies(_ image: UIImage, in frame: CGRect) -> Bool {
        guard let region = brightness(image, in: frame) else { return false }
        return (region.values.max() ?? 0) - (region.values.min() ?? 0) > 45
    }

    /// The bounds (screen points) of what is drawn with high contrast inside [frame]: pixels whose
    /// brightness (0...765) differs from the region's most common brightness by more than [contrast].
    /// Text clears the default; a quaternary rule or a separator does not.
    func inkBounds(_ image: UIImage, in frame: CGRect, contrast: Int = 300) -> CGRect? {
        guard let region = brightness(image, in: frame) else { return nil }
        var histogram = [Int](repeating: 0, count: 766)
        for value in region.values { histogram[value] += 1 }
        let background = histogram.indices.max { histogram[$0] < histogram[$1] } ?? 0
        var ink: (minX: Int, minY: Int, maxX: Int, maxY: Int)?
        for y in 0..<region.height {
            for x in 0..<region.width where abs(region.values[y * region.width + x] - background) > contrast {
                ink = (min(ink?.minX ?? x, x), min(ink?.minY ?? y, y), max(ink?.maxX ?? x, x), max(ink?.maxY ?? y, y))
            }
        }
        guard let ink else { return nil }
        let origin = region.pixels.origin, scale = region.scale
        return CGRect(x: (origin.x + CGFloat(ink.minX)) / scale, y: (origin.y + CGFloat(ink.minY)) / scale,
                      width: CGFloat(ink.maxX - ink.minX + 1) / scale, height: CGFloat(ink.maxY - ink.minY + 1) / scale)
    }

    /// Each pixel's brightness (r + g + b) inside [frame] (screen points), row by row from the top.
    func brightness(_ image: UIImage, in frame: CGRect)
        -> (values: [Int], width: Int, height: Int, pixels: CGRect, scale: CGFloat)? {
        guard let cgImage = image.cgImage, frame.width > 0, frame.height > 0 else { return nil }
        let scale = CGFloat(cgImage.width) / image.size.width
        let pixels = CGRect(x: frame.minX * scale, y: frame.minY * scale, width: frame.width * scale,
                            height: frame.height * scale).integral
        guard let crop = cgImage.cropping(to: pixels) else { return nil }
        let width = crop.width, height = crop.height
        var data = [UInt8](repeating: 0, count: width * height * 4)
        guard let context = CGContext(data: &data, width: width, height: height, bitsPerComponent: 8,
                                      bytesPerRow: width * 4, space: CGColorSpaceCreateDeviceRGB(),
                                      bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return nil }
        context.draw(crop, in: CGRect(x: 0, y: 0, width: width, height: height))
        let values = stride(from: 0, to: data.count, by: 4).map { Int(data[$0]) + Int(data[$0 + 1]) + Int(data[$0 + 2]) }
        return (values, width, height, pixels, scale)
    }

    func testLevelShowsTitleAndValueAndCommitsOnceOnRelease() {
        // The long thumb drag needs the slider's own tracking animation, so this launch keeps animations on.
        let app = start(["surface", "level"], animations: true)
        let level = app.descendants(matching: .any).matching(identifier: "led_brightness").firstMatch
        XCTAssertTrue(level.waitForExistence(timeout: 10))
        // One adjustable element: the visible title is its label and the owner's label its value.
        XCTAssertEqual(level.label, "LED Brightness")
        XCTAssertEqual(level.value as? String, "50%")
        // Drag the thumb from the middle across two grid values and hold before lifting. The playback
        // slider would send on every tick; a level sends exactly one grid value, on release.
        let thumb = level.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.75))
        let end = level.coordinate(withNormalizedOffset: CGVector(dx: 0.98, dy: 0.75))
        // XCUITest cannot sample mid-gesture; a per-tick sender would have counted several sends by now.
        thumb.press(forDuration: 0.3, thenDragTo: end, withVelocity: .slow, thenHoldForDuration: 1)
        XCTAssertTrue(app.staticTexts["level-sends:1"].waitForExistence(timeout: 5))
        let landed = NSPredicate { _, _ in
            ["led_brightness:75.0", "led_brightness:100.0"].contains(app.staticTexts["preview-last-action"].label)
                && ["75%", "100%"].contains(level.value as? String ?? "")
        }
        expectation(for: landed, evaluatedWith: nil)
        waitForExpectations(timeout: 5)
        Thread.sleep(forTimeInterval: 1)
        XCTAssertEqual(app.staticTexts["preview-last-saved"].label, "level-sends:1")
        capture(app, "native-level-control")
    }

    /// Moves a level one grid value by dragging its thumb from [from] to [to] (fractions of the row width).
    /// iOS XCUITest has no increment()/decrement(), so a short drag stands in for one adjustable step.
    func stepLevel(_ level: XCUIElement, from: CGFloat, to: CGFloat) {
        let start = level.coordinate(withNormalizedOffset: CGVector(dx: from, dy: 0.75))
        let end = level.coordinate(withNormalizedOffset: CGVector(dx: to, dy: 0.75))
        start.press(forDuration: 0.3, thenDragTo: end, withVelocity: .slow, thenHoldForDuration: 0.5)
    }

    func testLevelOneStepSendsOneValue() {
        let app = start(["surface", "level"])
        let level = app.descendants(matching: .any).matching(identifier: "led_brightness").firstMatch
        XCTAssertTrue(level.waitForExistence(timeout: 10))
        stepLevel(level, from: 0.5, to: 0.75)
        let stepped = NSPredicate { _, _ in
            app.staticTexts["preview-last-action"].label == "led_brightness:75.0" && (level.value as? String) == "75%"
        }
        expectation(for: stepped, evaluatedWith: nil)
        waitForExpectations(timeout: 5)
        XCTAssertEqual(app.staticTexts["preview-last-saved"].label, "level-sends:1")
        stepLevel(level, from: 0.75, to: 0.5)
        let back = NSPredicate { _, _ in app.staticTexts["preview-last-action"].label == "led_brightness:50.0" }
        expectation(for: back, evaluatedWith: nil)
        waitForExpectations(timeout: 5)
        XCTAssertEqual(app.staticTexts["preview-last-saved"].label, "level-sends:2")
    }

    func testLevelLargeTextKeepsTitleVisible() {
        let app = start(["surface", "level", "large"])
        let level = app.descendants(matching: .any).matching(identifier: "led_brightness").firstMatch
        XCTAssertTrue(level.waitForExistence(timeout: 10))
        XCTAssertEqual(level.label, "LED Brightness")
        XCTAssertTrue(level.isHittable)
        XCTAssertTrue(app.windows.firstMatch.frame.contains(level.frame), "The title row and slider stay on screen")
        XCTAssertGreaterThanOrEqual(level.frame.height, 44)
        capture(app, "native-level-control-large-text")
    }

    func testLevelFailureRevertsValue() {
        let app = start(["surface", "level", "failed-level"])
        let level = app.descendants(matching: .any).matching(identifier: "led_brightness").firstMatch
        XCTAssertTrue(level.waitForExistence(timeout: 10))
        stepLevel(level, from: 0.5, to: 0.75)
        XCTAssertTrue(app.staticTexts["native-surface-error"].waitForExistence(timeout: 5))
        let reverted = NSPredicate { _, _ in (level.value as? String) == "50%" }
        expectation(for: reverted, evaluatedWith: nil)
        waitForExpectations(timeout: 5)
        XCTAssertEqual(app.staticTexts["preview-last-saved"].label, "level-sends:1")
        XCTAssertEqual(app.staticTexts["preview-last-action"].label, "Preview fixture")
        // The failed edit blocks Save until the owner's value is committed again.
        app.buttons["save"].tap()
        Thread.sleep(forTimeInterval: 1)
        XCTAssertFalse(app.staticTexts["save:"].exists)
        stepLevel(level, from: 0.5, to: 0.25)
        XCTAssertTrue(app.staticTexts["level-sends:2"].waitForExistence(timeout: 5))
    }

    /// Whether any pixel inside [frame] (screen points) is a saturated red.
    func containsRed(_ image: UIImage, in frame: CGRect) -> Bool {
        guard let cgImage = image.cgImage else { return false }
        let scale = CGFloat(cgImage.width) / image.size.width
        let pixels = CGRect(x: frame.minX * scale, y: frame.minY * scale, width: frame.width * scale,
                            height: frame.height * scale).integral
        guard let crop = cgImage.cropping(to: pixels) else { return false }
        let width = crop.width, height = crop.height
        var data = [UInt8](repeating: 0, count: width * height * 4)
        guard let context = CGContext(data: &data, width: width, height: height, bitsPerComponent: 8,
                                      bytesPerRow: width * 4, space: CGColorSpaceCreateDeviceRGB(),
                                      bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return false }
        context.draw(crop, in: CGRect(x: 0, y: 0, width: width, height: height))
        return stride(from: 0, to: data.count, by: 4).contains { index in
            data[index] > 170 && data[index + 1] < 110 && data[index + 2] < 110
        }
    }

    /// Launches the fixture without animations, which keeps the suite fast; a test that checks an animation
    /// passes `animations: true`. The flag goes last, so it never takes another argument as its value.
    func start(_ arguments: [String] = [], animations: Bool = false) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = animations ? arguments : arguments + ["-ui-test-no-animations"]
        app.launch()
        return app
    }
    func capture(_ app: XCUIApplication, _ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
    func testReadTranscriptAndNativeBack() {
        let app = start()
        let row = app.buttons["native-conversation-conversation-1"]
        XCTAssertTrue(row.waitForExistence(timeout: 10))
        capture(app, "native-home-dark")
        row.tap()
        XCTAssertTrue(app.buttons["native-conversation-actions"].waitForExistence(timeout: 5))
        capture(app, "native-summary")
        app.segmentedControls.buttons["Transcript"].tap()
        XCTAssertTrue(app.staticTexts["Let us start with native conversation browsing."].waitForExistence(timeout: 5))
        capture(app, "native-transcript")
        app.navigationBars.buttons.element(boundBy: 0).tap()
        XCTAssertTrue(row.waitForExistence(timeout: 5))
    }
    func testLockedRowRoutesToExistingAction() {
        let app = start()
        app.buttons["native-conversation-locked-1"].tap()
        XCTAssertTrue(app.staticTexts["open:locked-1"].waitForExistence(timeout: 5))
    }
    func testFailedReadCanRetry() {
        let app = start(["error"])
        XCTAssertTrue(app.buttons["native-retry"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.staticTexts["No conversations yet"].exists)
        app.buttons["native-retry"].tap()
        XCTAssertTrue(app.buttons["native-conversation-conversation-1"].waitForExistence(timeout: 5))
    }
    func testEmptyReadIsNotError() {
        let app = start(["empty"])
        XCTAssertTrue(app.staticTexts["No conversations yet"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["native-retry"].exists)
        capture(app, "native-empty")
    }
    func testEmptySurfaceCentresItsCopyAndKeepsItsIdentifier() {
        let app = start(["surface", "empty-surface"])
        let empty = app.staticTexts["native-surface-empty"]
        XCTAssertTrue(empty.waitForExistence(timeout: 10))
        XCTAssertEqual(empty.label, "No tasks yet")
        let window = app.windows.firstMatch.frame
        XCTAssertEqual(empty.frame.midX, window.midX, accuracy: 2, "The empty state is centred, not a leading row")
        XCTAssertGreaterThan(empty.frame.minY, window.height / 4)
        XCTAssertTrue(app.buttons["save"].isHittable, "The empty state never covers the toolbar")
        capture(app, "native-surface-empty")
    }
    func testSessionInvalidationHidesNativeTranscript() {
        let app = start()
        app.buttons["native-conversation-conversation-1"].tap()
        app.segmentedControls.buttons["Transcript"].tap()
        XCTAssertTrue(app.staticTexts["Let us start with native conversation browsing."].waitForExistence(timeout: 5))
        app.buttons["preview-end-session"].tap()
        XCTAssertFalse(app.staticTexts["Let us start with native conversation browsing."].exists)
        XCTAssertFalse(app.staticTexts["Design catch-up"].exists)
    }
    func testLargeTextLightAppearance() {
        let app = start(["large", "light"])
        XCTAssertTrue(app.buttons["native-conversation-conversation-1"].waitForExistence(timeout: 5))
        capture(app, "native-home-large-text-light")
        app.buttons["native-conversation-conversation-1"].tap()
        XCTAssertTrue(app.buttons["native-conversation-actions"].waitForExistence(timeout: 5))
        app.segmentedControls.buttons["Transcript"].tap()
        XCTAssertTrue(app.staticTexts["Let us start with native conversation browsing."].waitForExistence(timeout: 5))
        capture(app, "native-transcript-large-text")
    }
    func testCompleteHomeChromeScrollAndActions() {
        let app = start(["chrome"])
        XCTAssertTrue(app.buttons["native-settings"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["native-device"].label.contains("53%"))
        XCTAssertTrue(app.buttons["native-recap-recap-1"].isHittable)
        let chat = app.buttons["native-chat"]
        // The system glass footer can finish its initial layout after the header is ready.
        // Wait for the actual tap target, then assert the dispatched owner action too.
        let hittable = XCTNSPredicateExpectation(predicate: NSPredicate(format: "isHittable == true"), object: chat)
        XCTAssertEqual(XCTWaiter.wait(for: [hittable], timeout: 10), .completed)
        chat.tap()
        XCTAssertTrue(app.staticTexts["chat:"].waitForExistence(timeout: 5))
        capture(app, "native-home-liquid-glass")
        app.buttons["native-tasks"].tap()
        capture(app, "native-home-after-tasks-action")
        XCTAssertTrue(app.staticTexts["tasks:"].waitForExistence(timeout: 5))
        app.swipeUp()
        XCTAssertTrue(app.buttons["native-conversation-conversation-1"].isHittable)
    }
    func testSeveralRecapsPageWithTheNextCardPeeking() {
        let app = start(["chrome", "recaps"])
        let first = app.buttons["native-recap-recap-1"], second = app.buttons["native-recap-recap-2"]
        XCTAssertTrue(first.waitForExistence(timeout: 10))
        XCTAssertTrue(first.isHittable)
        let window = app.windows.firstMatch.frame
        // The next card shows at the trailing edge, so the row reads as a carousel rather than one card.
        XCTAssertLessThan(first.frame.width, window.width - 40)
        XCTAssertTrue(second.exists)
        XCTAssertLessThan(second.frame.minX, window.maxX)
        capture(app, "native-home-recap-carousel")
        first.swipeLeft()
        wait(until: second.isHittable, "A swipe pages to the next recap")
        second.tap()
        XCTAssertTrue(app.staticTexts["recap:recap-2"].waitForExistence(timeout: 5))
    }
    func testHomeChromeLargeTextKeepsControlsReachable() {
        let app = start(["chrome", "large", "light"])
        XCTAssertTrue(app.buttons["native-chat"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["native-chat"].isHittable)
        XCTAssertLessThan(app.buttons["native-chat"].frame.height, 100)
        XCTAssertLessThan(app.buttons["native-tasks"].frame.height, 100)
        capture(app, "native-home-liquid-glass-large-text")
        app.swipeUp()
        XCTAssertTrue(app.buttons["native-recap-recap-1"].exists)
    }
    func testNativeTextKeepsLastRapidEdit() {
        let app = start(["surface"])
        let field = app.textFields["draft"].exists ? app.textFields["draft"] : app.textViews["draft"]
        XCTAssertTrue(field.waitForExistence(timeout: 10))
        field.tap()
        field.typeText("rapid final edit")
        XCTAssertTrue(app.staticTexts["draft:rapid final edit"].waitForExistence(timeout: 10))
        capture(app, "native-settings-edit")
    }

    func testSettingsNavigationTagsAndSafeHeader() {
        let app = start(["settings-menu"])
        let close = app.buttons["settings_close"]
        XCTAssertTrue(close.waitForExistence(timeout: 10))
        XCTAssertTrue(close.isHittable)
        if app.statusBars.firstMatch.exists {
            XCTAssertGreaterThanOrEqual(close.frame.minY, app.statusBars.firstMatch.frame.maxY)
        }
        XCTAssertTrue(app.buttons["account"].isHittable)
        XCTAssertTrue(app.staticTexts["NEW"].exists)
        XCTAssertTrue(app.staticTexts["BETA"].exists)
        capture(app, "native-settings-menu-dark")
        app.buttons["account"].tap()
        XCTAssertTrue(app.staticTexts["account:"].waitForExistence(timeout: 5))
        close.tap()
        XCTAssertTrue(app.staticTexts["settings_close:"].waitForExistence(timeout: 5))
    }

    func testSaveWaitsForLastQueuedEdit() {
        let app = start(["surface"])
        let field = app.textFields["draft"].exists ? app.textFields["draft"] : app.textViews["draft"]
        XCTAssertTrue(field.waitForExistence(timeout: 10))
        field.tap()
        field.typeText("do not save old text")
        app.buttons["save"].tap()
        XCTAssertTrue(app.staticTexts["preview-last-saved"].waitForExistence(timeout: 10))
        XCTAssertEqual(app.staticTexts["preview-last-saved"].label, "saved:do not save old text")
    }
    func testNativeChatSendPreservesFinalDraftAndClearsIt() {
        let app = start(["chat"])
        let field = app.textFields["chat_draft"].exists ? app.textFields["chat_draft"] : app.textViews["chat_draft"]
        XCTAssertTrue(field.waitForExistence(timeout: 10))
        field.tap()
        field.typeText("native final draft")
        app.buttons["chat_send"].tap()
        XCTAssertTrue(app.staticTexts["preview-last-saved"].waitForExistence(timeout: 10))
        XCTAssertEqual(app.staticTexts["preview-last-saved"].label, "saved:native final draft")
        XCTAssertEqual(field.value as? String, "Ask Omi")
        capture(app, "native-chat-liquid-glass")
    }

    func testNativeSwitchCallsOriginalMutation() {
        let app = start(["surface"])
        XCTAssertTrue(app.switches["enabled"].waitForExistence(timeout: 10))
        app.switches["enabled"].switches.firstMatch.tap()
        let updated = XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == '0'"), object: app.switches["enabled"])
        XCTAssertEqual(XCTWaiter.wait(for: [updated], timeout: 5), .completed)
    }
    func testNativePickerKeepsChoice() {
        let app = start(["surface"])
        app.buttons["mode"].tap()
        app.buttons["Dark"].tap()
        XCTAssertTrue(app.staticTexts["mode:dark"].waitForExistence(timeout: 5))
    }
    func testFailedEditCannotSaveStaleContent() {
        let app = start(["surface", "failed-edit"])
        let field = app.textFields["draft"]
        XCTAssertTrue(field.waitForExistence(timeout: 10))
        field.tap()
        // The first rejected edit removes focus. Do not type into an invalidated field.
        field.typeText("x")
        app.buttons["save"].tap()
        XCTAssertTrue(app.staticTexts["native-surface-error"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.staticTexts["saved:"].exists)
    }
    func testNativeSurfaceSessionInvalidationRemovesDraft() {
        let app = start(["surface"])
        let field = app.textFields["draft"]
        XCTAssertTrue(field.waitForExistence(timeout: 10))
        field.tap()
        field.typeText("private text")
        app.buttons["preview-end-session"].tap()
        XCTAssertFalse(field.exists)
        XCTAssertFalse(app.staticTexts["Appearance"].exists)
    }

    func testNativeAttachmentMenuForwardsSelectedPayload() {
        // Keep the fixture receipt away from the system menu/composer hit targets.
        let app = start(["chat", "attachments", "chrome"])
        XCTAssertTrue(app.buttons["chat_attach"].waitForExistence(timeout: 10))
        app.buttons["chat_attach"].tap()
        app.buttons["Choose File"].tap()
        XCTAssertTrue(app.staticTexts["chat_attach:file"].waitForExistence(timeout: 5))
        capture(app, "native-chat-attachment-menu")
    }
    func testGraphFillTapsSelectNodesWhileCameraGesturesSendNothing() {
        let app = start(["surface", "graph-fill"])
        let graph = app.otherElements["graph_canvas"]
        XCTAssertTrue(graph.waitForExistence(timeout: 30))
        let receipt = app.staticTexts["preview-last-action"]
        // The fixed user node sits at the origin, the centre of the stage.
        graph.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        XCTAssertTrue(app.staticTexts["graph_canvas:'me'"].waitForExistence(timeout: 15))
        let ada = app.buttons["graph_canvas_node_ada"]
        XCTAssertTrue(ada.waitForExistence(timeout: 10))
        ada.tap()
        XCTAssertTrue(app.staticTexts["graph_canvas:'ada'"].waitForExistence(timeout: 15))
        wait(until: ada.isSelected, "The owner's selection reaches the node element")
        capture(app, "native-graph-fill-selected")
        graph.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).withOffset(CGVector(dx: -170, dy: 0)).tap()
        XCTAssertTrue(app.staticTexts["graph_canvas:''"].waitForExistence(timeout: 15))
        wait(until: !ada.isSelected, "A background tap clears the selection")

        let zoomElement = app.descendants(matching: .any)["graph_canvas_zoom"]
        let zoom = zoomElement.value as? String
        let position = ada.frame
        graph.pinch(withScale: 1.8, velocity: 1)
        graph.swipeLeft()
        graph.rotate(0.5, withVelocity: 1)
        Thread.sleep(forTimeInterval: 2)
        XCTAssertEqual(receipt.label, "graph_canvas:''", "Pinch, rotation and pan stay native")
        XCTAssertNotEqual(zoomElement.value as? String, zoom)
        XCTAssertNotEqual(ada.frame, position)
        capture(app, "native-graph-fill-camera")
    }

    func testGraphFillKeepsLabelsAboveAndButtonsBelowAtLargeText() {
        let app = start(["surface", "graph-fill", "large"])
        let graph = app.otherElements["graph_canvas"]
        XCTAssertTrue(graph.waitForExistence(timeout: 30))
        let hint = app.staticTexts["graph_hint"]
        let proceed = app.buttons["graph_continue"]
        XCTAssertTrue(hint.exists)
        // A label row's accessibility frame reaches past its text, so compare where the hint is drawn.
        let hintText = inkBounds(app.screenshot().image, in: hint.frame) ?? .null
        XCTAssertFalse(hintText.isNull, "The hint is drawn")
        XCTAssertLessThanOrEqual(hintText.maxY, graph.frame.minY + 1)
        XCTAssertGreaterThanOrEqual(proceed.frame.minY, graph.frame.maxY - 1)
        XCTAssertGreaterThan(graph.frame.height, 100)
        XCTAssertTrue(proceed.isHittable)
        XCTAssertTrue(app.buttons["graph_back"].isHittable)
        capture(app, "native-graph-fill-large-text")
        proceed.tap()
        XCTAssertTrue(app.staticTexts["graph_continue:"].waitForExistence(timeout: 15))
    }

    func testGraphFillListsNodesForVoiceOverWithAdjustableZoom() {
        let app = start(["surface", "graph-fill"])
        let graph = app.otherElements["graph_canvas"]
        XCTAssertTrue(graph.waitForExistence(timeout: 30))
        XCTAssertEqual(graph.label, "Memory Graph")
        for (id, label) in [("me", "You"), ("ada", "Ada"), ("paris", "Paris"), ("omi", "Omi"), ("pendant", "Pendant"),
                            ("memory", "Memory")] {
            let node = app.buttons["graph_canvas_node_\(id)"]
            XCTAssertTrue(node.exists, id)
            XCTAssertEqual(node.label, label)
            XCTAssertFalse(node.isSelected)
            XCTAssertTrue(graph.frame.contains(CGPoint(x: node.frame.midX, y: node.frame.midY)), id)
        }
        let zoom = app.descendants(matching: .any)["graph_canvas_zoom"]
        XCTAssertTrue(zoom.exists)
        XCTAssertEqual(zoom.label, "Memory Graph")
        XCTAssertEqual(zoom.value as? String, "100%")
        // XCUITest on iOS reports neither the adjustable trait nor VoiceOver's swipe up and down, so the
        // fixture adjusts the element as VoiceOver does, and only when it carries the adjustable trait.
        app.buttons["preview-voiceover-increment"].tap()
        waitForLabel(app.staticTexts["preview-last-saved"], "graph_canvas_zoom:incremented")
        wait(until: zoom.value as? String == "125%", "VoiceOver can zoom the graph in")
        app.buttons["preview-voiceover-decrement"].tap()
        waitForLabel(app.staticTexts["preview-last-saved"], "graph_canvas_zoom:decremented")
        wait(until: zoom.value as? String == "100%", "VoiceOver can zoom the graph out")
        XCTAssertEqual(app.staticTexts["preview-last-action"].label, "Preview fixture", "Zooming sends nothing to Dart")
    }

    func testGraphCardTapSendsNilAndTheListStillScrolls() {
        let app = start(["surface", "graph-card"])
        let card = app.buttons["graph_card"]
        XCTAssertTrue(card.waitForExistence(timeout: 30))
        XCTAssertEqual(card.label, "Memory Graph")
        XCTAssertGreaterThanOrEqual(card.frame.height, 139)
        capture(app, "native-graph-card")
        let top = card.frame.minY
        card.swipeUp()
        wait(until: !card.exists || card.frame.minY < top - 40, "A drag that starts on the card scrolls the list")
        XCTAssertEqual(app.staticTexts["preview-last-action"].label, "Preview fixture")
        app.swipeDown()
        app.swipeDown()
        wait(until: card.isHittable, "The card returns")
        card.tap()
        XCTAssertTrue(app.staticTexts["graph_card:nil"].waitForExistence(timeout: 15))
    }

    func testGraphPlaceholderPulsesThenRests() {
        // The pulse is an animation, so this launch keeps animations on.
        let app = start(["surface", "graph-placeholder"], animations: true)
        let graph = app.otherElements["graph_canvas"]
        XCTAssertTrue(graph.waitForExistence(timeout: 30))
        XCTAssertTrue(app.descendants(matching: .any)["native-surface-loading"].waitForExistence(timeout: 10))
        let skeleton = skeletonRegion(graph.frame)
        var pulsed = false
        for _ in 0..<4 where !pulsed {
            let first = app.screenshot().image
            Thread.sleep(forTimeInterval: 0.5)
            pulsed = changedPixels(first, app.screenshot().image, in: skeleton) > 0
        }
        XCTAssertTrue(pulsed, "The skeleton pulses while loading")
        capture(app, "native-graph-placeholder")
        // Six pulses of 2 x 0.6 s (7.2 s), then it rests.
        Thread.sleep(forTimeInterval: 8)
        let rested = app.screenshot().image
        Thread.sleep(forTimeInterval: 0.6)
        XCTAssertEqual(changedPixels(rested, app.screenshot().image, in: skeleton), 0)
    }

    func testGraphPlaceholderIsStaticUnderReduceMotion() {
        // Reduce Motion is checked against a launch whose animations are otherwise on.
        let app = start(["surface", "graph-placeholder", "reduce-motion"], animations: true)
        let graph = app.otherElements["graph_canvas"]
        XCTAssertTrue(graph.waitForExistence(timeout: 30))
        let skeleton = skeletonRegion(graph.frame)
        for _ in 0..<3 {
            let first = app.screenshot().image
            Thread.sleep(forTimeInterval: 0.5)
            XCTAssertEqual(changedPixels(first, app.screenshot().image, in: skeleton), 0)
        }
    }

    /// The skeleton's left fifth, clear of the centred loading status.
    func skeletonRegion(_ frame: CGRect) -> CGRect {
        CGRect(x: frame.minX, y: frame.minY + frame.height * 0.2, width: frame.width * 0.22, height: frame.height * 0.6)
    }

    /// Pixels in [frame] (screen points) whose colour moved by more than a rounding step.
    func changedPixels(_ first: UIImage, _ second: UIImage, in frame: CGRect) -> Int {
        func pixels(_ image: UIImage) -> [UInt8] {
            guard let cgImage = image.cgImage else { return [] }
            let scale = CGFloat(cgImage.width) / image.size.width
            let crop = CGRect(x: frame.minX * scale, y: frame.minY * scale, width: frame.width * scale,
                              height: frame.height * scale).integral
            guard let region = cgImage.cropping(to: crop) else { return [] }
            var data = [UInt8](repeating: 0, count: region.width * region.height * 4)
            guard let context = CGContext(data: &data, width: region.width, height: region.height, bitsPerComponent: 8,
                                          bytesPerRow: region.width * 4, space: CGColorSpaceCreateDeviceRGB(),
                                          bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return [] }
            context.draw(region, in: CGRect(x: 0, y: 0, width: region.width, height: region.height))
            return data
        }
        let a = pixels(first), b = pixels(second)
        guard !a.isEmpty, a.count == b.count else { return -1 }
        return stride(from: 0, to: a.count, by: 4).filter { index in
            (0..<3).contains { abs(Int(a[index + $0]) - Int(b[index + $0])) > 4 }
        }.count
    }

    func wait(until condition: @escaping @autoclosure () -> Bool, _ message: String, timeout: TimeInterval = 15) {
        let predicate = NSPredicate { _, _ in condition() }
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: predicate, object: nil)], timeout: timeout),
                       .completed, message)
    }

    func testNativeVoiceWaveformKeepsControlsReachableAtLargeText() {
        let app = start(["chat", "voice", "large"])
        XCTAssertTrue(app.buttons["chat_voice_stop"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["chat_voice_stop"].isHittable)
        XCTAssertTrue(app.buttons["chat_voice_discard"].isHittable)
        capture(app, "native-chat-voice-large-text")
        app.buttons["chat_voice_stop"].tap()
        XCTAssertTrue(app.staticTexts["chat_voice_stop:"].waitForExistence(timeout: 5))
        app.buttons["preview-end-session"].tap()
        XCTAssertFalse(app.buttons["chat_voice_stop"].exists)
    }

    func testNativeModalReportsCancelAndSwipeReasons() {
        let app = start(["modal"])
        app.buttons["modal-open"].tap()
        XCTAssertTrue(app.textFields["draft"].waitForExistence(timeout: 10))
        app.buttons["cancel"].tap()
        XCTAssertTrue(app.staticTexts["reason:cancel"].waitForExistence(timeout: 10))
        XCTAssertEqual(app.staticTexts["modal-receipt"].label, "Cancelled without saving")
        app.buttons["modal-open"].tap()
        let field = app.textFields["draft"]
        XCTAssertTrue(field.waitForExistence(timeout: 10))
        // Drag the clean sheet down by its grabber.
        app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.08))
            .press(forDuration: 0.1, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.98)))
        XCTAssertTrue(app.staticTexts["reason:dismissed"].waitForExistence(timeout: 10))
        XCTAssertFalse(field.exists)
        capture(app, "native-modal-swipe-dismissed")
    }

    func testNonDismissibleSheetIgnoresSwipes() {
        let app = start(["modal", "locked"])
        app.buttons["modal-open"].tap()
        let field = app.textFields["draft"]
        XCTAssertTrue(field.waitForExistence(timeout: 10))
        app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.08))
            .press(forDuration: 0.1, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.98)))
        XCTAssertTrue(field.waitForExistence(timeout: 5))
        XCTAssertFalse(app.staticTexts["reason:dismissed"].exists)
        app.buttons["cancel"].tap()
        XCTAssertTrue(app.staticTexts["reason:cancel"].waitForExistence(timeout: 10))
    }

    func testNativeAlertCancelAndProgrammaticDismissalReportReasons() {
        let alert = start(["modal", "alert"])
        alert.buttons["modal-open"].tap()
        XCTAssertTrue(alert.alerts["Edit Person"].waitForExistence(timeout: 5))
        alert.alerts.buttons["Cancel"].tap()
        XCTAssertTrue(alert.staticTexts["reason:cancel"].waitForExistence(timeout: 10))
        alert.terminate()
        let expired = start(["modal", "expire"])
        expired.buttons["modal-open"].tap()
        XCTAssertTrue(expired.textFields["draft"].waitForExistence(timeout: 5))
        XCTAssertTrue(expired.staticTexts["reason:programmatic"].waitForExistence(timeout: 10))
        XCTAssertFalse(expired.textFields["draft"].exists)
    }

    func testForeignDismissalReleasesTheSlotAsDismissed() {
        let app = start(["modal", "foreign-dismiss"])
        app.buttons["modal-open"].tap()
        XCTAssertTrue(app.textFields["draft"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["reason:dismissed"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.textFields["draft"].exists)
        // The presenter's single slot is free again.
        app.buttons["modal-open"].tap()
        XCTAssertTrue(app.textFields["draft"].waitForExistence(timeout: 5))
        XCTAssertNotEqual(app.staticTexts["modal-receipt"].label, "Presentation failed")
    }

    func testActivityBlocksContentAndDismissesProgrammatically() {
        let app = start(["modal"])
        let beneath = app.buttons["activity-beneath"]
        XCTAssertTrue(beneath.waitForExistence(timeout: 10))
        // A screen point, because the modal overlay hides the content beneath from accessibility.
        let frame = beneath.frame
        let target = app.coordinate(withNormalizedOffset: .zero).withOffset(CGVector(dx: frame.midX, dy: frame.midY))
        app.buttons["activity-open"].tap()
        let activity = app.descendants(matching: .any)["native-activity"]
        XCTAssertTrue(activity.waitForExistence(timeout: 5))
        target.tap()
        XCTAssertTrue(activity.exists, "The tap landed while the overlay was up")
        capture(app, "native-activity")
        XCTAssertTrue(app.staticTexts["reason:programmatic"].waitForExistence(timeout: 15))
        XCTAssertFalse(activity.exists)
        XCTAssertEqual(app.staticTexts["activity-beneath-count"].label, "beneath:0", "The overlay took the tap")
        XCTAssertEqual(app.staticTexts["modal-receipt"].label, "Second presentation refused")
        beneath.tap()
        XCTAssertEqual(app.staticTexts["activity-beneath-count"].label, "beneath:1")
    }

    func testActivityLargeTextLabelStaysVisible() {
        let app = start(["modal", "large", "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"])
        app.buttons["activity-open"].tap()
        // The card is one accessibility element whose label is the activity label.
        let card = app.descendants(matching: .any)["native-activity"]
        XCTAssertTrue(card.waitForExistence(timeout: 5))
        XCTAssertTrue(card.label.contains("Saving your changes to this conversation summary"))
        XCTAssertTrue(app.windows.firstMatch.frame.contains(card.frame))
        XCTAssertGreaterThan(card.frame.height, 100, "The label wraps instead of truncating")
        capture(app, "native-activity-large-text")
        XCTAssertTrue(app.staticTexts["reason:programmatic"].waitForExistence(timeout: 15))
    }

    func testToastAboveAPageSheetIsHittableAndReportsItsAction() {
        let app = start(["toast"])
        app.buttons["toast-sheet"].tap()
        XCTAssertTrue(app.buttons["sheet-undo"].waitForExistence(timeout: 10))
        app.buttons["sheet-undo"].tap()
        let action = app.buttons["native-toast-action"]
        XCTAssertTrue(action.waitForExistence(timeout: 5))
        XCTAssertTrue(action.isHittable)
        XCTAssertEqual(action.label, "Undo")
        capture(app, "native-toast-above-sheet")
        action.tap()
        waitForLabel(app.staticTexts["sheet-outcomes"], "1:action")
        XCTAssertTrue(waitForDisappearance(app.otherElements["native-toast"]))
    }

    func testToastStaysTappableAboveABlockingOverlay() {
        let app = start(["toast"])
        app.buttons["toast-overlay"].tap()
        let action = app.buttons["native-toast-action"]
        XCTAssertTrue(action.waitForExistence(timeout: 10))
        XCTAssertTrue(action.isHittable)
        capture(app, "native-toast-above-activity")
        action.tap()
        waitForLabel(app.staticTexts["overlay-outcomes"], "1:action")
    }

    func testTouchesOutsideTheToastReachTheContentBelow() {
        let app = start(["toast"])
        app.buttons["toast-progress"].tap()
        let toast = app.otherElements["native-toast"]
        XCTAssertTrue(toast.waitForExistence(timeout: 5))
        // Coordinate taps test real touch pass-through rather than the accessibility hit test.
        let background = app.buttons["toast-background"]
        background.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        background.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        waitForLabel(background, "Background 2")
        XCTAssertTrue(toast.exists, "A touch outside the toast leaves it up")
        XCTAssertEqual(app.staticTexts["toast-outcomes"].label, "none")
        app.buttons["toast-dismiss"].tap()
        waitForLabel(app.staticTexts["toast-outcomes"], "1:invalidated")
        XCTAssertTrue(waitForDisappearance(toast))
        background.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        waitForLabel(background, "Background 3")
    }

    func testToastAnnouncesItsMessageAndTimesOut() {
        let app = start(["toast"])
        app.buttons["toast-confirm"].tap()
        XCTAssertTrue(app.staticTexts["native-toast-message"].waitForExistence(timeout: 5))
        waitForLabel(app.staticTexts["toast-announcement"], "Saved")
        waitForLabel(app.staticTexts["toast-outcomes"], "1:timeout", timeout: 6)
        XCTAssertTrue(waitForDisappearance(app.otherElements["native-toast"]))
    }

    func testNewerToastReplacesTheCurrentOneAndCloseReportsClosed() {
        let app = start(["toast"])
        app.buttons["toast-undo"].tap()
        XCTAssertTrue(app.buttons["native-toast-action"].waitForExistence(timeout: 5))
        app.buttons["toast-error"].tap()
        waitForLabel(app.staticTexts["toast-outcomes"], "1:replaced")
        let close = app.buttons["native-toast-close"]
        XCTAssertTrue(close.waitForExistence(timeout: 5))
        XCTAssertEqual(close.label, "Close")
        // The replaced capsule leaves with a short transition; wait until only the new action remains.
        let single = NSPredicate { _, _ in app.buttons.matching(identifier: "native-toast-action").count == 1 }
        expectation(for: single, evaluatedWith: nil)
        waitForExpectations(timeout: 5)
        XCTAssertEqual(app.buttons["native-toast-action"].label, "Try Again")
        capture(app, "native-toast-error")
        close.tap()
        waitForLabel(app.staticTexts["toast-outcomes"], "1:replaced,2:closed")
    }

    func testSwipingTheToastDownReportsSwiped() {
        let app = start(["toast"])
        app.buttons["toast-undo"].tap()
        let toast = app.otherElements["native-toast"]
        XCTAssertTrue(toast.waitForExistence(timeout: 5))
        // Drag the capsule well past the 24 pt threshold. swipeDown() scales its travel to the element, so
        // on the one-line message it moves the finger only about 8 pt and the toast rightly springs back.
        let centre = toast.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5))
        centre.press(forDuration: 0.05, thenDragTo: centre.withOffset(CGVector(dx: 0, dy: 80)), withVelocity: .fast,
                     thenHoldForDuration: 0)
        waitForLabel(app.staticTexts["toast-outcomes"], "1:swiped")
        XCTAssertTrue(waitForDisappearance(toast))
    }

    func testToastFollowsRightToLeftAndAccessibilityTextSizes() {
        let app = start(["toast", "rtl", "long", "-UIPreferredContentSizeCategoryName",
                         "UICTContentSizeCategoryAccessibilityXL"])
        app.buttons["toast-undo"].tap()
        let toast = app.otherElements["native-toast"]
        let action = app.buttons["native-toast-action"]
        XCTAssertTrue(action.waitForExistence(timeout: 5))
        XCTAssertTrue(action.isHittable)
        let screen = app.windows.firstMatch.frame
        XCTAssertGreaterThanOrEqual(toast.frame.minX, screen.minX)
        XCTAssertLessThanOrEqual(toast.frame.maxX, screen.maxX)
        XCTAssertLessThan(toast.frame.height, screen.height / 2, "The message is limited to four lines")
        XCTAssertLessThan(action.frame.midX, toast.frame.midX, "The action trails the message on the left in RTL")
        capture(app, "native-toast-rtl-large-text")
        action.tap()
        waitForLabel(app.staticTexts["toast-outcomes"], "1:action")
    }

    func testToastRisesAboveTheKeyboard() {
        let app = start(["toast"])
        let field = app.textFields["toast-field"]
        XCTAssertTrue(field.waitForExistence(timeout: 10))
        field.tap()
        let keyboard = app.keyboards.firstMatch
        XCTAssertTrue(keyboard.waitForExistence(timeout: 5))
        app.buttons["toast-undo"].tap()
        let toast = app.otherElements["native-toast"]
        XCTAssertTrue(toast.waitForExistence(timeout: 5))
        let above = NSPredicate { _, _ in toast.frame.maxY <= keyboard.frame.minY }
        expectation(for: above, evaluatedWith: nil)
        waitForExpectations(timeout: 5)
        XCTAssertTrue(toast.isHittable)
        capture(app, "native-toast-keyboard")
        // The toast's window never becomes key, so its action leaves the focused field and keyboard alone.
        app.buttons["native-toast-action"].tap()
        waitForLabel(app.staticTexts["toast-outcomes"], "1:action")
        XCTAssertTrue(keyboard.exists)
    }

    func waitForLabel(_ element: XCUIElement, _ label: String, timeout: TimeInterval = 5) {
        let matches = NSPredicate { _, _ in element.exists && element.label == label }
        expectation(for: matches, evaluatedWith: nil)
        waitForExpectations(timeout: timeout)
    }

    func waitForDisappearance(_ element: XCUIElement, timeout: TimeInterval = 5) -> Bool {
        let gone = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: element)
        return XCTWaiter.wait(for: [gone], timeout: timeout) == .completed
    }

    func testSecretIsMonospacedAndCopySendsOnlyTheCommand() {
        let app = start(["surface", "secret"])
        let key = "omi_dev_iiiiiiiiiiiiiiii"
        let value = app.staticTexts[key]
        XCTAssertTrue(value.waitForExistence(timeout: 10))
        // Sixteen narrow letters: a proportional font would draw this key far narrower.
        XCTAssertGreaterThan(value.frame.width, CGFloat(key.count) * 8)
        XCTAssertEqual(value.identifier, "secret_value")
        capture(app, "native-secret-reveal")
        let copy = app.buttons["secret_value"]
        XCTAssertEqual(copy.label, "Copy")
        copy.tap()
        XCTAssertTrue(app.staticTexts["secret_value:copy"].waitForExistence(timeout: 5))
        XCTAssertEqual(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", key)).count, 1,
                       "Only the secret row carries the key; the copy command never echoes it")
        app.buttons["secret_done"].tap()
        XCTAssertTrue(app.staticTexts["secret_done:"].waitForExistence(timeout: 5))
    }

    func testSecretRedactsWhileInactiveAndClearsOnSessionEnd() {
        let app = start(["surface", "secret"])
        let key = "omi_dev_iiiiiiiiiiiiiiii"
        XCTAssertTrue(app.staticTexts[key].waitForExistence(timeout: 10))
        app.buttons["preview-resign-active"].tap()
        let hidden = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: app.staticTexts[key])
        XCTAssertEqual(XCTWaiter.wait(for: [hidden], timeout: 5), .completed)
        capture(app, "native-secret-inactive-redacted")
        app.buttons["preview-become-active"].tap()
        XCTAssertTrue(app.staticTexts[key].waitForExistence(timeout: 5))
        app.buttons["preview-end-session"].tap()
        let cleared = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: app.buttons["secret_value"])
        XCTAssertEqual(XCTWaiter.wait(for: [cleared], timeout: 5), .completed)
        XCTAssertFalse(app.staticTexts[key].exists)
    }

    func testRichAIMessageRendersBlocksAndOpensOnlyWhitelistedLinks() {
        let app = start(["chat", "chat-rich"])
        // A heading, ordered and nested list items, a quote, code and a table all render in the AI bubble.
        for text in ["Launch plan", "1.", "Ship the native body", "Keep the owner", "Links stay with Dart",
                     "let owner = \"Dart\"", "Opens links"] {
            XCTAssertTrue(app.staticTexts[text].waitForExistence(timeout: 10), text)
        }
        // A link whitelist never adds a trailing button; only the retry row's explicit symbol does.
        XCTAssertTrue(app.staticTexts["Open"].exists)
        XCTAssertFalse(app.buttons["Open"].exists)
        XCTAssertTrue(app.buttons["Try again"].exists)
        XCTAssertGreaterThanOrEqual(app.buttons["Try again"].frame.height, 44, "The labelled retry keeps its hit target")
        capture(app, "native-chat-rich-ai-message")
        // Neither an unlisted link in a reply nor one in a reader row without options leaves the app.
        for link in ["another site", "unlisted note"] {
            XCTAssertTrue(app.links[link].waitForExistence(timeout: 5), link)
            app.links[link].tap()
            Thread.sleep(forTimeInterval: 2)
            XCTAssertEqual(app.state, .runningForeground, "\(link) must not open the system browser")
            XCTAssertEqual(app.staticTexts["preview-last-action"].label, "Preview fixture", link)
        }
        app.links["allowed guide"].tap()
        XCTAssertTrue(app.staticTexts["chat_rich_ai:https://omi.me/allowed"].waitForExistence(timeout: 5))
        XCTAssertEqual(app.state, .runningForeground)
        app.buttons["Try again"].tap()
        XCTAssertTrue(app.staticTexts["chat_rich_retry:"].waitForExistence(timeout: 5))
    }

    /// Visual review captures in the light appearance and right to left, and of the open editor sheet, which
    /// the behaviour tests above only capture after it closes. Each waits for its screen; nothing is tapped
    /// beyond opening the presentation under review.
    func testLightRightToLeftAndSheetReviewCaptures() {
        var app = start(["chat", "chat-rich", "light"])
        XCTAssertTrue(app.buttons["Try again"].waitForExistence(timeout: 10))
        capture(app, "native-chat-rich-light")
        app = start(["chat", "attachments", "rtl", "chrome"])
        XCTAssertTrue(app.buttons["chat_attach"].waitForExistence(timeout: 10))
        capture(app, "native-chat-rtl")
        app = start(["chat", "voice"])
        XCTAssertTrue(app.buttons["chat_voice_stop"].waitForExistence(timeout: 10))
        capture(app, "native-chat-voice")
        app = start(["chat", "attachments", "followup", "light"])
        XCTAssertTrue(app.buttons["What should I do next?"].waitForExistence(timeout: 10))
        capture(app, "native-chat-followup-light")
        app = start(["surface", "reader", "light"])
        XCTAssertTrue(app.buttons["play"].waitForExistence(timeout: 10))
        capture(app, "native-conversation-reader-light")
        app = start(["surface", "light"])
        XCTAssertTrue(app.switches["enabled"].waitForExistence(timeout: 10))
        capture(app, "native-settings-light")
        for appearance in ["dark", "light"] {
            app = start(["surface", "form-rows", appearance])
            XCTAssertTrue(app.buttons["delete_account"].waitForExistence(timeout: 10))
            capture(app, "native-form-rows-\(appearance)")
        }
        for appearance in ["dark", "light"] {
            app = start(["modal", appearance])
            app.buttons["modal-open"].tap()
            XCTAssertTrue(app.textFields["draft"].waitForExistence(timeout: 10))
            XCTAssertTrue(app.buttons["save"].waitForExistence(timeout: 5))
            capture(app, "native-modal-sheet-\(appearance)")
        }
        app = start(["modal", "light"])
        app.buttons["activity-open"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["native-activity"].waitForExistence(timeout: 5))
        capture(app, "native-activity-light")
        app = start(["toast", "light"])
        app.buttons["toast-error"].tap()
        XCTAssertTrue(app.buttons["native-toast-close"].waitForExistence(timeout: 5))
        capture(app, "native-toast-light")
        app = start(["toast"])
        app.buttons["toast-confirm"].tap()
        XCTAssertTrue(app.staticTexts["native-toast-message"].waitForExistence(timeout: 5))
        capture(app, "native-toast-confirm")
    }

    func testCategoricalBarChartsKeepLongLabelsSinglePointAndLargeText() {
        assertCategoricalCharts("chart-bar")
    }

    func testCategoricalLineChartsKeepLongLabelsSinglePointAndLargeText() {
        assertCategoricalCharts("chart-line")
    }

    /// Both categorical charts render at their fixed height from one point on, while the unstyled
    /// quantitative chart keeps its one-point subtitle; large text keeps every chart reachable.
    private func assertCategoricalCharts(_ fixture: String) {
        for large in [false, true] {
            let app = start(large ? ["surface", fixture, "large"] : ["surface", fixture])
            XCTAssertTrue(app.staticTexts["Messages per day"].waitForExistence(timeout: 10))
            assertChart(app, "Messages per day")
            capture(app, "native-\(fixture)\(large ? "-large-text" : "")")
            let single = app.staticTexts["Single day"]
            for _ in 0..<6 where !(single.exists && single.isHittable) { app.swipeUp() }
            XCTAssertTrue(single.exists)
            assertChart(app, "Single day")
            let legacy = app.staticTexts["Collecting data"]
            for _ in 0..<6 where !(legacy.exists && legacy.isHittable) { app.swipeUp() }
            XCTAssertTrue(legacy.exists, "The unstyled chart keeps its one-point subtitle")
            capture(app, "native-\(fixture)-single\(large ? "-large-text" : "")")
        }
    }

    /// The chart itself carries its title as accessibility label at the fixed 200 pt height.
    private func assertChart(_ app: XCUIApplication, _ title: String) {
        let labelled = app.descendants(matching: .any).matching(NSPredicate(format: "label == %@", title))
        XCTAssertTrue(labelled.allElementsBoundByIndex.contains { abs($0.frame.height - 200) <= 1 }, title)
    }
}

/// Runs inside the test bundle, which compiles NativeGraphView.swift with the contract, so the
/// row-scoped ImageRenderer capture is checked without launching the fixture.
final class NativeGraphCaptureTests: XCTestCase {
    private func graph(placeholder: Bool = false) throws -> NativeSurfaceRow.Graph {
        // A hub and 39 spokes, all within the middle of a 390 x 600 frame.
        let nodes: [[String: Any]] = (0..<40).map { index in
            let user = index == 0
            return ["id": "n\(index)", "label": "Node \(index)", "type": user ? "user" : "concept",
                    "x": user ? 0.0 : Double(index * 37 % 200 - 100), "y": user ? 0.0 : Double(index * 53 % 300 - 150),
                    "z": user ? 0.0 : Double(index * 71 % 400 - 200), "fixed": user]
        }
        let edges: [[String: Any]] = (1..<40).map { ["source": "n0", "target": "n\($0)", "label": $0 % 3 == 0 ? "knows" : ""] }
        var row: [String: Any] = ["id": "graph", "title": "Memory Graph", "kind": "graph", "subtitle": "", "options": [],
            "destructive": false, "enabled": true,
            "graph": ["nodes": placeholder ? [] : nodes, "edges": placeholder ? [] : edges,
                      "highlighted": placeholder ? [] : ["n0", "n3"], "zoom": 1.0, "interactive": !placeholder,
                      "layout": "fill", "placeholder": placeholder, "accent": "#1A2B3C"]]
        if !placeholder { row["value"] = "n0" }
        let snapshot = try NativeSurfaceSnapshot.decode(["version": 1, "revision": 0, "title": "Memory Graph",
            "appearance": "dark", "locale": "en", "direction": "ltr", "loading": false, "failed": false, "empty": "",
            "sections": [["id": "graph", "title": "", "footer": "", "rows": [row]]], "toolbar": [],
            "searchEnabled": false, "searchValue": "", "searchPlaceholder": "", "refreshEnabled": false,
            "error": "Error", "retry": "Retry", "loadingLabel": "Loading"])
        return try XCTUnwrap(snapshot.fillGraphRow?.graph)
    }

    @MainActor
    func testRowCaptureIsPNGWithinSixteenMegapixelsAndSixteenMegabytes() throws {
        let graph = try graph()
        let camera = NativeGraphCamera(zoom: graph.zoom)
        let phone = try XCTUnwrap(NativeGraphCapture.png(graph, camera: camera, size: CGSize(width: 390, height: 600),
                                                         colorScheme: .dark))
        XCTAssertEqual(Array(phone.prefix(8)), [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])
        let image = try XCTUnwrap(UIImage(data: phone)?.cgImage)
        XCTAssertEqual(image.width, 1170, "A phone-sized graph renders at 3x")
        XCTAssertEqual(image.height, 1800)
        XCTAssertGreaterThan(alpha(image, x: image.width / 2, y: image.height / 2), 0, "The user node is drawn at the centre")
        XCTAssertEqual(alpha(image, x: 2, y: 2), 0, "Like the Flutter capture, the background stays transparent")

        for size in [CGSize(width: 4000, height: 9000), CGSize(width: 3333.3, height: 4800.7)] {
            let data = try XCTUnwrap(NativeGraphCapture.png(graph, camera: camera, size: size, colorScheme: .light))
            XCTAssertLessThanOrEqual(data.count, 16 * 1024 * 1024)
            let large = try XCTUnwrap(UIImage(data: data)?.cgImage)
            XCTAssertLessThanOrEqual(large.width * large.height, 16_000_000, "\(size)")
            XCTAssertGreaterThan(large.width * large.height, 15_000_000, "\(size) is scaled down, not dropped")
        }
        XCTAssertNil(NativeGraphCapture.png(try self.graph(placeholder: true), camera: camera,
                                            size: CGSize(width: 390, height: 600), colorScheme: .dark))
        for size in [CGSize.zero, CGSize(width: 390, height: 0), CGSize(width: CGFloat.infinity, height: 10),
                     CGSize(width: CGFloat.nan, height: 10)] {
            XCTAssertNil(NativeGraphCapture.png(graph, camera: camera, size: size, colorScheme: .dark), "\(size)")
        }
    }

    private func alpha(_ image: CGImage, x: Int, y: Int) -> UInt8 {
        var pixel = [UInt8](repeating: 0, count: 4)
        guard let context = CGContext(data: &pixel, width: 1, height: 1, bitsPerComponent: 8, bytesPerRow: 4,
                                      space: CGColorSpaceCreateDeviceRGB(),
                                      bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return 0 }
        context.draw(image, in: CGRect(x: -x, y: y - image.height + 1, width: image.width, height: image.height))
        return pixel[3]
    }
}
