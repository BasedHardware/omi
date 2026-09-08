import CryptoKit
import Foundation
import XCTest

@testable import Omi_Computer

final class RealtimeVoicePhraseAssetTests: XCTestCase {
  private let scratch = FileManager.default.temporaryDirectory
    .appendingPathComponent("omi-realtime-voice-phrases-\(UUID().uuidString)", isDirectory: true)

  override func setUpWithError() throws {
    try super.setUpWithError()
    try FileManager.default.createDirectory(at: scratch, withIntermediateDirectories: true)
  }

  override func tearDownWithError() throws {
    try? FileManager.default.removeItem(at: scratch)
    try super.tearDownWithError()
  }

  func testProfilesPinTheNativeRealtimeVoice() {
    XCTAssertEqual(RealtimeVoicePhraseProfile(provider: .gemini), .geminiCharon)
    XCTAssertEqual(RealtimeVoicePhraseProfile(provider: .openai), .openAICedar)
    XCTAssertEqual(RealtimeVoicePhraseProfile.geminiCharon.voiceName, "Charon")
    XCTAssertEqual(RealtimeVoicePhraseProfile.openAICedar.voiceName, "cedar")
    XCTAssertEqual(RealtimeVoicePhraseProfile.geminiCharon.provider, .gemini)
    XCTAssertEqual(RealtimeVoicePhraseProfile.openAICedar.provider, .openai)
  }

  func testAssetFilenameIsStableAndContainsProviderVoiceKindAndPhrase() {
    let asset = RealtimeVoicePhraseAsset(
      profile: .geminiCharon,
      kind: .deeperThinking,
      phrase: "I'll take a closer look."
    )

    XCTAssertEqual(
      asset.fileName,
      "gemini-charon-deeper-thinking-ill-take-a-closer-look.wav"
    )
    XCTAssertEqual(
      RealtimeVoicePhraseAsset.slug("Give me a moment to think that through."),
      "give-me-a-moment-to-think-that-through"
    )
  }

  func testProviderAndKindArePartOfEveryFilename() {
    let phrases = RealtimeSlowToolAcknowledgementKind.allCases.flatMap { kind in
      kind.phrases.map { (kind, $0) }
    }
    let assets = RealtimeVoicePhraseProfile.allCases.flatMap { profile in
      phrases.map { RealtimeVoicePhraseAsset(profile: profile, kind: $0.0, phrase: $0.1) }
    }
    let names = Set(assets.map(\.fileName))

    XCTAssertEqual(names.count, assets.count)
    XCTAssertTrue(names.allSatisfy { $0.hasSuffix(".wav") })
    XCTAssertTrue(names.contains { $0.hasPrefix("gemini-charon-") })
    XCTAssertTrue(names.contains { $0.hasPrefix("openai-cedar-") })
  }

  func testLocatorPrefersEarlierRootAndSupportsTheProcessedVoicePhrasesDirectory() throws {
    let firstRoot = scratch.appendingPathComponent("first", isDirectory: true)
    let secondRoot = scratch.appendingPathComponent("second", isDirectory: true)
    try FileManager.default.createDirectory(at: firstRoot, withIntermediateDirectories: true)
    try FileManager.default.createDirectory(at: secondRoot, withIntermediateDirectories: true)

    let provider = RealtimeHubProvider.gemini
    let kind = RealtimeSlowToolAcknowledgementKind.deeperThinking
    let phrase = "Let me think that through."
    let asset = RealtimeVoicePhraseAsset(
      profile: RealtimeVoicePhraseProfile(provider: provider), kind: kind, phrase: phrase)
    let nested = firstRoot.appendingPathComponent("VoicePhrases", isDirectory: true)
      .appendingPathComponent(asset.fileName)
    try FileManager.default.createDirectory(at: nested.deletingLastPathComponent(), withIntermediateDirectories: true)
    try Data("nested".utf8).write(to: nested)
    let flat = secondRoot.appendingPathComponent(asset.fileName)
    try Data("flat".utf8).write(to: flat)

    let locator = RealtimeVoicePhraseAssetLocator(roots: [firstRoot, secondRoot])
    XCTAssertEqual(locator.url(for: asset), nested)
    XCTAssertEqual(locator.url(for: provider, kind: kind, phrase: phrase), nested)
  }

  func testLocatorReturnsNilForAnAbsentProviderVoicePhrase() {
    let locator = RealtimeVoicePhraseAssetLocator(roots: [scratch])
    XCTAssertNil(
      locator.url(
        for: .openai,
        kind: .publicWebSearch,
        phrase: "Let me look that up."
      )
    )
  }

  func testProductionSelectionUsesBundledAudioBeforeFallback() throws {
    let phrase = "Let me think that through."
    let asset = RealtimeVoicePhraseAsset(
      profile: .geminiCharon, kind: .deeperThinking, phrase: phrase)
    let url = scratch.appendingPathComponent(asset.fileName)
    let wav = Self.validWAVFixture()
    try wav.write(to: url)
    var loadCount = 0

    let selection = RealtimeVoicePhraseAudioSelection.select(
      provider: .gemini,
      kind: .deeperThinking,
      phrase: phrase,
      locator: RealtimeVoicePhraseAssetLocator(roots: [scratch]),
      load: { candidate in
        loadCount += 1
        return try Data(contentsOf: candidate)
      })

    XCTAssertEqual(selection, .bundled(wav))
    XCTAssertEqual(loadCount, 1)
  }

  func testProductionSelectionFallsBackForMissingOrMalformedAudio() throws {
    let phrase = "Let me think that through."
    let asset = RealtimeVoicePhraseAsset(
      profile: .geminiCharon, kind: .deeperThinking, phrase: phrase)
    let url = scratch.appendingPathComponent(asset.fileName)
    try Data("not a wav".utf8).write(to: url)
    let locator = RealtimeVoicePhraseAssetLocator(roots: [scratch])

    XCTAssertEqual(
      RealtimeVoicePhraseAudioSelection.select(
        provider: .gemini, kind: .deeperThinking, phrase: phrase, locator: locator),
      .fallback)
    XCTAssertEqual(
      RealtimeVoicePhraseAudioSelection.select(
        provider: .openai, kind: .deeperThinking, phrase: phrase, locator: locator),
      .fallback)
  }

  func testBundledPackContainsEveryProviderKindAndPhrase() throws {
    let sourceResourceRoot = Self.sourceResourceRoot
    let sourceLocator = RealtimeVoicePhraseAssetLocator(roots: [sourceResourceRoot])

    for profile in RealtimeVoicePhraseProfile.allCases {
      for kind in RealtimeSlowToolAcknowledgementKind.allCases {
        for phrase in kind.phrases {
          let asset = RealtimeVoicePhraseAsset(profile: profile, kind: kind, phrase: phrase)
          let url = try XCTUnwrap(
            sourceLocator.url(for: asset),
            "missing bundled voice phrase \(asset.fileName)"
          )
          let data = try Data(contentsOf: url)
          XCTAssertGreaterThan(data.count, 44, "\(asset.fileName) must contain WAV audio")
          XCTAssertEqual(String(data: data.prefix(4), encoding: .ascii), "RIFF")
          XCTAssertEqual(String(data: data.dropFirst(8).prefix(4), encoding: .ascii), "WAVE")
        }
      }
    }
  }

  func testManifestMetadataAndHashesMatchEveryShippedClip() throws {
    let directory = Self.sourceResourceRoot.appendingPathComponent("VoicePhrases")
    let manifestData = try Data(contentsOf: directory.appendingPathComponent("manifest.json"))
    let manifest = try JSONDecoder().decode(VoicePhraseManifest.self, from: manifestData)
    let expectedNames = Set(
      RealtimeVoicePhraseProfile.allCases.flatMap { profile in
        RealtimeSlowToolAcknowledgementKind.allCases.flatMap { kind in
          kind.phrases.map {
            RealtimeVoicePhraseAsset(profile: profile, kind: kind, phrase: $0).fileName
          }
        }
      })

    XCTAssertEqual(manifest.schemaVersion, 1)
    XCTAssertEqual(Set(manifest.assets.map(\.file)), expectedNames)
    for asset in manifest.assets {
      let data = try Data(contentsOf: directory.appendingPathComponent(asset.file))
      XCTAssertEqual(data.count, asset.bytes, asset.file)
      XCTAssertEqual(
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined(),
        asset.sha256,
        asset.file)
      XCTAssertEqual(asset.phrase, asset.transcription, asset.file)
    }
  }

  private static var sourceResourceRoot: URL {
    URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()  // Tests/
      .deletingLastPathComponent()  // Desktop/
      .appendingPathComponent("Sources/Resources")
  }

  private static func validWAVFixture() -> Data {
    var data = Data("RIFF".utf8)
    data.append(Data(repeating: 0, count: 4))
    data.append(Data("WAVE".utf8))
    data.append(Data(repeating: 0, count: 40))
    return data
  }
}

private struct VoicePhraseManifest: Decodable {
  struct Asset: Decodable {
    let file: String
    let phrase: String
    let transcription: String
    let sha256: String
    let bytes: Int
  }

  let schemaVersion: Int
  let assets: [Asset]
}
