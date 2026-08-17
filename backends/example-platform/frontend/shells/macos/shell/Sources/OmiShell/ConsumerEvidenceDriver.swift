import AppKit
import CoreFoundation
import Darwin
import Foundation
import WebKit

@MainActor
final class ConsumerEvidenceDriver {
  private let collector: ConsumerEvidenceCollector
  private let baseURL: URL
  private weak var controller: WebViewController?
  private var routeIndex = 0
  private var pollTimer: Timer?
  private var routeDriveState = ConsumerEvidenceRouteDriveState()
  private(set) var failed = false
  private var failFinished = false

  init(collector: ConsumerEvidenceCollector, baseURL: URL) {
    self.collector = collector
    self.baseURL = baseURL
  }

  func start(with controller: WebViewController) {
    self.controller = controller
    loadCurrentRoute()
  }

  func pageDidFinish(_ navigation: WKNavigation?) {
    guard !failed, routeIndex < ConsumerEvidenceRoute.allCases.count,
      routeDriveState.acceptFinished(navigation)
    else { return }
    schedulePoll()
  }

  func pageDidFail(_ navigation: WKNavigation?, error: Error) {
    let route = currentRouteName()
    fail("navigation failed on \(route): \(error.localizedDescription)")
  }

  func contentProcessDidTerminate() {
    fail("WKWebView content process terminated on \(currentRouteName())")
  }

  func teardown() {
    pollTimer?.invalidate()
    pollTimer = nil
    collector.teardown()
  }

  private func currentRouteName() -> String {
    guard routeIndex < ConsumerEvidenceRoute.allCases.count else { return "complete" }
    return ConsumerEvidenceRoute.allCases[routeIndex].rawValue
  }

  private func timeoutReason() -> String {
    let route = currentRouteName()
    let polls = routeDriveState.pollCount
    guard routeIndex < ConsumerEvidenceRoute.allCases.count else {
      return
        "timed out waiting for rendered semantic observation on \(route) (wait=rendered-observation selectorMatched=n/a clickIssued=n/a latchedAtPoll=none pollsSinceLatch=none pollCount=\(polls))"
    }
    switch ConsumerEvidenceRoute.allCases[routeIndex] {
    case .listen:
      if let latched = routeDriveState.listenClickLatchPoll {
        return
          "timed out waiting for rendered transcript on listen (wait=transcript-after-click selectorMatched=true clickIssued=true latchedAtPoll=\(latched) pollsSinceLatch=\(polls - latched) pollCount=\(polls))"
      }
      return
        "timed out waiting for start-listen click on listen (wait=start-listen-selector selectorMatched=false clickIssued=false latchedAtPoll=none pollsSinceLatch=none pollCount=\(polls))"
    case .chat:
      if routeDriveState.chatAdmissionBaseline == nil {
        return
          "timed out waiting for chat composer on chat (wait=chat-author selectorMatched=false clickIssued=false latchedAtPoll=none pollsSinceLatch=none pollCount=\(polls))"
      }
      if let latched = routeDriveState.chatSubmitLatchPoll {
        return
          "timed out waiting for chat admission on chat (wait=chat-admission-after-submit selectorMatched=true clickIssued=true latchedAtPoll=\(latched) pollsSinceLatch=\(polls - latched) pollCount=\(polls))"
      }
      return
        "timed out waiting for chat submit on chat (wait=chat-submit-selector selectorMatched=false clickIssued=false latchedAtPoll=none pollsSinceLatch=none pollCount=\(polls))"
    case .memories, .tasks, .conversations, .folders, .settings, .screen:
      return
        "timed out waiting for rendered semantic observation on \(route) (wait=rendered-observation selectorMatched=n/a clickIssued=n/a latchedAtPoll=none pollsSinceLatch=none pollCount=\(polls))"
    }
  }

  private static func evidenceLog(_ line: String) {
    FileHandle.standardError.write(Data("CONSUMER-EVIDENCE: \(line)\n".utf8))
  }

  /// WKWebView boxes JS booleans as NSNumber. `as? Bool` is the historical
  /// latch; this keeps that answer and also accepts the boxed form so the log
  /// and the latch describe the same value.
  private static func jsFlag(_ value: Any?) -> Bool {
    if let flag = value as? Bool { return flag }
    if let number = value as? NSNumber { return number.boolValue }
    return false
  }

  private static func describeJSResult(_ value: Any?, error: Error?) -> String {
    let errorText: String
    if let error {
      let raw = error.localizedDescription.replacingOccurrences(of: "\n", with: " ")
      errorText = raw.count <= 160 ? raw : String(raw.prefix(160))
    } else {
      errorText = "none"
    }
    let valueText: String
    switch value {
    case nil, is NSNull:
      valueText = "nil"
    case let flag as Bool:
      valueText = flag ? "true" : "false"
    case let number as NSNumber:
      if CFGetTypeID(number) == CFBooleanGetTypeID() {
        valueText = number.boolValue ? "true" : "false"
      } else {
        valueText = number.stringValue
      }
    case let text as String:
      let compact = text.replacingOccurrences(of: "\n", with: " ")
      valueText = compact.count <= 80 ? compact : String(compact.prefix(80))
    default:
      valueText = String(describing: type(of: value as Any))
    }
    return "value=\(valueText) error=\(errorText)"
  }

  private func loadCurrentRoute() {
    guard let controller, routeIndex < ConsumerEvidenceRoute.allCases.count else { return }
    let route = ConsumerEvidenceRoute.allCases[routeIndex]
    FileHandle.standardError.write(Data("CONSUMER-EVIDENCE: begin \(route.rawValue)\n".utf8))
    guard var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false) else {
      fail("cannot construct evidence route URL")
      return
    }
    var items = (components.queryItems ?? []).filter {
      !["route", "qa", "rig", "state"].contains($0.name)
    }
    items.append(URLQueryItem(name: "route", value: route.rawValue))
    components.queryItems = items
    guard let url = components.url else {
      fail("cannot construct evidence route URL")
      return
    }
    guard let navigation = controller.load(url), routeDriveState.begin(navigation) else {
      fail("cannot start evidence route navigation")
      return
    }
    pollTimer?.invalidate()
    pollTimer = nil
  }

  private func schedulePoll() {
    pollTimer?.invalidate()
    pollTimer = Timer.scheduledTimer(withTimeInterval: 0.15, repeats: false) {
      [weak self] _ in
      MainActor.assumeIsolated { self?.pollRenderedObservation() }
    }
  }

  private func pollRenderedObservation() {
    guard let controller, routeIndex < ConsumerEvidenceRoute.allCases.count else { return }
    routeDriveState.pollCount += 1
    if routeDriveState.pollCount > 200 {
      fail(timeoutReason())
      return
    }
    let expected = ConsumerEvidenceRoute.allCases[routeIndex]
    let poll = routeDriveState.pollCount
    if expected == .listen && !routeDriveState.listenStartRequested {
      controller.webView.evaluateJavaScript(
        Self.startListenScript
      ) { [weak self] value, error in
        MainActor.assumeIsolated {
          guard let self, !self.failed else { return }
          Self.evidenceLog(
            "listen-click poll=\(poll) \(Self.describeJSResult(value, error: error))")
          let clicked = Self.jsFlag(value)
          self.routeDriveState.listenStartRequested = clicked
          if clicked { self.routeDriveState.listenClickLatchPoll = poll }
          self.schedulePoll()
        }
      }
      return
    }
    if expected == .chat && routeDriveState.chatAdmissionBaseline == nil {
      controller.webView.evaluateJavaScript(Self.authorChatScript) { [weak self] value, error in
        MainActor.assumeIsolated {
          guard let self, !self.failed else { return }
          Self.evidenceLog(
            "chat-author poll=\(poll) \(Self.describeJSResult(value, error: error))")
          if let number = value as? NSNumber {
            self.routeDriveState.chatAdmissionBaseline = number.intValue
          }
          self.schedulePoll()
        }
      }
      return
    }
    if expected == .chat && !routeDriveState.chatSubmitted {
      controller.webView.evaluateJavaScript(Self.submitChatScript) { [weak self] value, error in
        MainActor.assumeIsolated {
          guard let self, !self.failed else { return }
          Self.evidenceLog(
            "chat-submit poll=\(poll) \(Self.describeJSResult(value, error: error))")
          let submitted = Self.jsFlag(value)
          self.routeDriveState.chatSubmitted = submitted
          if submitted { self.routeDriveState.chatSubmitLatchPoll = poll }
          self.schedulePoll()
        }
      }
      return
    }
    let observationScript = expected == .chat
      ? Self.renderedChatObservationScript(after: routeDriveState.chatAdmissionBaseline ?? Int.max)
      : Self.renderedObservationScript
    controller.webView.evaluateJavaScript(observationScript) { [weak self] value, error in
      MainActor.assumeIsolated {
        guard let self, !self.failed else { return }
        if error != nil || value is NSNull || value == nil {
          self.schedulePoll()
          return
        }
        guard let json = value as? String, let data = json.data(using: .utf8) else {
          self.fail("rendered observation was not JSON")
          return
        }
        do {
          let observation = try RenderedConsumerObservation.decodeRenderedJSON(data)
          try self.collector.accept(observation, expected: expected)
          FileHandle.standardError.write(
            Data("CONSUMER-EVIDENCE: accepted \(expected.rawValue)\n".utf8))
          self.routeIndex += 1
          if self.routeIndex == ConsumerEvidenceRoute.allCases.count {
            try self.collector.finish()
            FileHandle.standardError.write(
              Data("CONSUMER-EVIDENCE: wrote eight rendered routes\n".utf8))
            if ProcessInfo.processInfo.environment["OMI_CONSUMER_EVIDENCE_EXIT"] == "1" {
              NSApp.terminate(nil)
            }
          } else {
            self.loadCurrentRoute()
          }
        } catch {
          self.fail("\(error)")
        }
      }
    }
  }

  private func fail(_ reason: String) {
    guard !failed else { return }
    failed = true
    pollTimer?.invalidate()
    pollTimer = nil
    routeDriveState.failCurrentRoute()
    let route = currentRouteName()
    FileHandle.standardError.write(Data("CONSUMER-EVIDENCE: FAIL \(reason)\n".utf8))
    let finish: () -> Void = { [weak self] in
      guard let self, !self.failFinished else { return }
      self.failFinished = true
      self.teardown()
      FileHandle.standardError.synchronizeFile()
      if ProcessInfo.processInfo.environment["OMI_CONSUMER_EVIDENCE_EXIT"] == "1" {
        Darwin.exit(1)
      }
    }
    guard let controller else {
      finish()
      return
    }
    controller.webView.evaluateJavaScript(Self.abortSnapshotScript) { value, error in
      MainActor.assumeIsolated {
        let snapshot = value as? String ?? "unavailable"
        let jsError = error.map { $0.localizedDescription } ?? "none"
        FileHandle.standardError.write(
          Data("CONSUMER-EVIDENCE: abort-at \(route) snapshot=\(snapshot) jsError=\(jsError)\n".utf8)
        )
        finish()
      }
    }
    DispatchQueue.main.asyncAfter(deadline: .now() + 1) { finish() }
  }

  /// Bounded DOM snapshot for a named abort. Dataset flags only — never inner
  /// text, tokens, or a JavaScript-provided success boolean.
  private static let abortSnapshotScript = #"""
    (() => {
      const e = document.querySelector("main[data-production-shell='true']");
      if (!e) return JSON.stringify({productionShell:false});
      const button = e.querySelector("[data-consumer-action='start-listen']");
      return JSON.stringify({
        productionShell: true,
        route: e.dataset.route || null,
        surfaceState: e.dataset.surfaceState || null,
        qaFixture: e.dataset.qaFixture || null,
        captureKind: e.dataset.captureKind || null,
        semantic: e.dataset.consumerSemantic || null,
        transcriptPresent: e.dataset.consumerTranscript !== undefined,
        startListenPresent: Boolean(button),
        startListenDisabled: button ? Boolean(button.disabled) : null,
        bridge: e.dataset.bridge || null,
        frameTotal: e.dataset.frameTotal || null,
        frameImage: e.dataset.frameImage || null
      });
    })()
    """#

  /// Reads only the bounded semantic attributes on the currently rendered
  /// production root. It never accepts launch intent, arbitrary DOM text, a
  /// JavaScript-provided hash, or a JavaScript-provided success boolean.
  private static let renderedObservationScript = #"""
    (() => {
      const e = document.querySelector("main[data-production-shell='true']");
      if (!e || e.dataset.surfaceState !== 'ready' || e.dataset.qaFixture !== 'none') return null;
      const route = e.dataset.route;
      const semantic = e.dataset.consumerSemantic;
      if (!['memories','tasks','conversations','folders','listen','chat','settings','screen'].includes(route)) return null;
      if (typeof semantic !== 'string' || semantic.trim() === '' || new TextEncoder().encode(semantic).length > 256) return null;
      if (route === 'screen') {
        const frames = Number(e.dataset.frameTotal);
        const image = e.dataset.frameImage;
        if (!Number.isSafeInteger(frames) || frames < 0) return null;
        if (frames > 0 && image !== 'ready' && !(image === 'unavailable' && e.dataset.bridge === 'absent')) return null;
      }
      if (route === 'listen') {
        const transcript = e.dataset.consumerTranscript;
        if (typeof transcript !== 'string' || transcript.trim() === '' || new TextEncoder().encode(transcript).length > 1024) return null;
        return JSON.stringify({route, state:'ready', semantic, transcript});
      }
      if (e.dataset.consumerTranscript !== undefined) return null;
      return JSON.stringify({route, state:'ready', semantic});
    })()
    """#

  private static let startListenScript = #"""
    (() => {
      const button = document.querySelector("main[data-production-shell='true'][data-route='listen'][data-surface-state='ready'] [data-consumer-action='start-listen']");
      if (!button || button.disabled) return false;
      button.click();
      return true;
    })()
    """#

  /// The message is fixed and bounded in native source. The baseline comes
  /// from the rendered Chat root, never from launcher intent or a dispatch
  /// counter. React's native value setter is used so the production controlled
  /// composer receives the same input transition as a person typing.
  private static let authorChatScript = #"""
    (() => {
      const root = document.querySelector("main[data-production-shell='true'][data-route='chat'][data-surface-state='ready'][data-qa-fixture='none']");
      if (!root) return null;
      const baseline = Number(root.dataset.consumerChatAdmissionCount);
      const draft = root.querySelector('textarea.chat-draft');
      if (!Number.isSafeInteger(baseline) || baseline < 0 || !draft) return null;
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set;
      if (!setter) return null;
      setter.call(draft, 'C3b3 deterministic synthetic Chat evidence.');
      draft.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText'}));
      return baseline;
    })()
    """#

  private static let submitChatScript = #"""
    (() => {
      const root = document.querySelector("main[data-production-shell='true'][data-route='chat'][data-surface-state='ready'][data-qa-fixture='none']");
      const button = root?.querySelector('button.chat-send');
      if (!button || button.disabled) return false;
      button.click();
      return true;
    })()
    """#

  private static func renderedChatObservationScript(after baseline: Int) -> String {
    #"""
    (() => {
      const e = document.querySelector("main[data-production-shell='true'][data-route='chat']");
      if (!e || e.dataset.surfaceState !== 'ready' || e.dataset.qaFixture !== 'none') return null;
      const admitted = Number(e.dataset.consumerChatAdmissionCount);
      if (!Number.isSafeInteger(admitted) || admitted <= \#(baseline)) return null;
      const semantic = e.dataset.consumerSemantic;
      if (typeof semantic !== 'string' || semantic.trim() === '' || new TextEncoder().encode(semantic).length > 256) return null;
      if (e.dataset.consumerTranscript !== undefined) return null;
      return JSON.stringify({route:'chat', state:'ready', semantic});
    })()
    """#
  }
}
