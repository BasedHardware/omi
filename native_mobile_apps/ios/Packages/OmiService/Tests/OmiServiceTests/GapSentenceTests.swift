@testable import OmiService
import Testing

struct GapSentenceTests {
    let name = GapSentence("My name is ___ and I spend most of my time ___.")
    let nameDE = GapSentence("Ich heiße ___ und verbringe die meiste Zeit mit ___.")

    func heard(_ match: GapSentence.Match) -> [String] {
        match.pieces.compactMap { if case let .word(word, true) = $0 { word } else { nil } }
    }

    @Test func blanksAndWordsAreReadFromTheTemplate() {
        #expect(name.parts.count == 12)
        #expect(name.parts[3] == .blank)
        #expect(name.parts.last == .blank)
        #expect(GapSentence.free.parts == [.blank])
    }

    @Test func blanksFillLiveAsTheSentenceIsSpoken() {
        let start = name.match("My name is")
        #expect(heard(start) == ["My", "name", "is"])
        #expect(start.blanks == ["", ""])
        #expect(!start.isComplete)

        let middle = name.match("My name is Ada and I")
        #expect(middle.blanks == ["Ada", ""])
        #expect(heard(middle).contains("and"))

        let done = name.match("My name is Ada, and I spend most of my time building apps.")
        #expect(done.blanks == ["Ada", "building apps"])
        #expect(done.fixedHeard == done.fixedTotal)
        #expect(done.isComplete)
        #expect(done.progress == 1)
    }

    @Test func aBlankNeedsAWord() {
        let match = name.match("My name is Ada and I spend most of my time")
        #expect(match.blanks == ["Ada", ""])
        #expect(!match.isComplete)
        #expect(match.progress > 0.8 && match.progress < 1)
    }

    @Test func misheardAndMissingWordsStillCount() {
        // "nam" for "name", "of" dropped, "Leo" as the name: fuzzy and tolerant.
        let match = name.match("my nam is Leo and I spend most my time coding")
        #expect(match.blanks == ["Leo", "coding"])
        #expect(match.isComplete)
    }

    @Test func aCloseParaphraseStillCounts() {
        let match = GapSentence("In my free time I love ___.").match("When I have free time, I love cooking with friends.")
        #expect(match.blanks == ["cooking with friends"])
        #expect(match.isComplete)
    }

    @Test func paraphrasingTooMuchIsNotTheSentence() {
        let match = name.match("Ada here, I code a lot")
        #expect(!match.isComplete)
    }

    @Test func fillerBeforeTheSentenceIsIgnored() {
        let match = GapSentence("Right now I'm working on ___.").match("Okay so right now I am working on a new app")
        #expect(match.blanks == ["a new app"])
        #expect(match.isComplete)
    }

    @Test func germanWithUmlautsSharpSAndOtherEndings() {
        let match = nameDE.match("Ich heisse Ada und verbringe die meiste Zeit mit Programmieren")
        #expect(match.blanks == ["Ada", "Programmieren"])
        #expect(match.isComplete)
        let work = GapSentence("Gerade arbeite ich an ___.").match("gerade arbeiten ich an einer neuen App")
        #expect(work.blanks == ["einer neuen App"])
        #expect(work.isComplete)
    }

    @Test func theFreeSentenceWantsAFewWords() {
        #expect(!GapSentence.free.match("Hello").isComplete)
        #expect(GapSentence.free.match("Today I walked to work").isComplete)
    }

    @Test func wordsAreComparedForgivingly() {
        #expect(GapSentence.similar("arbeite", "arbeiten"))
        #expect(GapSentence.similar("heisse", "heise"))
        #expect(!GapSentence.similar("in", "im"))
        #expect(!GapSentence.similar("time", "name"))
        #expect(GapSentence.tokens("I'm") == ["i", "am"])
        #expect(GapSentence.tokens("Heiße,") == ["heisse"])
    }
}

struct VoiceProgressTests {
    @Test func finishedSentencesAreFullStepsTheCurrentOneNeverCompletesItsStep() {
        #expect(VoiceProgress.fraction(completed: 0, total: 3, current: 0) == 0)
        #expect(VoiceProgress.fraction(completed: 1, total: 3, current: 0) == 1.0 / 3)
        // A sentence spoken in full but not yet finished stops short of the next step.
        #expect(VoiceProgress.fraction(completed: 1, total: 3, current: 1) < 2.0 / 3)
        #expect(VoiceProgress.fraction(completed: 3, total: 3, current: 0) == 1)
    }
}
