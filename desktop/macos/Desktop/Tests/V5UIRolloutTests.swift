import Foundation
import Testing

@testable import Omi_Computer

struct V5UIRolloutTests {
  @Test func localOverrideControlsDevelopmentMount() throws {
    let key = DefaultsKey.v5UILocalOverride
    let fixture = IsolatedTestDefaults()
    let defaults = try fixture.makeDefaults()

    defaults.set(false, forKey: key)
    #if DEBUG
      #expect(!V5UIRollout.localOverrideEnabled(in: defaults))
      defaults.set(true, forKey: key)
      #expect(V5UIRollout.localOverrideEnabled(in: defaults))
    #else
      defaults.set(true, forKey: key)
      #expect(!V5UIRollout.localOverrideEnabled(in: defaults))
    #endif
  }
}
