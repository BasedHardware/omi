import XCTest

/// Opt-in runtime probe.  The host WKWebView returns only the allowlisted
/// typed runtime marker through its accessibility identifier; this test keeps
/// the marker as one retained JSON attachment for the Node producer.
final class NativeRuntimeEvidenceUITests: XCTestCase {
  func testNativeRuntimeEvidence() {
    let app = XCUIApplication()
    app.launchEnvironment["OMI_POLISH_RUNTIME_PROBE"] = "1"
    app.launch()
    XCTAssertTrue(app.wait(for: .runningForeground, timeout: 20), "fixture app did not reach foreground")
    let webView = app.webViews.firstMatch
    XCTAssertTrue(webView.waitForExistence(timeout: 20), "fixture exposed no native WKWebView")

    var marker: String?
    for _ in 0..<40 {
      let identifier = webView.identifier
      let value = webView.value as? String ?? ""
      if identifier.hasPrefix("OMI_RUNTIME_JSON_") {
        marker = String(identifier.dropFirst("OMI_RUNTIME_JSON_".count))
        break
      } else if value.hasPrefix("OMI_RUNTIME_JSON_") {
        marker = String(value.dropFirst("OMI_RUNTIME_JSON_".count))
        break
      }
      RunLoop.current.run(until: Date(timeIntervalSinceNow: 0.25))
    }
    guard let encoded = marker else {
      XCTFail("typed native runtime host marker was not observed")
      return
    }
    let normalized = encoded
      .replacingOccurrences(of: "-", with: "+")
      .replacingOccurrences(of: "_", with: "/")
    let padded = normalized + String(repeating: "=", count: (4 - normalized.count % 4) % 4)
    guard let data = Data(base64Encoded: padded),
          let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
          object["schema"] as? String == "omi.native-runtime-marker/v1" else {
      XCTFail("typed native runtime host marker was not observed")
      return
    }
    guard let eventData = try? JSONSerialization.data(withJSONObject: object, options: [.sortedKeys]) else {
      XCTFail("native runtime marker could not be canonicalized")
      return
    }
    let attachment = XCTAttachment(data: eventData, uniformTypeIdentifier: "public.json")
    attachment.name = "OMI_NATIVE_IOS_RUNTIME_JSON"
    attachment.lifetime = .keepAlways
    add(attachment)
    print("OMI_NATIVE_IOS_RUNTIME_JSON:\(eventData.base64EncodedString())")
  }
}
