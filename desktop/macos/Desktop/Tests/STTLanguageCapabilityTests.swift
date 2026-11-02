import FluidAudio
import XCTest

@testable import Omi_Computer

final class STTLanguageCapabilityTests: XCTestCase {
  private func single(_ code: String) -> STTLanguageCapability.Selection {
    STTLanguageCapability.Selection(effective: code, primary: code)
  }

  private func autoDetect(primary: String) -> STTLanguageCapability.Selection {
    STTLanguageCapability.Selection(effective: STTLanguageCapability.autoDetect, primary: primary)
  }

  private func resolve(
    _ language: STTLanguageCapability.Selection,
    source: Omi_Computer.AudioSource = .microphone,
    appleSilicon: Bool = true,
    preferLocalOnBasic: Bool = false
  ) -> STTSessionState.ResolvedMode {
    STTSessionState().resolveMode(
      audioSource: source, isAppleSilicon: appleSilicon, debugForceCloud: false,
      preferLocalOnBasic: preferLocalOnBasic, language: language)
  }

  // MARK: - Model table

  func testEnglishUsesTheEnglishOnlyModel() {
    XCTAssertEqual(single("en").onDeviceModel, .englishV2)
    XCTAssertEqual(single("en-GB").onDeviceModel, .englishV2)
    XCTAssertEqual(LocalTranscriptionService.modelVersion(for: single("en")), .v2)
  }

  /// The reported bug: Japanese meetings were decoded by v3, which has no Japanese tokens.
  func testJapaneseUsesTheJapaneseModel() {
    XCTAssertEqual(single("ja").onDeviceModel, .japanese)
    XCTAssertEqual(LocalTranscriptionService.modelVersion(for: single("ja")), .tdtJa)
  }

  func testEuropeanLanguagesUseV3() {
    for code in ["de", "es", "fr", "pl", "uk", "pt-BR"] {
      XCTAssertEqual(single(code).onDeviceModel, .europeanV3, code)
      XCTAssertEqual(LocalTranscriptionService.modelVersion(for: single(code)), .v3, code)
    }
    XCTAssertEqual(STTLanguageCapability.europeanV3Languages.count, 25)
  }

  func testLanguagesNoOnDeviceModelCoversHaveNoModel() {
    for code in ["ko", "zh-CN", "hi", "ar", "vi", "tr"] {
      XCTAssertNil(single(code).onDeviceModel, code)
      XCTAssertNil(LocalTranscriptionService.modelVersion(for: single(code)), code)
      XCTAssertTrue(STTLanguageCapability.cloudSupports(code), code)
    }
  }

  /// Auto-detect runs on v3, which identifies among its own languages only.
  func testAutoDetectStaysOnDeviceOnlyForAV3PrimaryLanguage() {
    XCTAssertEqual(autoDetect(primary: "en").onDeviceModel, .europeanV3)
    XCTAssertEqual(autoDetect(primary: "de").onDeviceModel, .europeanV3)
    XCTAssertNil(autoDetect(primary: "ja").onDeviceModel)
    XCTAssertNil(autoDetect(primary: "hi").onDeviceModel)
    XCTAssertTrue(STTLanguageCapability.cloudSupports(STTLanguageCapability.autoDetect))
  }

  func testDecodeHintIsTheLanguageAndNoneForAutoDetect() {
    XCTAssertEqual(single("pl").decodeHint, "pl")
    XCTAssertEqual(single("pt-BR").decodeHint, "pt")
    XCTAssertNil(autoDetect(primary: "en").decodeHint)
    // Every v3 language has a FluidAudio script-filter case, so no hint is silently dropped.
    for code in STTLanguageCapability.europeanV3Languages {
      XCTAssertNotNil(Language(rawValue: code), code)
    }
  }

  // MARK: - Routing

  func testJapaneseOnAppleSiliconStaysLocal() {
    XCTAssertEqual(resolve(single("ja")), .local)
  }

  func testKoreanOnAppleSiliconGoesToCloud() {
    XCTAssertEqual(resolve(single("ko")), .cloud)
  }

  func testEnglishOnAppleSiliconStaysLocal() {
    XCTAssertEqual(resolve(single("en")), .local)
  }

  func testJapaneseAutoDetectGoesToCloud() {
    XCTAssertEqual(resolve(autoDetect(primary: "ja")), .cloud)
  }

  func testBleWithoutBasicPlanStaysCloudForEveryLanguage() {
    for language in [single("en"), single("ja"), single("ko")] {
      XCTAssertEqual(resolve(language, source: .bleDevice), .cloud, language.effective)
    }
  }

  func testBasicBleFollowsTheLanguageLikeTheMic() {
    XCTAssertEqual(resolve(single("ja"), source: .bleDevice, preferLocalOnBasic: true), .local)
    XCTAssertEqual(resolve(single("ko"), source: .bleDevice, preferLocalOnBasic: true), .cloud)
  }

  func testIntelStaysCloudEvenForCoveredLanguages() {
    XCTAssertEqual(resolve(single("ja"), appleSilicon: false), .cloud)
  }

  /// A cloud outage must not drop an uncovered language onto a model that cannot decode it.
  func testCloudToLocalFallbackIsRefusedForAnUncoveredLanguage() {
    var session = STTSessionState()
    session.beginRecording(
      audioSource: .microphone, isAppleSilicon: true, debugForceCloud: false, language: single("ko"))
    XCTAssertEqual(session.activeMode, .cloud)
    XCTAssertFalse(
      session.canBeginCloudToLocalFallback(isTranscribing: true, audioSource: .microphone, isAppleSilicon: true))

    session.beginRecording(
      audioSource: .microphone, isAppleSilicon: true, debugForceCloud: true, language: single("ja"))
    XCTAssertEqual(session.activeMode, .cloud)
    XCTAssertTrue(
      session.canBeginCloudToLocalFallback(isTranscribing: true, audioSource: .microphone, isAppleSilicon: true))
  }

  func testSessionForcedLocalStillRoutesAnUncoveredLanguageToCloud() {
    var session = STTSessionState()
    session.beginRecording(
      audioSource: .microphone, isAppleSilicon: true, debugForceCloud: true, language: single("ja"))
    session.beginCloudToLocalFallback()
    XCTAssertEqual(
      session.resolveMode(
        audioSource: .microphone, isAppleSilicon: true, debugForceCloud: true, language: single("ja")),
      .local)
    XCTAssertEqual(
      session.resolveMode(
        audioSource: .microphone, isAppleSilicon: true, debugForceCloud: true, language: single("ko")),
      .cloud)
  }

  // MARK: - Settings notice

  func testCloudNoticeShowsOnlyForUncoveredLanguagesOnAppleSilicon() {
    XCTAssertTrue(CloudTranscriptionLanguageHint.isShown(for: single("ko"), isAppleSilicon: true))
    XCTAssertTrue(CloudTranscriptionLanguageHint.isShown(for: autoDetect(primary: "ja"), isAppleSilicon: true))
    XCTAssertFalse(CloudTranscriptionLanguageHint.isShown(for: single("ja"), isAppleSilicon: true))
    XCTAssertFalse(CloudTranscriptionLanguageHint.isShown(for: single("en"), isAppleSilicon: true))
    XCTAssertFalse(CloudTranscriptionLanguageHint.isShown(for: single("ko"), isAppleSilicon: false))
  }
}
