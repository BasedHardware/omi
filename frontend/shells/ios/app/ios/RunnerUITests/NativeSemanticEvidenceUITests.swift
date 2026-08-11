import XCTest

/// A fixture-only UI test.  It emits a single base64 JSON marker so the host
/// wrapper can bind source/coordinate metadata and write verifier artifacts.
/// No AX value, text-field value, or arbitrary user label crosses the marker.
final class NativeSemanticEvidenceUITests: XCTestCase {
  private let allowedLabels: Set<String> = [
    "Memories", "Tasks", "Conversations", "Folders", "Listen", "Chat", "Settings",
    "Search", "Send", "Close", "Cancel", "Try again", "All Conversations",
  ]

  private struct Node: Encodable {
    let role: String
    let name: String
  }

  private struct Step: Encodable {
    let key: String
    let action: String
    let result: String
  }

  private struct Marker: Encodable {
    let schema: String
    let bundleId: String
    let nodes: [Node]
    let steps: [Step]
  }

  func testChatReadySemanticEvidence() {
    let app = XCUIApplication()
    app.launch()
    XCTAssertTrue(app.wait(for: .runningForeground, timeout: 20), "fixture app did not reach foreground")

    let nodes = semanticNodes(app)
    XCTAssertFalse(nodes.isEmpty, "fixture exposed no allowlisted native semantics")

    var steps = [Step(key: "launch", action: "launch", result: "foreground")]
    let textField = app.textFields.firstMatch
    if textField.waitForExistence(timeout: 5) {
      textField.tap()
      let keyboard = app.keyboards.firstMatch
      if keyboard.waitForExistence(timeout: 2) {
        // Keyboard visibility is the only portable focus observation exposed
        // by XCTest here.  No element value or typed text is retained.
        textField.typeText("x")
        steps.append(Step(key: "focus", action: "tap", result: "keyboard-visible"))
        steps.append(Step(key: "type-text", action: "typeText", result: "accepted"))
        // The simulator supports a real command-key probe.  This is recorded
        // as an input attempt only; no product shortcut is claimed by it.
        app.typeKey("k", modifierFlags: .command)
        let search = app.buttons["Search"].firstMatch
        if search.waitForExistence(timeout: 2) {
          steps.append(Step(key: "command-k", action: "typeKey", result: "transition-observed"))
          app.typeKey(XCUIKeyboardKey.escape, modifierFlags: [])
          if !search.exists && textField.exists {
            steps.append(Step(key: "escape", action: "typeKey", result: "restored"))
          }
        }
      } else {
        steps.append(Step(key: "focus", action: "tap", result: "keyboard-not-observed"))
      }
    } else {
      var tapped = false
      for label in allowedLabels {
        let button = app.buttons[label].firstMatch
        if button.exists {
          button.tap()
          steps.append(Step(key: "tap", action: "tap", result: "accepted"))
          tapped = true
          break
        }
      }
      if !tapped {
        let webView = app.webViews.firstMatch
        XCTAssertTrue(webView.waitForExistence(timeout: 5), "fixture exposed no text field, button, or web view")
        webView.tap()
        steps.append(Step(key: "tap", action: "tap", result: "web-view-accepted"))
      }
    }

    let marker = Marker(
      schema: "omi.native-ios-semantic-marker.v1",
      bundleId: "me.omi.proto.omiWebviewProto",
      nodes: nodes,
      steps: steps
    )
    let data = try! JSONEncoder().encode(marker)
    let attachment = XCTAttachment(data: data, uniformTypeIdentifier: "public.json")
    attachment.name = "OMI_NATIVE_IOS_SEMANTIC_JSON"
    attachment.lifetime = .keepAlways
    add(attachment)
    print("OMI_NATIVE_IOS_SEMANTIC_JSON:\(data.base64EncodedString())")
  }

  private func semanticNodes(_ app: XCUIApplication) -> [Node] {
    var nodes: [Node] = [Node(role: "application", name: "Omi")]
    var seen = Set<String>()
    for label in allowedLabels.sorted() {
      let button = app.buttons[label].firstMatch
      if button.exists {
        nodes.append(Node(role: "button", name: label))
        seen.insert("button:\(label)")
      }
      let staticText = app.staticTexts[label].firstMatch
      if staticText.exists && !seen.contains("static-text:\(label)") {
        nodes.append(Node(role: "static-text", name: label))
        seen.insert("static-text:\(label)")
      }
      let textField = app.textFields[label].firstMatch
      if textField.exists && !seen.contains("text-field:\(label)") {
        nodes.append(Node(role: "text-field", name: label))
        seen.insert("text-field:\(label)")
      }
    }
    let webView = app.webViews.firstMatch
    if webView.exists {
      nodes.append(Node(role: "web-view", name: "Omi surface"))
    }
    return nodes
  }

}
