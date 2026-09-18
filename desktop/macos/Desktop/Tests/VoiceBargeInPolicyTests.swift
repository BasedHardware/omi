import XCTest

@testable import Omi_Computer

final class VoiceBargeInPolicyTests: XCTestCase {

  func testUserSpeechInterruptsActivePlayback() {
    let result = VoiceBargeInPolicy.shouldInterrupt(
      isUser: true,
      speaker: 0,
      text: "Wait, stop that",
      isSpeaking: true
    )
    XCTAssertTrue(result)
  }

  func testUserSpeechNoopWhenNotPlaying() {
    let result = VoiceBargeInPolicy.shouldInterrupt(
      isUser: true,
      speaker: 0,
      text: "Hello there",
      isSpeaking: false
    )
    XCTAssertFalse(result)
  }

  func testOtherSpeakerSpeechDoesNotInterrupt() {
    let result = VoiceBargeInPolicy.shouldInterrupt(
      isUser: false,
      speaker: 1,
      text: "Sure, let's look at the next slide",
      isSpeaking: true
    )
    XCTAssertFalse(result, "Other speakers on a call should not interrupt the user's assistant output")
  }

  func testEmptyOrWhitespaceSpeechDoesNotInterrupt() {
    let emptyResult = VoiceBargeInPolicy.shouldInterrupt(
      isUser: true,
      speaker: 0,
      text: "",
      isSpeaking: true
    )
    XCTAssertFalse(emptyResult)

    let whitespaceResult = VoiceBargeInPolicy.shouldInterrupt(
      isUser: true,
      speaker: 0,
      text: "   \n\t  ",
      isSpeaking: true
    )
    XCTAssertFalse(whitespaceResult)
  }

  func testSpeakerZeroTreatedAsUserEvenIfIsUserFlagFalse() {
    let result = VoiceBargeInPolicy.shouldInterrupt(
      isUser: false,
      speaker: 0,
      text: "Cancel that order",
      isSpeaking: true
    )
    XCTAssertTrue(result, "Speaker 0 is the primary local user and must be allowed to interrupt")
  }
}
