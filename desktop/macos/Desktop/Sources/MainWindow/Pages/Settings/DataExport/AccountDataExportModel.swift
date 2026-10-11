import AppKit
import Foundation
import UniformTypeIdentifiers

@MainActor
final class AccountDataExportModel: ObservableObject {
  @Published private(set) var isExporting = false
  @Published private(set) var bytesReceived: Int64 = 0
  @Published var errorMessage: String?

  private let runSavePanel: @MainActor () async -> URL?
  private let ownerSnapshot: () -> RuntimeOwnerAuthorizationSnapshot?
  private let download:
    (URL, RuntimeOwnerAuthorizationSnapshot, @escaping @Sendable (Int64) -> Void) async throws -> Void
  private let confirm: @MainActor (String) -> Void
  private let allowsAutomation: () -> Bool

  private var exportTask: Task<Void, Never>?
  private var activeRunID = UUID()

  init(
    runSavePanel: (@MainActor () async -> URL?)? = nil,
    ownerSnapshot: (() -> RuntimeOwnerAuthorizationSnapshot?)? = nil,
    download: ((URL, RuntimeOwnerAuthorizationSnapshot, @escaping @Sendable (Int64) -> Void) async throws -> Void)? =
      nil,
    confirm: (@MainActor (String) -> Void)? = nil,
    allowsAutomation: (() -> Bool)? = nil
  ) {
    self.runSavePanel =
      runSavePanel ?? { await Self.presentSavePanel() }
    self.ownerSnapshot =
      ownerSnapshot ?? { RuntimeOwnerIdentity.captureAuthorizationSnapshot() }
    self.download =
      download ?? { destination, snapshot, onProgress in
        try await APIClient.shared.exportUserData(
          to: destination,
          authorizationSnapshot: snapshot,
          onProgress: onProgress)
      }
    self.confirm =
      confirm ?? { OmiToastCenter.shared.confirm($0) }
    self.allowsAutomation = allowsAutomation ?? { AppBuild.isNonProduction }
  }

  func startExport() {
    beginExport()
  }

  private func beginExport(destinationOverride: URL? = nil) {
    guard !isExporting else { return }
    guard let snapshot = ownerSnapshot() else {
      errorMessage = "You need to be signed in to export your data."
      return
    }

    errorMessage = nil
    isExporting = true
    bytesReceived = 0
    let runID = UUID()
    activeRunID = runID
    let download = self.download
    let runSavePanel = self.runSavePanel

    exportTask = Task { @MainActor [weak self] in
      guard let self else { return }
      defer {
        if self.activeRunID == runID {
          self.isExporting = false
          self.exportTask = nil
        }
      }
      do {
        let destination: URL
        if let destinationOverride {
          destination = destinationOverride
        } else {
          guard let panelDestination = await runSavePanel() else { return }
          destination = panelDestination
        }
        try Task.checkCancellation()
        try await download(destination, snapshot) { [weak self] bytes in
          Task { @MainActor in
            guard let self, self.activeRunID == runID else { return }
            self.bytesReceived = bytes
          }
        }
        try Task.checkCancellation()
        guard self.activeRunID == runID else { return }
        self.confirm("Export Saved")
      } catch is CancellationError {
      } catch {
        guard self.activeRunID == runID else { return }
        self.errorMessage = UserFacingErrorPresentation.message(for: error, while: .memoryExport)
      }
    }
  }

  func cancelExport() {
    activeRunID = UUID()
    exportTask?.cancel()
    exportTask = nil
    isExporting = false
  }

  func exportForAutomation() async throws -> [String: String] {
    guard allowsAutomation() else {
      throw DesktopAutomationActionError.invalidParams("export fixture requires a non-production build")
    }
    let allowedHosts: Set<String> = ["127.0.0.1", "localhost", "::1"]
    guard let host = URL(string: await APIClient.shared.baseURL)?.host,
      allowedHosts.contains(host)
    else {
      throw DesktopAutomationActionError.invalidParams("export fixture requires a loopback backend")
    }
    guard !isExporting else {
      throw DesktopAutomationActionError.invalidParams("an export is already running")
    }
    let directory = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-export-automation-\(UUID().uuidString)")
    try FileManager.default.createDirectory(
      at: directory,
      withIntermediateDirectories: true,
      attributes: [.posixPermissions: 0o700])
    defer { try? FileManager.default.removeItem(at: directory) }

    let destination = directory.appendingPathComponent("omi-export.json")
    beginExport(destinationOverride: destination)
    await exportTask?.value
    if errorMessage != nil {
      throw DesktopAutomationActionError.invalidParams("export failed")
    }
    try APIClient.validateExportFile(at: destination, expectedLength: -1)
    let size =
      (try FileManager.default.attributesOfItem(atPath: destination.path)[.size] as? Int64) ?? 0
    return ["completed": "true", "bytes": "\(size)"]
  }

  func registerAutomationActions() {
    guard allowsAutomation() else { return }
    DesktopAutomationActionRegistry.shared.register(
      name: "settings_export_data_fixture",
      effects: [.localState, .localArtifact, .networkOrModel],
      summary: "Export and validate synthetic account data through the loopback backend",
      category: "debug",
      surfaces: ["settings"],
      sideEffects: [
        "writes and removes one owned temporary export file",
        "reads account data only from the loopback fixture",
      ]
    ) { [weak self] _ in
      guard let self else {
        throw DesktopAutomationActionError.invalidParams("export view not mounted")
      }
      return try await self.exportForAutomation()
    }
  }

  func unregisterAutomationActions() {
    DesktopAutomationActionRegistry.shared.unregister("settings_export_data_fixture")
  }

  private static func presentSavePanel() async -> URL? {
    let panel = NSSavePanel()
    panel.nameFieldStringValue = "omi-export.json"
    panel.allowedContentTypes = [.json]
    if let window = NSApp.keyWindow {
      return await withCheckedContinuation { continuation in
        panel.beginSheetModal(for: window) { response in
          continuation.resume(returning: response == .OK ? panel.url : nil)
        }
      }
    }
    return panel.runModal() == .OK ? panel.url : nil
  }
}
