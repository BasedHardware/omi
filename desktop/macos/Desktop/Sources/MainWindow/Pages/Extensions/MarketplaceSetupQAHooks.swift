import SwiftUI

/// Screen-scoped, opt-in loopback fixtures. These cannot inspect or mutate the
/// user's real extension store, and cannot target a public provider.
enum MarketplaceSetupQA {
  static let fixtureID = "local.qa/marketplace-setup"

  static var isEnabled: Bool {
    guard DesktopAutomationLaunchOptions.isEnabled,
      let isolated = LocalExtensionQAStorage.root(
        enabled: ProcessInfo.processInfo.environment["OMI_EXTENSION_QA_ISOLATION"] == "1",
        isNonProduction: AppBuild.isNonProduction,
        bundleIdentifier: AppBuild.bundleIdentifier,
        temporaryDirectory: FileManager.default.temporaryDirectory)
    else { return false }
    return LocalSkillsStore.rootURL == isolated
  }

  static func fixture(url: String) throws -> ExtensionCatalog.Entry {
    guard let parsed = URLComponents(string: url), parsed.scheme == "http", parsed.host == "127.0.0.1",
      let port = parsed.port, (1...65_535).contains(port), parsed.user == nil, parsed.password == nil,
      parsed.query == nil, parsed.fragment == nil, parsed.path == "/mcp"
    else { throw LocalMcpStore.storeError("The setup fixture requires an HTTP loopback /mcp endpoint") }
    return ExtensionCatalog.Entry(
      id: fixtureID, name: "MCP Setup QA", subtitle: "Remote",
      detail: "Controlled loopback MCP server for marketplace setup verification",
      publisher: "Local QA fixture",
      install: .mcpRemote(url: url, transport: "http", secretHeader: nil))
  }

  @MainActor
  static func installActions(
    session: ExtensionInstallSession,
    performInstall: @escaping @MainActor () -> Void
  ) {
    let registry = DesktopAutomationActionRegistry.shared
    registry.register(
      name: "marketplace_setup_fixture_install",
      effects: [.localState, .localArtifact, .networkOrModel],
      summary: "Press Install in the mounted isolated marketplace fixture",
      category: "test", surfaces: ["apps"],
      sideEffects: ["writes only the named QA extension store", "refreshes extension projection"]
    ) { _ in
      performInstall()
      return ["install_requested": "true"]
    }
    registry.register(
      name: "marketplace_setup_fixture_snapshot", effects: [],
      summary: "Read shape-only installation state from the mounted marketplace fixture",
      category: "read", surfaces: ["apps"]
    ) { _ in
      let phase: String
      switch session.phase {
      case .ready: phase = "ready"
      case .installing: phase = "installing"
      case .failed: phase = "failed"
      case .serverSetup: phase = "server_setup"
      case .skillInstalled: phase = "skill_installed"
      case .closed: phase = "closed"
      }
      return [
        "phase": phase,
        "installed_server": session.installedServer?.name ?? "",
        "has_error": session.errorText == nil ? "false" : "true",
        "isolated_storage": "true",
      ]
    }
  }

  @MainActor
  static func removeInstallActions() {
    DesktopAutomationActionRegistry.shared.unregister("marketplace_setup_fixture_install")
    DesktopAutomationActionRegistry.shared.unregister("marketplace_setup_fixture_snapshot")
  }
}

@MainActor
private struct MarketplaceSetupFixtureModifier: ViewModifier {
  let onSelect: (ExtensionCatalog.Entry) -> Void

  func body(content: Content) -> some View {
    content
      .onAppear {
        guard MarketplaceSetupQA.isEnabled else { return }
        DesktopAutomationActionRegistry.shared.register(
          name: "marketplace_setup_show_fixture", effects: [.localState, .networkOrModel],
          summary: "Open a loopback marketplace fixture in the mounted Apps page",
          params: ["url"], category: "test", surfaces: ["apps"]
        ) { parameters in
          let entry = try MarketplaceSetupQA.fixture(url: parameters["url"] ?? "")
          onSelect(entry)
          return ["fixture_opened": "true", "isolated_storage": "true"]
        }
      }
      .onDisappear {
        guard MarketplaceSetupQA.isEnabled else { return }
        DesktopAutomationActionRegistry.shared.unregister("marketplace_setup_show_fixture")
      }
  }
}

extension View {
  @MainActor
  func marketplaceSetupFixture(onSelect: @escaping (ExtensionCatalog.Entry) -> Void) -> some View {
    modifier(MarketplaceSetupFixtureModifier(onSelect: onSelect))
  }
}
