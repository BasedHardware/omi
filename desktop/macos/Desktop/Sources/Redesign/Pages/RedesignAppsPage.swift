import SwiftUI

/// "Where I learn, and where I work." — mockup `apps.html`, live-wired.
///
/// A clear, accurate read-only display of the two sides of Omi's app surface:
///   • LEFT  "Sources I learn from" — the real `ImportConnector.all`, with the
///     live connected/Connect state from `ImportConnectorStatusStore`.
///   • RIGHT "Places I work" — the real `MemoryExportDestination.allCases`, with
///     the live configured/Connect state from `MemoryExportService`.
///
/// Tapping "Connect" jumps to the full Apps page (nav index 8), where the actual
/// connect/import/export sheets live. This page never invents connectors,
/// destinations, or statuses — it only reflects what those sources report.
@MainActor
struct RedesignAppsPage: View {
  @ObservedObject var appProvider: AppProvider
  var appState: AppState? = nil
  @Binding var selectedIndex: Int

  @StateObject private var connectorStatus = ImportConnectorStatusStore()
  @State private var exportStatuses: [MemoryExportDestination: MemoryExportStatus] = [:]

  private let connectors = ImportConnector.all
  private let destinations = MemoryExportDestination.allCases

  private var connectedSourceCount: Int {
    connectors.filter { connectorStatus.snapshot(for: $0).isConnected }.count
  }

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 6) {
        Text("Apps").inkEyebrow()
        Text("Where I learn, and where I work.").inkH1()
        Text(
          "Point me at what you already use. I read from the left, and I act inside the tools on the right."
        )
        .inkSmall()
        .frame(maxWidth: 560, alignment: .leading)
        .padding(.bottom, 18)

        HStack(alignment: .top, spacing: 22) {
          sourcesCard
          placesCard
        }
      }
      .frame(maxWidth: 1000, alignment: .leading)
      .frame(maxWidth: .infinity, alignment: .center)
      .padding(.horizontal, 48)
      .padding(.vertical, 44)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(Ink.canvas)
    .task {
      await connectorStatus.refresh()
      exportStatuses = await MemoryExportService.shared.allStatuses()
    }
  }

  // MARK: - Left: Sources I learn from

  private var sourcesCard: some View {
    InkCard {
      VStack(alignment: .leading, spacing: 0) {
        sectionHead(
          title: "Sources I learn from",
          caption: connectedSourceCount == 1 ? "1 connected" : "\(connectedSourceCount) connected")

        ForEach(Array(connectors.enumerated()), id: \.element.id) { index, connector in
          if index > 0 { rowDivider }
          let snapshot = connectorStatus.snapshot(for: connector)
          connectorRow(
            mark: mark(forConnectorID: connector.id),
            name: connector.title,
            sub: connector.description,
            connected: snapshot.isConnected)
        }
      }
      .frame(maxWidth: .infinity, alignment: .leading)
    }
  }

  // MARK: - Right: Places I work

  private var placesCard: some View {
    InkCard {
      VStack(alignment: .leading, spacing: 0) {
        sectionHead(title: "Places I work", caption: "Your memory, anywhere")

        ForEach(Array(destinations.enumerated()), id: \.element.id) { index, destination in
          if index > 0 { rowDivider }
          connectorRow(
            mark: mark(forDestination: destination),
            name: destination.title,
            sub: destination.subtitle,
            connected: exportStatuses[destination]?.isConfigured ?? false)
        }

        HStack(spacing: 8) {
          Image(systemName: "chevron.left.forwardslash.chevron.right")
            .font(.system(size: 11, weight: .medium))
          Text("Connected over MCP · open protocol, your keys.")
        }
        .foregroundColor(Ink.faint)
        .font(InkFont.sans(12))
        .padding(.top, 16)
      }
      .frame(maxWidth: .infinity, alignment: .leading)
    }
  }

  // MARK: - Shared row building blocks

  private func sectionHead(title: String, caption: String) -> some View {
    HStack(alignment: .firstTextBaseline) {
      Text(title).inkH3()
      Spacer(minLength: 12)
      Text(caption).inkCaption()
    }
    .padding(.bottom, 4)
  }

  private var rowDivider: some View {
    Rectangle().fill(Ink.hair).frame(height: 1)
  }

  private func connectorRow(mark: Mark, name: String, sub: String, connected: Bool) -> some View {
    HStack(spacing: 13) {
      MonoChip(mark: mark)

      VStack(alignment: .leading, spacing: 1) {
        Text(name)
          .font(InkFont.sans(14, .medium))
          .foregroundColor(Ink.ink)
          .lineLimit(1)
        if !sub.isEmpty {
          Text(sub)
            .font(InkFont.sans(12))
            .foregroundColor(Ink.faint)
            .lineLimit(1)
            .truncationMode(.tail)
        }
      }
      .frame(maxWidth: .infinity, alignment: .leading)

      if connected {
        HStack(spacing: 6) {
          Circle().fill(Ink.live).frame(width: 7, height: 7)
          Text("Connected").font(InkFont.sans(12.5, .medium))
        }
        .foregroundColor(Ink.sentText)
        .fixedSize()
      } else {
        InkButton(title: "Connect", kind: .plain, size: .sm) {
          // The full Apps page (nav index 8) hosts the real connect sheets.
          selectedIndex = 8
        }
      }
    }
    .padding(.vertical, 13)
    .frame(maxWidth: .infinity, alignment: .leading)
  }

  // MARK: - Monochrome brand marks

  /// A monochrome chip mark: either an SF Symbol or a literal glyph (e.g. 𝕏),
  /// falling back to the item's initial. Keeps the whole page on the Ink
  /// monochrome palette instead of pulling in full-color brand logos.
  fileprivate struct Mark {
    var symbol: String? = nil
    var glyph: String? = nil
  }

  private struct MonoChip: View {
    let mark: Mark

    var body: some View {
      RoundedRectangle(cornerRadius: 9, style: .continuous)
        .fill(Ink.surface)
        .overlay(
          RoundedRectangle(cornerRadius: 9, style: .continuous)
            .strokeBorder(Ink.hair, lineWidth: 1)
        )
        .frame(width: 34, height: 34)
        .overlay(glyphView)
    }

    @ViewBuilder private var glyphView: some View {
      if let symbol = mark.symbol {
        Image(systemName: symbol)
          .font(.system(size: 15, weight: .medium))
          .foregroundColor(Ink.ink)
      } else if let glyph = mark.glyph {
        Text(glyph)
          .font(.system(size: 16, weight: .semibold))
          .foregroundColor(Ink.ink)
      }
    }
  }

  private func mark(forConnectorID id: String) -> Mark {
    switch id {
    case "calendar": return Mark(symbol: "calendar")
    case "email": return Mark(symbol: "envelope")
    case "local-files": return Mark(symbol: "folder")
    case "apple-notes": return Mark(symbol: "note.text")
    case "x": return Mark(glyph: "𝕏")
    case "chatgpt": return Mark(symbol: "bubble.left.and.bubble.right")
    case "claude": return Mark(symbol: "sparkles")
    default: return Mark(glyph: String(id.prefix(1)).uppercased())
    }
  }

  private func mark(forDestination destination: MemoryExportDestination) -> Mark {
    switch destination {
    case .notion: return Mark(symbol: "doc.text")
    case .obsidian: return Mark(symbol: "mountain.2")
    case .chatgpt: return Mark(symbol: "bubble.left.and.bubble.right")
    case .claude: return Mark(symbol: "sparkles")
    case .gemini: return Mark(symbol: "sparkle")
    case .agents: return Mark(glyph: "🤖")
    case .claudeCode: return Mark(symbol: "terminal")
    case .codex: return Mark(symbol: "chevron.left.forwardslash.chevron.right")
    case .openclaw: return Mark(symbol: "pawprint")
    case .hermes: return Mark(symbol: "bolt.horizontal")
    }
  }
}
