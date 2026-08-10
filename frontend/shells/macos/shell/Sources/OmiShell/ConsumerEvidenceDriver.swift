import AppKit
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
  private var pollCount = 0
  private var listenStartRequested = false
  private(set) var failed = false

  init(collector: ConsumerEvidenceCollector, baseURL: URL) {
    self.collector = collector
    self.baseURL = baseURL
  }

  func start(with controller: WebViewController) {
    self.controller = controller
    loadCurrentRoute()
  }

  func pageDidFinish() {
    guard !failed, routeIndex < ConsumerEvidenceRoute.allCases.count else { return }
    pollCount = 0
    listenStartRequested = false
    schedulePoll()
  }

  func teardown() {
    pollTimer?.invalidate()
    pollTimer = nil
    collector.teardown()
  }

  private func loadCurrentRoute() {
    guard let controller, routeIndex < ConsumerEvidenceRoute.allCases.count else { return }
    let route = ConsumerEvidenceRoute.allCases[routeIndex]
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
    controller.load(url)
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
    pollCount += 1
    if pollCount > 200 {
      fail("timed out waiting for rendered semantic observation")
      return
    }
    let expected = ConsumerEvidenceRoute.allCases[routeIndex]
    if expected == .listen && !listenStartRequested {
      controller.webView.evaluateJavaScript(
        Self.startListenScript
      ) { [weak self] value, _ in
        MainActor.assumeIsolated {
          guard let self, !self.failed else { return }
          self.listenStartRequested = value as? Bool == true
          self.schedulePoll()
        }
      }
      return
    }
    controller.webView.evaluateJavaScript(Self.renderedObservationScript) { [weak self] value, error in
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
          self.routeIndex += 1
          if self.routeIndex == ConsumerEvidenceRoute.allCases.count {
            try self.collector.finish()
            FileHandle.standardError.write(
              Data("CONSUMER-EVIDENCE: wrote seven rendered routes\n".utf8))
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
    teardown()
    FileHandle.standardError.write(Data("CONSUMER-EVIDENCE: FAIL \(reason)\n".utf8))
    if ProcessInfo.processInfo.environment["OMI_CONSUMER_EVIDENCE_EXIT"] == "1" {
      Darwin.exit(1)
    }
  }

  /// Reads only the bounded semantic attributes on the currently rendered
  /// production root. It never accepts launch intent, arbitrary DOM text, a
  /// JavaScript-provided hash, or a JavaScript-provided success boolean.
  private static let renderedObservationScript = #"""
    (() => {
      const e = document.querySelector("main[data-production-shell='true']");
      if (!e || e.dataset.surfaceState !== 'ready' || e.dataset.qaFixture !== 'none') return null;
      const route = e.dataset.route;
      const semantic = e.dataset.consumerSemantic;
      if (!['memories','tasks','conversations','folders','listen','chat','settings'].includes(route)) return null;
      if (typeof semantic !== 'string' || semantic.trim() === '' || new TextEncoder().encode(semantic).length > 256) return null;
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
      if (!button) return false;
      button.click();
      return true;
    })()
    """#
}
