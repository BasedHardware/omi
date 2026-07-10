import Foundation
import XCTest

@testable import Omi_Computer

final class WacliInstallerTests: XCTestCase {
  func testInstallDirectoryIsUnderApplicationSupportWhatsAppBin() {
    let home = URL(fileURLWithPath: "/tmp/omi-wacli-home", isDirectory: true)
    let dir = WacliInstaller.installDirectory(homeDirectory: home)
    XCTAssertEqual(
      dir.path,
      "/tmp/omi-wacli-home/Library/Application Support/Omi/whatsapp/bin"
    )
  }

  func testFindInstalledBinaryRequiresMatchingVersionFile() throws {
    let home = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-wacli-find-\(UUID().uuidString)", isDirectory: true)
    defer { try? FileManager.default.removeItem(at: home) }

    let installDir = WacliInstaller.installDirectory(homeDirectory: home)
    try FileManager.default.createDirectory(at: installDir, withIntermediateDirectories: true)

    let binary = WacliInstaller.installedBinaryURL(homeDirectory: home)
    FileManager.default.createFile(atPath: binary.path, contents: Data("#!/bin/sh\n".utf8))
    try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: binary.path)

    XCTAssertNil(WacliInstaller.findInstalledBinary(homeDirectory: home))

    let versionURL = installDir.appendingPathComponent("wacli.version")
    try "\(WacliInstaller.version)\n".write(to: versionURL, atomically: true, encoding: .utf8)
    XCTAssertEqual(WacliInstaller.findInstalledBinary(homeDirectory: home), binary.path)
  }

  func testArchiveChecksumConstantMatchesPinnedRelease() {
    XCTAssertEqual(WacliInstaller.version, "0.11.2")
    XCTAssertEqual(
      WacliInstaller.archiveSHA256,
      "d76b6f8a90ceee03a25adf2b2a1f680d8f63c1b5bba0322aa5e1de07a06dd9e2"
    )
    XCTAssertTrue(
      WacliInstaller.downloadURL.absoluteString.contains("wacli_0.11.2_darwin_universal.tar.gz")
    )
  }

  func testSha256HexHelper() {
    let hex = WacliInstaller.sha256Hex(of: Data("abc".utf8))
    XCTAssertEqual(hex, "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
  }
}
