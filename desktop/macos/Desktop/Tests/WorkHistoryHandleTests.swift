import Foundation
import GRDB
import XCTest

@testable import Omi_Computer

final class WorkHistoryHandleTests: XCTestCase {
  func testCanonicalizesHttpURLAndDropsFragmentUserinfoAndDefaultPort() {
    let handle = WorkHistoryHandle.url(
      "HTTPS://User:secret@Docs.Google.COM:443/document/d/abc/?usp=sharing#heading")
    XCTAssertEqual(handle?.kind, .url)
    XCTAssertEqual(handle?.value, "https://docs.google.com/document/d/abc")
  }

  func testTrackingQueryDoesNotSplitIdentity() {
    let shared = WorkHistoryHandle.url("https://docs.google.com/document/d/abc?usp=sharing")
    let clean = WorkHistoryHandle.url("https://docs.google.com/document/d/abc")
    XCTAssertEqual(shared, clean)
  }

  func testCredentialQueryIsDroppedFromIdentityAndOutboundJSON() {
    let handle = WorkHistoryHandle.url(
      "https://docs.google.com/document/d/abc?access_token=secret&q=proposal")
    XCTAssertEqual(handle?.value, "https://docs.google.com/document/d/abc?q=proposal")
    XCTAssertEqual(handle?.jsonObject()["value"], "https://docs.google.com/document/d/abc?q=proposal")
  }

  func testPreservesPercentEncodedPathIdentity() {
    let handle = WorkHistoryHandle.url("https://example.com/a%2Fb/?utm_source=x")
    XCTAssertEqual(handle?.value, "https://example.com/a%2Fb")
  }

  func testBrowserPrefersDocumentURLOverChildAXURL() {
    let snapshot = WorkHistoryFrontmostSnapshot(
      appName: "Safari",
      windowTitle: "Proposal",
      bundleID: "com.apple.Safari",
      documentURL: URL(string: "https://docs.google.com/document/d/abc"),
      browserURL: URL(string: "https://example.com/favicon.ico")
    )
    XCTAssertEqual(
      WorkHistoryHandleExtractor.handles(from: snapshot).first?.value,
      "https://docs.google.com/document/d/abc")
  }

  func testRejectsNonHttpSchemesAndAboutBlank() {
    XCTAssertNil(WorkHistoryHandle.url("about:blank"))
    XCTAssertNil(WorkHistoryHandle.url("javascript:alert(1)"))
    XCTAssertNil(WorkHistoryHandle.url("file:///tmp/notes.md"))
  }

  func testCanonicalizesFilePaths() {
    XCTAssertEqual(WorkHistoryHandle.file("file:///Users/ada/Notes.md")?.value, "/Users/ada/Notes.md")
    XCTAssertEqual(WorkHistoryHandle.file("/Users/ada/./Notes.md")?.value, "/Users/ada/Notes.md")
    XCTAssertNil(WorkHistoryHandle.file("/"))
  }

  func testExtractorPrefersBrowserURLOverWindowTitle() {
    let snapshot = WorkHistoryFrontmostSnapshot(
      appName: "Google Chrome",
      windowTitle: "Proposal - Google Docs",
      bundleID: "com.google.Chrome",
      documentURL: nil,
      browserURL: URL(string: "https://docs.google.com/document/d/abc")
    )
    let handles = WorkHistoryHandleExtractor.handles(from: snapshot)
    XCTAssertEqual(handles.first?.kind, .url)
    XCTAssertEqual(handles.first?.value, "https://docs.google.com/document/d/abc")
    XCTAssertTrue(handles.contains(where: { $0.kind == .appWindow }))
  }

  func testExtractorUsesAXDocumentAsFileHandleForEditors() {
    let snapshot = WorkHistoryFrontmostSnapshot(
      appName: "Cursor",
      windowTitle: "WorkHistoryHandle.swift — omi",
      bundleID: "com.todesktop.230313mzl4w4u92",
      documentURL: URL(fileURLWithPath: "/Users/ada/omi/WorkHistoryHandle.swift"),
      browserURL: nil
    )
    let handles = WorkHistoryHandleExtractor.handles(from: snapshot)
    XCTAssertEqual(handles.first?.kind, .file)
    XCTAssertEqual(handles.first?.value, "/Users/ada/omi/WorkHistoryHandle.swift")
  }

  func testSameCanonicalURLIsPrimaryAcrossApps() {
    let chrome = WorkHistoryHandleExtractor.handles(
      from: WorkHistoryFrontmostSnapshot(
        appName: "Google Chrome",
        windowTitle: "PR 12",
        browserURL: URL(string: "https://github.com/BasedHardware/omi/pull/12/")
      ))
    let arc = WorkHistoryHandleExtractor.handles(
      from: WorkHistoryFrontmostSnapshot(
        appName: "Arc",
        windowTitle: "Different title",
        browserURL: URL(string: "https://github.com/BasedHardware/omi/pull/12")
      ))
    XCTAssertEqual(WorkHistoryHandle.primary(in: chrome), WorkHistoryHandle.primary(in: arc))
  }
}
