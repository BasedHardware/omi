import AppKit
import Foundation

/// A single user-facing consent question for one actuating tool invocation.
struct AgentToolConsentRequest: Equatable, Sendable {
  let toolName: String
  let title: String
  let message: String
  let approveButtonTitle: String
  let denyButtonTitle: String
}

enum AgentToolConsentDecision: Equatable, Sendable {
  case approved
  case denied
}

/// Records the prompts a run actually raised so a test can assert the user was
/// asked, not only that execution was refused.
@MainActor
final class AgentToolConsentLog {
  private(set) var requests: [AgentToolConsentRequest] = []

  func record(_ request: AgentToolConsentRequest) {
    requests.append(request)
  }
}

/// Owner identity answers *who* is running a tool. This gate answers *whether the
/// user agreed*, which is the only question that stops screen-injected tool calls.
/// Every actuating surface asks it through the same seam so a new caller cannot
/// acquire an unprompted actuation path.
@MainActor
enum AgentToolConsentGate {
  typealias Presenter = @MainActor (AgentToolConsentRequest) -> AgentToolConsentDecision

  private static var presenter: Presenter = AgentToolConsentGate.presentModalConfirmation

  static func confirm(_ request: AgentToolConsentRequest) -> Bool {
    presenter(request) == .approved
  }

  /// Test seam. Production never installs a presenter, so the modal below is the
  /// only way an approval can be produced in a shipped build. Passing `nil`
  /// restores the modal.
  static func setPresenterForTesting(_ presenter: Presenter?) {
    Self.presenter = presenter ?? AgentToolConsentGate.presentModalConfirmation
  }

  static func recordedRequestsPresenter(
    _ decision: AgentToolConsentDecision,
    into log: AgentToolConsentLog
  ) -> Presenter {
    { request in
      log.record(request)
      return decision
    }
  }

  private static func presentModalConfirmation(
    _ request: AgentToolConsentRequest
  ) -> AgentToolConsentDecision {
    let alert = NSAlert()
    alert.messageText = request.title
    alert.informativeText = request.message
    alert.alertStyle = .critical
    // The refusing button is added first so it is the default: pressing Return
    // on a prompt the user did not expect never actuates.
    alert.addButton(withTitle: request.denyButtonTitle)
    alert.addButton(withTitle: request.approveButtonTitle)
    NSApp.activate(ignoringOtherApps: true)
    return alert.runModal() == .alertSecondButtonReturn ? .approved : .denied
  }
}

/// Execution-time consent classification. The TypeScript coordinator policy
/// (`agent/src/runtime/desktop-tool-policy.ts`) classifies these same tools
/// `dispatch_required`; this table is the enforcing mirror consulted on the
/// actual Swift execution path rather than an advisory verdict the model may
/// choose to request.
enum AgentToolConsentPolicy {
  /// Tools whose consent question depends only on the tool name and its
  /// arguments, checked for every tool at the chat dispatch funnel.
  static func request(forToolNamed name: String, arguments: [String: Any])
    -> AgentToolConsentRequest?
  {
    switch name {
    case "fill_cloud_connector_form":
      return cloudConnectorRequest(arguments: arguments)
    default:
      return nil
    }
  }

  static func cloudConnectorRequest(arguments: [String: Any]) -> AgentToolConsentRequest {
    let provider = ((arguments["provider"] as? String) ?? "").lowercased()
    let providerLabel: String
    switch provider {
    case "claude": providerLabel = "Claude"
    case "chatgpt": providerLabel = "ChatGPT"
    default: providerLabel = "cloud AI"
    }
    let serverURL = (arguments["server_url"] as? String) ?? "(none)"
    let connectorName = (arguments["name"] as? String) ?? "Omi Memory"
    let submits = (arguments["submit"] as? Bool) ?? false
    let action =
      submits
      ? "fill in and submit a connector form in your signed-in \(providerLabel) account"
      : "fill in a connector form in your signed-in \(providerLabel) account"
    return AgentToolConsentRequest(
      toolName: "fill_cloud_connector_form",
      title: "Connect your \(providerLabel) account to an external server?",
      message: """
        Omi wants to \(action).

        Connector name: \(connectorName)
        Remote MCP server URL: \(serverURL)

        Approving gives that server ongoing access through your \(providerLabel) \
        account. Only continue if you recognize this address and asked Omi to add it.
        """,
      approveButtonTitle: submits ? "Connect" : "Fill Form",
      denyButtonTitle: "Don't Connect")
  }

  static func sqlWriteRequest(query: String) -> AgentToolConsentRequest {
    AgentToolConsentRequest(
      toolName: "execute_sql",
      title: "Let Omi change your local data?",
      message: """
        Omi wants to run a query that modifies your local Omi database:

        \(query)

        Approving runs it once. Only continue if you asked Omi to make this change.
        """,
      approveButtonTitle: "Run Query",
      denyButtonTitle: "Don't Run")
  }

  static func syntheticInputArmingRequest() -> AgentToolConsentRequest {
    AgentToolConsentRequest(
      toolName: "point_click",
      title: "Let Omi click for you in this voice session?",
      message: """
        Omi wants to move your pointer and click at coordinates it chooses, based \
        on what it sees on your screen.

        Approving allows clicking until this voice session ends. Omi cannot turn \
        this on by itself.
        """,
      approveButtonTitle: "Allow for This Session",
      denyButtonTitle: "Don't Allow")
  }

  static let cloudConnectorDeclinedResult =
    "Error: the user declined to connect this server. Do not retry; ask the user to add the connector themselves."

  static let sqlWriteDeclinedResult =
    "Error: the user did not approve this write. execute_sql is read-only unless the user approves each change."

  static let syntheticInputDeclinedResult =
    "Could not click: the user has not enabled clicking for this voice session."
}
