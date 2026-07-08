import SwiftUI

/// "Where I learn, and where I work." — mockup `apps.html`, fully live-wired.
///
/// The two sides of Omi's app surface, rendered with the REAL colored brand
/// logos and the REAL connect popups:
///   • LEFT  "Sources I learn from" — the real `ImportConnector.all`, each row
///     showing its true `ConnectorBrandIcon`. "Connect" opens the real
///     `ImportConnectorSheet` (calendar / Gmail / X OAuth / Apple Notes / local
///     files / ChatGPT + Claude memory import). Live status comes from
///     `ImportConnectorStatusStore`.
///   • RIGHT "Places I work" — the real `MemoryExportDestination.allCases`, each
///     row showing its true `ConnectorBrandIcon`. "Connect" opens the real
///     `ConnectDestinationSheet` (which itself routes to
///     `MemoryExportDestinationSheet` for single destinations, or the grouped
///     Claude/ChatGPT picker). Live status comes from `MemoryExportService`.
///
/// This page never invents connectors, destinations, logos, or statuses — it
/// only reflects what those real sources report, and it drives the exact same
/// sheets the full Apps page (nav index 8) uses.
@MainActor
struct RedesignAppsPage: View {
  @ObservedObject var appProvider: AppProvider
  var appState: AppState? = nil
  @Binding var selectedIndex: Int

  @StateObject private var connectorStatus = ImportConnectorStatusStore()
  @State private var exportStatuses: [MemoryExportDestination: MemoryExportStatus] = [:]

  // Presenting the REAL connect popups. Setting either drives a `.dismissableSheet`.
  @State private var selectedConnector: ImportConnector?
  @State private var selectedDestination: MemoryExportDestination?

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
    // The REAL import popup — same sheet the full Apps page presents.
    .dismissableSheet(item: $selectedConnector) { connector in
      ImportConnectorSheet(
        connector: connector,
        appState: appState,
        statusStore: connectorStatus,
        onDismiss: { selectedConnector = nil })
        .frame(width: 520, height: 620)
    }
    // The REAL export/connect popup — routes to MemoryExportDestinationSheet or
    // the grouped Claude/ChatGPT picker internally.
    .dismissableSheet(item: $selectedDestination) { destination in
      ConnectDestinationSheet(
        destination: destination,
        statuses: $exportStatuses,
        onDismiss: { selectedDestination = nil })
        .frame(width: 520, height: 620)
    }
    // When the export popup closes, pull fresh status so the row flips to
    // "Connected" without needing a page reload.
    .onChange(of: selectedDestination) { _, newValue in
      if newValue == nil {
        Task { exportStatuses = await MemoryExportService.shared.allStatuses() }
      }
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
            brand: connector.brand,
            name: connector.title,
            sub: connector.description,
            connected: snapshot.isConnected,
            connect: { selectedConnector = connector })
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
            brand: destination.brand,
            name: destination.title,
            sub: destination.subtitle,
            connected: exportStatuses[destination]?.isConfigured ?? false,
            connect: { selectedDestination = destination })
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

  /// One row: the REAL colored brand logo (`ConnectorBrandIcon`), the name/sub,
  /// and either a live "Connected" pill or a "Connect" button that opens the
  /// real popup.
  private func connectorRow(
    brand: ConnectorBrand,
    name: String,
    sub: String,
    connected: Bool,
    connect: @escaping () -> Void
  ) -> some View {
    HStack(spacing: 13) {
      ConnectorBrandIcon(brand: brand, size: 34, cornerRadius: 9)

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
        InkButton(title: "Connect", kind: .plain, size: .sm, action: connect)
      }
    }
    .padding(.vertical, 13)
    .frame(maxWidth: .infinity, alignment: .leading)
  }
}
