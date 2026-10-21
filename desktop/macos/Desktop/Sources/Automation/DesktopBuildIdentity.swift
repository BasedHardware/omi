import Foundation

/// Source identity embedded into a desktop bundle by `run.sh`.
///
/// The fields are treated as one receipt: partial or malformed metadata never
/// becomes trusted evidence. Older bundles therefore report `unknown` instead
/// of borrowing the identity of whichever checkout happens to inspect them.
struct DesktopBuildIdentity: Codable, Equatable, Sendable {
  enum WorkingTreeState: String, Codable, Sendable {
    case clean
    case dirty
    case unknown
  }

  static let metadataSchemaVersion = 1
  static let schemaVersionInfoKey = "OMIBuildIdentitySchemaVersion"
  static let revisionInfoKey = "OMISourceRevision"
  static let workingTreeStateInfoKey = "OMISourceWorkingTreeState"

  let schemaVersion: Int
  let revision: String
  let workingTreeState: WorkingTreeState

  static let unknown = DesktopBuildIdentity(
    schemaVersion: metadataSchemaVersion,
    revision: "unknown",
    workingTreeState: .unknown)

  static var current: DesktopBuildIdentity {
    from(infoDictionary: Bundle.main.infoDictionary ?? [:])
  }

  static func from(infoDictionary: [String: Any]) -> DesktopBuildIdentity {
    guard
      let schemaVersion = infoDictionary[schemaVersionInfoKey] as? NSNumber,
      schemaVersion.intValue == metadataSchemaVersion,
      let revision = infoDictionary[revisionInfoKey] as? String,
      isFullGitRevision(revision),
      let rawTreeState = infoDictionary[workingTreeStateInfoKey] as? String,
      let workingTreeState = WorkingTreeState(rawValue: rawTreeState),
      workingTreeState != .unknown
    else {
      return .unknown
    }

    return DesktopBuildIdentity(
      schemaVersion: metadataSchemaVersion,
      revision: revision,
      workingTreeState: workingTreeState)
  }

  private static func isFullGitRevision(_ value: String) -> Bool {
    guard value.count == 40, value == value.lowercased() else { return false }
    let hexadecimal = CharacterSet(charactersIn: "0123456789abcdef")
    return value.unicodeScalars.allSatisfy(hexadecimal.contains)
  }
}

/// Unauthenticated identity payload returned by `GET /health`.
struct DesktopAutomationHealth: Codable {
  let ok: Bool
  let name: String
  let bundleIdentifier: String
  let sourceIdentity: DesktopBuildIdentity
  let processID: Int32
  let logFilePath: String
  let logLaunchID: String
  let bridgePort: UInt16
  let requiresAuth: Bool
  let backendEnvironment: String
  let pythonBackendURL: String
  let rustBackendURL: String
  let agentRuntimeRunning: Bool
  let agentRuntimeExpectedProtocolVersion: Int
  let agentRuntimeProtocolVersion: Int?
  let agentRuntimeVersion: String?
}
