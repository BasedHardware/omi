@testable import Omi_Computer

// Compile-only aliases for pre-scenario tests. These are not Step cases and do not enter CaseIterable.
extension SBOnboardingModel.Step {
  static let name = Self.hello
  static let howHeard = Self.hello
  static let language = Self.hello
  static let role = Self.hello
  static let mic = Self.talk
  static let systemAudio = Self.talk
  static let screen = Self.see
  static let files = Self.see
  static let accessibility = Self.ready
  static let automation = Self.card
  static let notifications = Self.card
  static let shortcutOpen = Self.talk
  static let shortcutTalk = Self.talk
  static let screenDemo = Self.talk
  static let agents = Self.write
  static let context = Self.write
  static let capture = Self.ready
  static let referral = Self.ready
}
