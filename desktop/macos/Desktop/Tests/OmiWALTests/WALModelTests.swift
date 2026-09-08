import OmiWAL
import XCTest

final class WALModelTests: XCTestCase {

  func testGenerateFileNameUsesSampleFrameSize() {
    let opus = WALEntry(
      timerStart: 1_700_000_000,
      codec: "opus",
      device: "dev1",
      deviceModel: "Omi"
    )
    XCTAssertEqual(opus.generateFileName(), "audio_dev1_opus_16000_1_fs160_1700000000.bin")

    let opusFs320 = WALEntry(
      timerStart: 1_700_000_000,
      codec: "opus_fs320",
      device: "dev1",
      deviceModel: "Limitless"
    )
    XCTAssertEqual(opusFs320.generateFileName(), "audio_dev1_opus_fs320_16000_1_fs320_1700000000.bin")
  }

  func testNormalizedForUploadRewritesLegacyOpusByteLength() {
    let legacy = "audio_dev1_opus_16000_1_fs80_1700000000.bin"
    XCTAssertEqual(
      WALSyncUploadFileName.normalizedForUpload(legacy),
      "audio_dev1_opus_16000_1_fs160_1700000000.bin"
    )
  }

  func testNormalizedForUploadRewritesLegacyOpusFs320ByteLength() {
    let legacy = "audio_dev1_opus_fs320_16000_1_fs160_1700000000.bin"
    XCTAssertEqual(
      WALSyncUploadFileName.normalizedForUpload(legacy),
      "audio_dev1_opus_fs320_16000_1_fs320_1700000000.bin"
    )
  }

  func testNormalizedForUploadLeavesCorrectSampleFrameSizeUnchanged() {
    let correct = "audio_dev1_opus_16000_1_fs160_1700000000.bin"
    XCTAssertEqual(WALSyncUploadFileName.normalizedForUpload(correct), correct)
  }

  func testNormalizedForUploadLeavesPcmUnchanged() {
    let pcm = "audio_dev1_pcm16_16000_1_fs160_1700000000.bin"
    XCTAssertEqual(WALSyncUploadFileName.normalizedForUpload(pcm), pcm)
  }

  func testNormalizedForUploadLeavesNonWalNamesUnchanged() {
    let other = "notes.txt"
    XCTAssertEqual(WALSyncUploadFileName.normalizedForUpload(other), other)
  }

  func testNormalizedForUploadDoesNotCorruptDeviceIdContainingFsToken() {
    // A device identifier containing the `_fs80` substring must not be touched
    // by the trailing `_fsN` rewrite. Only the matched trailing token is
    // rewritten; the device segment stays intact.
    let legacy = "audio_dev_fs80_opus_16000_1_fs80_1700000000.bin"
    XCTAssertEqual(
      WALSyncUploadFileName.normalizedForUpload(legacy),
      "audio_dev_fs80_opus_16000_1_fs160_1700000000.bin"
    )
  }
}
