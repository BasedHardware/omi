import Foundation

struct AppSessionStart: Equatable, Sendable {
  enum Kind: String, Sendable {
    case coldStart = "cold_start"
    case foregroundResume = "foreground_resume"
  }

  let id: String
  let kind: Kind
}

final class AppSessionLifecycle {
  private let makeID: () -> String
  private var launched = false
  private var inactiveSinceLaunch = false

  init(makeID: @escaping () -> String = { UUID().uuidString }) {
    self.makeID = makeID
  }

  func appLaunched() -> AppSessionStart? {
    guard !launched else { return nil }
    launched = true
    return AppSessionStart(id: makeID(), kind: .coldStart)
  }

  func appResignedActive() {
    guard launched else { return }
    inactiveSinceLaunch = true
  }

  func appBecameActive() -> AppSessionStart? {
    guard launched, inactiveSinceLaunch else { return nil }
    inactiveSinceLaunch = false
    return AppSessionStart(id: makeID(), kind: .foregroundResume)
  }
}
