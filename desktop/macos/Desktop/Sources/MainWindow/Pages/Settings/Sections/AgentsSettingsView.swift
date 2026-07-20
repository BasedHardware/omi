import AppKit
import SwiftUI

/// Settings > AI Agents: see every coding agent Omi can route to, its connected
/// status, one-tap install for the ones that aren't set up, and the default. Makes
/// the Track 1 routing visible and controllable, not just a hidden voice behavior.
struct AgentsSettingsView: View {
  @AppStorage("chatBridgeMode") private var bridgeMode: String = "piMono"
  @State private var refreshTick = 0
  @State private var copiedCommandFor: String?

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 16) {
        header
        VStack(spacing: 10) {
          ForEach(AIProvider.all, id: \.id) { provider in
            agentRow(provider)
          }
        }
        defaultPicker
        routingExplainer
      }
      .padding()
      .id(refreshTick)
    }
    .onAppear { refreshTick += 1 }
  }

  private var header: some View {
    HStack(alignment: .top) {
      VStack(alignment: .leading, spacing: 2) {
        Text("AI Agents")
          .font(.title2).bold()
        Text("Omi routes a spoken task to the best connected agent, with fallback to the others.")
          .font(.callout)
          .foregroundStyle(OmiColors.textTertiary)
      }
      Spacer()
      Button {
        refreshTick += 1
      } label: {
        Label("Refresh", systemImage: "arrow.clockwise")
      }
      .buttonStyle(.bordered)
    }
  }

  private func directed(for provider: AIProvider) -> AgentPillsManager.DirectedProvider? {
    AgentPillsManager.DirectedProvider(rawValue: provider.bridgeModeRawValue)
  }

  private func isConnected(_ provider: AIProvider) -> Bool {
    if let directed = directed(for: provider) {
      return LocalAgentProviderDetector.isAvailable(directed)
    }
    // Omi AI is built in; Claude Code counts when selected as the provider.
    if provider.bridgeModeRawValue == "piMono" { return true }
    return bridgeMode == provider.bridgeModeRawValue
  }

  private func agentRow(_ provider: AIProvider) -> some View {
    let connected = isConnected(provider)
    let installable = directed(for: provider)
    return VStack(alignment: .leading, spacing: 8) {
      HStack(spacing: 10) {
        Circle()
          .fill(connected ? OmiColors.success : OmiColors.textQuaternary)
          .frame(width: 9, height: 9)
        VStack(alignment: .leading, spacing: 1) {
          Text(provider.displayName).font(.headline)
          Text(provider.tagline).font(.caption).foregroundStyle(OmiColors.textTertiary)
        }
        Spacer()
        if bridgeMode == provider.bridgeModeRawValue {
          Text("Default")
            .font(.caption).foregroundStyle(OmiColors.textTertiary)
            .padding(.horizontal, 6).padding(.vertical, 2)
            .background(OmiColors.border, in: Capsule())
        }
        Text(connected ? "Connected" : (installable != nil ? "Not installed" : "Connect in AI Chat"))
          .font(.caption)
          .foregroundStyle(connected ? OmiColors.success : OmiColors.textTertiary)
      }
      if !connected, let installable {
        HStack(spacing: 8) {
          Text(installable.installCommand)
            .font(.system(.caption, design: .monospaced))
            .textSelection(.enabled)
            .padding(6)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(OmiColors.backgroundTertiary, in: RoundedRectangle(cornerRadius: 6))
          Button {
            copyCommand(installable.installCommand, key: provider.id)
          } label: {
            Label(
              copiedCommandFor == provider.id ? "Copied" : "Copy install",
              systemImage: copiedCommandFor == provider.id ? "checkmark" : "doc.on.doc")
          }
          .buttonStyle(.bordered)
          Button {
            if let url = URL(string: installable.docsURL) { NSWorkspace.shared.open(url) }
          } label: {
            Label("Docs", systemImage: "book")
          }
          .buttonStyle(.bordered)
        }
      }
    }
    .padding()
    .background(OmiColors.backgroundRaised, in: RoundedRectangle(cornerRadius: 10))
    .overlay(RoundedRectangle(cornerRadius: 10).stroke(OmiColors.border))
  }

  private var defaultPicker: some View {
    VStack(alignment: .leading, spacing: 6) {
      Text("Default agent")
        .font(.headline)
      Text("Used when the best-fit agents tie, or when you don't name one.")
        .font(.caption).foregroundStyle(OmiColors.textTertiary)
      Picker("", selection: $bridgeMode) {
        ForEach(AIProvider.all, id: \.id) { provider in
          Text(provider.displayName).tag(provider.bridgeModeRawValue)
        }
      }
      .labelsHidden()
      .frame(maxWidth: 280, alignment: .leading)
    }
    .padding()
    .background(OmiColors.backgroundRaised, in: RoundedRectangle(cornerRadius: 10))
    .overlay(RoundedRectangle(cornerRadius: 10).stroke(OmiColors.border))
  }

  private var routingExplainer: some View {
    VStack(alignment: .leading, spacing: 6) {
      Label("How routing works", systemImage: "arrow.triangle.branch")
        .font(.headline)
      Text(
        "Say a task and name an agent (\"use Codex\") to run it there. Say a task without naming one and Omi picks the best connected agent for it, then falls back through the others. Name an agent that isn't installed and Omi shows you how."
      )
      .font(.callout)
      .foregroundStyle(OmiColors.textTertiary)
    }
    .padding()
    .background(OmiColors.backgroundRaised, in: RoundedRectangle(cornerRadius: 10))
    .overlay(RoundedRectangle(cornerRadius: 10).stroke(OmiColors.border))
  }

  private func copyCommand(_ command: String, key: String) {
    NSPasteboard.general.clearContents()
    NSPasteboard.general.setString(command, forType: .string)
    copiedCommandFor = key
    DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
      if copiedCommandFor == key { copiedCommandFor = nil }
    }
  }
}
