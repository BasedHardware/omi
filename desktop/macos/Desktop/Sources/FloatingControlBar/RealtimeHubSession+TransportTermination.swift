import Foundation

extension RealtimeHubSession {
  func stopAndWait() async {
    let handles: (URLSessionWebSocketTask?, RealtimeRawWebSocketTransport?) = await withCheckedContinuation {
      continuation in
      q.async { [weak self] in
        guard let self else {
          continuation.resume(returning: (nil, nil))
          return
        }
        let handles = (self.task, self.rawWS)
        self.beginStopOnQueue()
        continuation.resume(returning: handles)
      }
    }
    await waitForRawTransportTerminal(handles.1)
    await waitForURLTaskTerminal(handles.0)
    let handlesBox = SessionCallbackBox(handles)
    await withCheckedContinuation { continuation in
      q.async { [weak self] in
        let handles = handlesBox.value
        if let urlTask = handles.0, self?.task === urlTask {
          self?.task = nil
        }
        if let rawTransport = handles.1, self?.rawWS === rawTransport {
          self?.rawWS = nil
        }
        continuation.resume()
      }
    }
  }

  private func waitForRawTransportTerminal(_ transport: RealtimeRawWebSocketTransport?) async {
    guard let transport else { return }
    await transport.closeAndWait()
  }

  private func waitForURLTaskTerminal(_ urlTask: URLSessionWebSocketTask?) async {
    guard let urlTask else { return }
    await withCheckedContinuation { continuation in
      q.async { [weak self] in
        guard let self else {
          continuation.resume()
          return
        }
        let taskID = urlTask.taskIdentifier
        if self.completedURLTaskIDs.contains(taskID) || urlTask.state == .completed {
          continuation.resume()
          return
        }
        self.urlTaskTerminalWaiters[taskID, default: []].append(continuation)
        urlTask.cancel(with: .goingAway, reason: nil)
      }
    }
  }
}
