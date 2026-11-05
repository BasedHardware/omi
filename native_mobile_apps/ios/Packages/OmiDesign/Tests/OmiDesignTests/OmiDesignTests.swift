@testable import OmiDesign
import Testing

struct StringsTests {
    @Test func missingKeyFallsBackToKey() {
        #expect(L("definitely_not_a_key") == "definitely_not_a_key")
    }
}
