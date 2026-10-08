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

    func start(_ arguments: [String] = []) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = arguments
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
        let message = app.staticTexts["native-toast-message"]
        XCTAssertTrue(message.waitForExistence(timeout: 5))
        message.swipeDown()
        waitForLabel(app.staticTexts["toast-outcomes"], "1:swiped")
        XCTAssertTrue(waitForDisappearance(app.otherElements["native-toast"]))
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
}
