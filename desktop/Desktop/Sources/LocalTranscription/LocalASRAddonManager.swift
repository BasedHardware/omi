import CryptoKit
import Foundation

struct LocalASRAddonProgress: Equatable {
  var label: String
  var fraction: Double?
}

struct LocalASRAddonStatus: Equatable {
  enum State: Equatable {
    case notInstalled
    case installing(LocalASRAddonProgress)
    case installed(version: String, models: Set<LocalTranscriptionModel>)
    case updateAvailable(installedVersion: String, latestVersion: String)
    case repairRequired(reason: String)
    case unsupported(reason: String)
  }

  var state: State
  var pythonPath: String?
  var detail: String

  var isInstalled: Bool {
    if case .installed = state { return true }
    if case .updateAvailable = state { return true }
    return false
  }

  var isActionableInstall: Bool {
    switch state {
    case .notInstalled, .repairRequired, .updateAvailable:
      return true
    case .installing, .unsupported:
      return false
    case .installed:
      return true
    }
  }
}

struct LocalASRAddonRemoteManifest: Codable, Equatable {
  var version: Int
  var runtime: RuntimeArtifact
  var models: [ModelArtifact]

  struct RuntimeArtifact: Codable, Equatable {
    var version: String
    var platform: String
    var arch: String
    var url: String
    var sha256: String
    var sizeBytes: Int64
    var minimumAppVersion: String?

    enum CodingKeys: String, CodingKey {
      case version, platform, arch, url, sha256
      case sizeBytes = "size_bytes"
      case minimumAppVersion = "minimum_app_version"
    }
  }

  struct ModelArtifact: Codable, Equatable {
    var model: LocalTranscriptionModel
    var version: String
    var url: String
    var sha256: String
    var sizeBytes: Int64

    enum CodingKeys: String, CodingKey {
      case model, version, url, sha256
      case sizeBytes = "size_bytes"
    }
  }
}

struct LocalASRAddonInstalledManifest: Codable, Equatable {
  var schemaVersion: Int
  var runtimeVersion: String
  var runtimeSha256: String
  var pythonPath: String
  var installedAt: Date
  var models: [InstalledModel]

  struct InstalledModel: Codable, Equatable {
    var model: LocalTranscriptionModel
    var version: String
    var sha256: String
    var path: String
    var installedAt: Date
  }

  enum CodingKeys: String, CodingKey {
    case schemaVersion = "schema_version"
    case runtimeVersion = "runtime_version"
    case runtimeSha256 = "runtime_sha256"
    case pythonPath = "python_path"
    case installedAt = "installed_at"
    case models
  }
}

enum LocalASRAddonManager {
  typealias ProgressHandler = @MainActor (LocalASRAddonProgress) -> Void

  private static let manifestFilename = "installed-manifest.json"
  private static let schemaVersion = 1

  static var rootDirectory: URL {
    let appSupport =
      FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
      ?? URL(fileURLWithPath: NSHomeDirectory()).appendingPathComponent(
        "Library/Application Support")
    return appSupport.appendingPathComponent("Omi/LocalASR", isDirectory: true)
  }

  static var manifestURL: URL {
    rootDirectory.appendingPathComponent(manifestFilename, isDirectory: false)
  }

  static func status() -> LocalASRAddonStatus {
    if let unsupported = unsupportedReason() {
      return LocalASRAddonStatus(
        state: .unsupported(reason: unsupported), pythonPath: nil, detail: unsupported)
    }

    guard let installed = try? readInstalledManifest() else {
      return LocalASRAddonStatus(
        state: .notInstalled,
        pythonPath: nil,
        detail: "Install local Whisper to enable on-device transcription"
      )
    }

    guard FileManager.default.isExecutableFile(atPath: installed.pythonPath) else {
      return LocalASRAddonStatus(
        state: .repairRequired(reason: "Installed runtime is missing"),
        pythonPath: installed.pythonPath,
        detail: "Installed runtime is missing"
      )
    }

    if let missingModel = installed.models.first(where: {
      !FileManager.default.fileExists(atPath: $0.path)
    }) {
      return LocalASRAddonStatus(
        state: .repairRequired(reason: "Installed \(missingModel.model.rawValue) model is missing"),
        pythonPath: installed.pythonPath,
        detail: "Installed \(missingModel.model.rawValue) model is missing"
      )
    }

    let installedModels = Set(installed.models.map(\.model))
    return LocalASRAddonStatus(
      state: .installed(version: installed.runtimeVersion, models: installedModels),
      pythonPath: installed.pythonPath,
      detail: installedModels.isEmpty
        ? "Local Whisper runtime installed; model install required"
        : "Local Whisper add-on installed"
    )
  }

  static func activateIfInstalled() {
    guard let installed = try? readInstalledManifest() else { return }
    guard FileManager.default.isExecutableFile(atPath: installed.pythonPath) else { return }

    setenv("OMI_LOCAL_ASR_PYTHON", installed.pythonPath, 1)
    setenv("OMI_LOCAL_ASR_ALLOW_MODEL_DOWNLOAD", "0", 1)

    for model in installed.models where FileManager.default.fileExists(atPath: model.path) {
      setenv(modelDirectoryEnvironmentKey(for: model.model), model.path, 1)
    }
  }

  static func install(
    quality: TranscriptionQualityPreset = .auto,
    progress: ProgressHandler? = nil
  ) async throws -> LocalASRAddonStatus {
    if let unsupported = unsupportedReason() {
      throw addonError(unsupported)
    }

    let model = initialModel(for: quality)
    let remote = try await fetchRemoteManifest()
    try await install(remote: remote, requiredModel: model, progress: progress)
    activateIfInstalled()
    return status()
  }

  static func installModel(
    for quality: TranscriptionQualityPreset,
    progress: ProgressHandler? = nil
  ) async throws -> LocalASRAddonStatus {
    if let unsupported = unsupportedReason() {
      throw addonError(unsupported)
    }

    let model = initialModel(for: quality)
    let remote = try await fetchRemoteManifest()
    try await install(remote: remote, requiredModel: model, progress: progress)
    activateIfInstalled()
    return status()
  }

  static func refreshStatusAgainstRemote() async -> LocalASRAddonStatus {
    var current = status()
    guard case .installed(let installedVersion, _) = current.state else { return current }
    guard let remote = try? await fetchRemoteManifest() else { return current }
    if remote.runtime.version != installedVersion {
      current.state = .updateAvailable(
        installedVersion: installedVersion,
        latestVersion: remote.runtime.version
      )
      current.detail = "Local Whisper update available"
    }
    return current
  }

  static func status(afterCapabilityProbe engines: Set<LocalTranscriptionEngine>)
    -> LocalASRAddonStatus
  {
    var current = status()
    guard current.isInstalled, !engines.contains(.mlxWhisper) else { return current }
    current.state = .repairRequired(
      reason: "Installed runtime did not pass the MLX Whisper capability probe")
    current.detail = "Installed runtime did not pass the MLX Whisper capability probe"
    return current
  }

  static func remove() throws -> LocalASRAddonStatus {
    if FileManager.default.fileExists(atPath: rootDirectory.path) {
      try FileManager.default.removeItem(at: rootDirectory)
    }

    unsetenv("OMI_LOCAL_ASR_PYTHON")
    unsetenv("OMI_LOCAL_ASR_ALLOW_MODEL_DOWNLOAD")
    for model in LocalTranscriptionModel.allCases {
      unsetenv(modelDirectoryEnvironmentKey(for: model))
    }

    return status()
  }

  private static func install(
    remote: LocalASRAddonRemoteManifest,
    requiredModel: LocalTranscriptionModel,
    progress: ProgressHandler?
  ) async throws {
    try validate(remote: remote)
    let runtimeArtifact = remote.runtime
    let modelArtifact = try artifact(for: requiredModel, in: remote)

    let tempRoot = rootDirectory.appendingPathComponent(
      "installing-\(UUID().uuidString)", isDirectory: true)
    let runtimeTemp = tempRoot.appendingPathComponent("runtime", isDirectory: true)
    let modelTemp = tempRoot.appendingPathComponent(
      "model-\(requiredModel.rawValue)", isDirectory: true)
    let runtimeActive = rootDirectory.appendingPathComponent("runtime", isDirectory: true)
    let modelsActive = rootDirectory.appendingPathComponent("models", isDirectory: true)
    let modelActive = modelsActive.appendingPathComponent(requiredModel.rawValue, isDirectory: true)

    try FileManager.default.createDirectory(at: tempRoot, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: tempRoot) }

    let existing = try? readInstalledManifest()
    let existingRuntimeUsable =
      existing?.runtimeVersion == runtimeArtifact.version
      && (existing?.runtimeSha256.lowercased() == runtimeArtifact.sha256.lowercased())
      && FileManager.default.isExecutableFile(atPath: existing?.pythonPath ?? "")

    let activePython: URL
    if existingRuntimeUsable, let existingPython = existing?.pythonPath {
      activePython = URL(fileURLWithPath: existingPython)
    } else {
      await progress?(LocalASRAddonProgress(label: "Downloading runtime", fraction: nil))
      let runtimeZip = try await download(
        artifactURL: runtimeArtifact.url,
        expectedSHA256: runtimeArtifact.sha256,
        expectedBytes: runtimeArtifact.sizeBytes,
        destinationName: "runtime-\(runtimeArtifact.version).zip",
        progressLabel: "Downloading runtime",
        progress: progress
      )
      try unzip(runtimeZip, to: runtimeTemp)
      let runtimePayload = try singlePayloadDirectory(in: runtimeTemp)
      let pythonPath = try findPython(in: runtimePayload)

      try FileManager.default.createDirectory(at: rootDirectory, withIntermediateDirectories: true)
      if FileManager.default.fileExists(atPath: runtimeActive.path) {
        try FileManager.default.removeItem(at: runtimeActive)
      }
      try FileManager.default.moveItem(at: runtimePayload, to: runtimeActive)
      activePython = runtimeActive.appendingPathComponent(
        relativePath(from: runtimePayload, to: pythonPath))
    }

    await progress?(LocalASRAddonProgress(label: "Downloading model", fraction: nil))
    let modelZip = try await download(
      artifactURL: modelArtifact.url,
      expectedSHA256: modelArtifact.sha256,
      expectedBytes: modelArtifact.sizeBytes,
      destinationName: "model-\(requiredModel.rawValue).zip",
      progressLabel: "Downloading model",
      progress: progress
    )
    try unzip(modelZip, to: modelTemp)

    try FileManager.default.createDirectory(at: rootDirectory, withIntermediateDirectories: true)
    try FileManager.default.createDirectory(at: modelsActive, withIntermediateDirectories: true)

    if FileManager.default.fileExists(atPath: modelActive.path) {
      try FileManager.default.removeItem(at: modelActive)
    }
    try FileManager.default.moveItem(at: modelTemp, to: modelActive)

    let activeModelPath = try singlePayloadDirectory(in: modelActive).path
    try writeInstalledManifest(
      runtimeVersion: runtimeArtifact.version,
      runtimeSha256: runtimeArtifact.sha256,
      pythonPath: activePython.path,
      model: requiredModel,
      modelVersion: modelArtifact.version,
      modelSha256: modelArtifact.sha256,
      modelPath: activeModelPath
    )

    activateIfInstalled()
    await progress?(LocalASRAddonProgress(label: "Validating local Whisper", fraction: nil))
    let engines = LocalASRHelperLocator.detectedEngines()
    guard engines.contains(.mlxWhisper) else {
      throw addonError("Installed runtime did not pass the MLX Whisper capability probe")
    }
  }

  private static func fetchRemoteManifest() async throws -> LocalASRAddonRemoteManifest {
    let manifestURL = try remoteManifestURL()
    if manifestURL.isFileURL {
      let data = try Data(contentsOf: manifestURL)
      return try JSONDecoder.localASRAddon.decode(LocalASRAddonRemoteManifest.self, from: data)
    }

    let (data, response): (Data, URLResponse)
    do {
      (data, response) = try await URLSession.shared.data(from: manifestURL)
    } catch {
      throw addonError("Local Whisper manifest request failed: \(error.localizedDescription)")
    }
    guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
      throw addonError("Local Whisper manifest request failed")
    }
    return try JSONDecoder.localASRAddon.decode(LocalASRAddonRemoteManifest.self, from: data)
  }

  private static func remoteManifestURL() throws -> URL {
    let override = ProcessInfo.processInfo.environment["OMI_LOCAL_ASR_MANIFEST_URL"]?
      .trimmingCharacters(in: .whitespacesAndNewlines)
    if let override, !override.isEmpty {
      guard let url = URL(string: override) else {
        throw addonError("Invalid OMI_LOCAL_ASR_MANIFEST_URL: \(override)")
      }
      return url
    }

    let base = DesktopBackendEnvironment.rustBackendURL()
    if let message = localDevManifestConfigurationMessage(
      modeValue: ProcessInfo.processInfo.environment["OMI_DESKTOP_BACKEND_MODE"],
      rustBackendURL: base,
      manifestOverride: override
    ) {
      throw addonError(message)
    }

    guard !base.isEmpty, let url = URL(string: base + "v1/local-asr/manifest") else {
      throw addonError("Omi desktop backend is not configured for Local Whisper add-on downloads")
    }
    return url
  }

  static func localDevManifestConfigurationMessage(
    modeValue: String?,
    rustBackendURL: String,
    manifestOverride: String?
  ) -> String? {
    let mode = modeValue?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    let override = manifestOverride?.trimmingCharacters(in: .whitespacesAndNewlines)
    guard override?.isEmpty ?? true else { return nil }
    guard ["local", "local-daemon", "local_daemon", "daemon"].contains(mode ?? "") else { return nil }
    guard let host = URL(string: rustBackendURL)?.host?.lowercased(), host == "omi-rust-invalid" else {
      return nil
    }
    return
      "Local Whisper add-on manifest is not configured for local dev. Run `make local-asr-fixture`, or set OMI_LOCAL_ASR_MANIFEST_URL."
  }

  private static func download(
    artifactURL: String,
    expectedSHA256: String,
    expectedBytes: Int64,
    destinationName: String,
    progressLabel: String,
    progress: ProgressHandler?
  ) async throws -> URL {
    guard let url = URL(string: artifactURL) else {
      throw addonError("Invalid Local Whisper artifact URL: \(artifactURL)")
    }

    let downloads = rootDirectory.appendingPathComponent("downloads", isDirectory: true)
    try FileManager.default.createDirectory(at: downloads, withIntermediateDirectories: true)
    let destination = downloads.appendingPathComponent(destinationName, isDirectory: false)
    let partial = destination.appendingPathExtension("part")

    if url.isFileURL {
      await progress?(LocalASRAddonProgress(label: progressLabel, fraction: nil))
      if FileManager.default.fileExists(atPath: partial.path) {
        try FileManager.default.removeItem(at: partial)
      }
      try FileManager.default.copyItem(at: url, to: partial)
      let actual = try sha256(of: partial)
      guard actual.lowercased() == expectedSHA256.lowercased() else {
        try? FileManager.default.removeItem(at: partial)
        throw addonError("Local Whisper artifact checksum mismatch")
      }
      if FileManager.default.fileExists(atPath: destination.path) {
        try FileManager.default.removeItem(at: destination)
      }
      try FileManager.default.moveItem(at: partial, to: destination)
      await progress?(LocalASRAddonProgress(label: progressLabel, fraction: 1.0))
      return destination
    }

    var existingBytes: Int64 = 0
    if FileManager.default.fileExists(atPath: partial.path),
      let attrs = try? FileManager.default.attributesOfItem(atPath: partial.path),
      let size = attrs[.size] as? NSNumber
    {
      existingBytes = size.int64Value
    }

    var request = URLRequest(url: url)
    if existingBytes > 0 {
      request.setValue("bytes=\(existingBytes)-", forHTTPHeaderField: "Range")
    }

    let (bytes, response) = try await URLSession.shared.bytes(for: request)
    guard let http = response as? HTTPURLResponse else {
      throw addonError("Invalid Local Whisper artifact response")
    }

    let shouldAppend = existingBytes > 0 && http.statusCode == 206
    guard http.statusCode == 200 || shouldAppend else {
      throw addonError("Local Whisper artifact download failed with HTTP \(http.statusCode)")
    }

    if !shouldAppend {
      existingBytes = 0
      try? FileManager.default.removeItem(at: partial)
      FileManager.default.createFile(atPath: partial.path, contents: nil)
    }

    let handle = try FileHandle(forWritingTo: partial)
    try handle.seekToEnd()
    defer { try? handle.close() }

    var downloaded = existingBytes
    var buffer = Data()
    buffer.reserveCapacity(64 * 1024)
    for try await byte in bytes {
      buffer.append(byte)
      if buffer.count >= 64 * 1024 {
        try handle.write(contentsOf: buffer)
        buffer.removeAll(keepingCapacity: true)
      }
      downloaded += 1
      if expectedBytes > 0 && downloaded % 262_144 == 0 {
        await progress?(
          LocalASRAddonProgress(
            label: progressLabel,
            fraction: min(Double(downloaded) / Double(expectedBytes), 1.0)
          ))
      }
    }
    if !buffer.isEmpty {
      try handle.write(contentsOf: buffer)
    }

    try handle.close()
    let actual = try sha256(of: partial)
    guard actual.lowercased() == expectedSHA256.lowercased() else {
      try? FileManager.default.removeItem(at: partial)
      throw addonError("Local Whisper artifact checksum mismatch")
    }

    if FileManager.default.fileExists(atPath: destination.path) {
      try FileManager.default.removeItem(at: destination)
    }
    try FileManager.default.moveItem(at: partial, to: destination)
    await progress?(LocalASRAddonProgress(label: progressLabel, fraction: 1.0))
    return destination
  }

  private static func validate(remote: LocalASRAddonRemoteManifest) throws {
    guard remote.version == 1 else {
      throw addonError("Unsupported Local Whisper manifest version")
    }
    guard remote.runtime.platform == "macos", remote.runtime.arch == "arm64" else {
      throw addonError("Local Whisper runtime does not support this Mac")
    }
    guard !remote.runtime.url.isEmpty, !remote.runtime.sha256.isEmpty else {
      throw addonError("Local Whisper runtime manifest is incomplete")
    }
    if let minimumAppVersion = remote.runtime.minimumAppVersion,
      compareVersion(currentAppVersion(), minimumAppVersion) == .orderedAscending
    {
      throw addonError("Local Whisper requires Omi \(minimumAppVersion) or newer")
    }
  }

  private static func artifact(
    for model: LocalTranscriptionModel,
    in remote: LocalASRAddonRemoteManifest
  ) throws -> LocalASRAddonRemoteManifest.ModelArtifact {
    guard let artifact = remote.models.first(where: { $0.model == model }) else {
      throw addonError("No Local Whisper model artifact is available for \(model.rawValue)")
    }
    return artifact
  }

  private static func readInstalledManifest() throws -> LocalASRAddonInstalledManifest {
    let data = try Data(contentsOf: manifestURL)
    return try JSONDecoder.localASRAddon.decode(LocalASRAddonInstalledManifest.self, from: data)
  }

  private static func writeInstalledManifest(
    runtimeVersion: String,
    runtimeSha256: String,
    pythonPath: String,
    model: LocalTranscriptionModel,
    modelVersion: String,
    modelSha256: String,
    modelPath: String
  ) throws {
    var installedModels: [LocalASRAddonInstalledManifest.InstalledModel] = []
    if let existing = try? readInstalledManifest() {
      installedModels = existing.models.filter { $0.model != model }
    }
    installedModels.append(
      LocalASRAddonInstalledManifest.InstalledModel(
        model: model,
        version: modelVersion,
        sha256: modelSha256,
        path: modelPath,
        installedAt: Date()
      ))

    let manifest = LocalASRAddonInstalledManifest(
      schemaVersion: schemaVersion,
      runtimeVersion: runtimeVersion,
      runtimeSha256: runtimeSha256,
      pythonPath: pythonPath,
      installedAt: Date(),
      models: installedModels.sorted { $0.model.rawValue < $1.model.rawValue }
    )
    let data = try JSONEncoder.localASRAddon.encode(manifest)
    try data.write(to: manifestURL, options: .atomic)
  }

  private static func findPython(in directory: URL) throws -> URL {
    let candidates = [
      directory.appendingPathComponent("bin/python3", isDirectory: false),
      directory.appendingPathComponent("venv/bin/python3", isDirectory: false),
      directory.appendingPathComponent("runtime/bin/python3", isDirectory: false),
      directory.appendingPathComponent("runtime/venv/bin/python3", isDirectory: false),
    ]
    if let python = candidates.first(where: {
      FileManager.default.isExecutableFile(atPath: $0.path)
    }) {
      return python
    }
    throw addonError("Local Whisper runtime artifact does not contain bin/python3")
  }

  private static func singlePayloadDirectory(in directory: URL) throws -> URL {
    let contents = try FileManager.default.contentsOfDirectory(
      at: directory,
      includingPropertiesForKeys: [.isDirectoryKey],
      options: [.skipsHiddenFiles]
    )
    if contents.count == 1,
      let values = try? contents[0].resourceValues(forKeys: [.isDirectoryKey]),
      values.isDirectory == true
    {
      return contents[0]
    }
    return directory
  }

  private static func unzip(_ zipURL: URL, to destination: URL) throws {
    try FileManager.default.createDirectory(at: destination, withIntermediateDirectories: true)
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/usr/bin/unzip")
    process.arguments = ["-q", zipURL.path, "-d", destination.path]
    process.standardOutput = Pipe()
    let errors = Pipe()
    process.standardError = errors
    try process.run()
    process.waitUntilExit()
    guard process.terminationStatus == 0 else {
      let stderr =
        String(data: errors.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
      throw addonError("Failed to extract Local Whisper artifact: \(stderr)")
    }
  }

  private static func sha256(of url: URL) throws -> String {
    let handle = try FileHandle(forReadingFrom: url)
    defer { try? handle.close() }

    var hasher = SHA256()
    while true {
      let data = try handle.read(upToCount: 1024 * 1024) ?? Data()
      if data.isEmpty { break }
      hasher.update(data: data)
    }
    return hasher.finalize().map { String(format: "%02x", $0) }.joined()
  }

  private static func relativePath(from root: URL, to child: URL) -> String {
    let rootPath = root.standardizedFileURL.path
    let childPath = child.standardizedFileURL.path
    guard childPath.hasPrefix(rootPath + "/") else { return child.lastPathComponent }
    return String(childPath.dropFirst(rootPath.count + 1))
  }

  private static func compareVersion(_ lhs: String, _ rhs: String) -> ComparisonResult {
    lhs.compare(rhs, options: [.numeric, .caseInsensitive])
  }

  private static func currentAppVersion() -> String {
    Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "0.0.0"
  }

  static func initialModel(for quality: TranscriptionQualityPreset) -> LocalTranscriptionModel {
    let memory = ProcessInfo.processInfo.physicalMemory / (1024 * 1024 * 1024)
    switch quality {
    case .fast:
      return .base
    case .auto, .balanced:
      return memory >= 8 ? .small : .base
    case .accurate:
      return memory >= 24 ? .largeV3Turbo : (memory >= 16 ? .medium : .small)
    }
  }

  private static func modelDirectoryEnvironmentKey(for model: LocalTranscriptionModel) -> String {
    "OMI_MLX_WHISPER_MODEL_DIR_\(model.rawValue.uppercased())"
  }

  private static func unsupportedReason() -> String? {
    let capabilities = LocalTranscriptionCapabilityDetector().detect()
    switch capabilities.processor {
    case .nativeAppleSilicon:
      return nil
    case .rosettaOnAppleSilicon:
      return "MLX Whisper requires running Omi natively, not under Rosetta."
    case .intel:
      return "MLX Whisper requires an Apple Silicon Mac."
    case .unknown:
      return "This Mac does not report a supported Apple Silicon processor."
    }
  }

  private static func addonError(_ message: String) -> NSError {
    NSError(domain: "LocalASRAddonManager", code: 1, userInfo: [NSLocalizedDescriptionKey: message])
  }
}

extension JSONDecoder {
  static var localASRAddon: JSONDecoder {
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .iso8601
    return decoder
  }
}

extension JSONEncoder {
  static var localASRAddon: JSONEncoder {
    let encoder = JSONEncoder()
    encoder.dateEncodingStrategy = .iso8601
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    return encoder
  }
}
