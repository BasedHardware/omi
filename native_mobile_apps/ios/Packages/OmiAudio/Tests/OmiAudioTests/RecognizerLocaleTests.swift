import Foundation
@testable import OmiAudio
import Testing

struct RecognizerLocaleTests {
    let supported: Set<Locale> = ["de-AT", "de-CH", "de-DE", "en-GB", "en-US", "fr-FR"].map(Locale.init(identifier:)).reduce(into: []) {
        $0.insert($1)
    }

    func locale(_ language: String, region: String?) -> String? {
        OnDeviceTranscriber.locale(for: language, supported: supported, region: region)?.identifier
    }

    @Test func theUsersLanguageNotTheIPhones() {
        // A German iPhone, an English speaker: English, in the iPhone's region when it has one.
        #expect(locale("en", region: "DE") == "en-US")
        #expect(locale("en", region: "GB") == "en-GB")
        #expect(locale("de", region: "CH") == "de-CH")
        #expect(locale("de", region: "US") == "de-DE")
        #expect(locale("en-GB", region: "US") == "en-GB")
        #expect(locale("de_AT", region: nil) == "de-AT")
    }

    @Test func noRecognizerForTheLanguageIsNil() {
        #expect(locale("ja", region: "JP") == nil)
        #expect(locale("multi", region: "DE") == nil)
    }
}

/// Apple's recognizer starting over after a pause must not replace what was said before it.
struct UtterancePartsTests {
    @Test func revisionsStayInOnePart() {
        var parts = UtteranceParts()
        #expect(parts.next("You", endsUtterance: false) == 0)
        #expect(parts.next("Hello can you", endsUtterance: false) == 0)
        #expect(parts.next("Hello can you hear me", endsUtterance: false) == 0)
        #expect(parts.next("Hello, can you hear me?", endsUtterance: false) == 0)
    }

    @Test func aRestartAfterAPauseIsANewPart() {
        var parts = UtteranceParts()
        _ = parts.next("My name is Alex", endsUtterance: false)
        _ = parts.next("My name is Alex and I spend most of my time doing work", endsUtterance: false)
        // iOS starts the line over with only the new words.
        #expect(parts.next("Right", endsUtterance: false) == 1)
        #expect(parts.next("Right now I'm working", endsUtterance: false) == 1)
        #expect(parts.next("Right now I'm working on something interesting", endsUtterance: false) == 1)
    }

    @Test func theEndOfAnUtteranceStartsTheNextPart() {
        var parts = UtteranceParts()
        _ = parts.next("Hello", endsUtterance: false)
        #expect(parts.next("Hello there", endsUtterance: true) == 0)
        // Even a longer line after the marked end is new.
        #expect(parts.next("In my free time I love to play football", endsUtterance: false) == 1)
    }
}
