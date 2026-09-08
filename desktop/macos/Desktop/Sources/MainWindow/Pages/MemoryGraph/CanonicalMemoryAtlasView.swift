import AppKit
import OSLog
import OmiSupport
import OmiTheme
import SwiftUI

private let memoryAtlasLogger = Logger(
  subsystem: Bundle.main.bundleIdentifier ?? "com.omi.desktop",
  category: "MemoryAtlas"
)

extension Notification.Name {
  static let desktopAutomationOpenMemoryAtlasRequested = Notification.Name(
    "desktopAutomationOpenMemoryAtlasRequested"
  )
  static let desktopAutomationMemoryAtlasViewportRequested = Notification.Name(
    "desktopAutomationMemoryAtlasViewportRequested"
  )
  static let desktopAutomationMemoryAtlasTimeRequested = Notification.Name(
    "desktopAutomationMemoryAtlasTimeRequested"
  )
  /// Selecting an entity or a connection is otherwise only reachable by
  /// clicking the canvas, which puts the inspector out of reach of every
  /// cursor-free check.
  static let desktopAutomationMemoryAtlasSelectRequested = Notification.Name(
    "desktopAutomationMemoryAtlasSelectRequested"
  )
  /// Going into a neighbourhood is otherwise only reachable by clicking its
  /// caption, which is a small target computed from the live camera — so the
  /// one interaction the territory layer exists for was the one no check could
  /// reach.
  static let desktopAutomationMemoryAtlasRegionRequested = Notification.Name(
    "desktopAutomationMemoryAtlasRegionRequested"
  )
}

// MARK: - Canonical Atlas Containers

/// Holds the canvas until a complete graph is ready, so the first visit cannot
/// paint a synthetic owner as the whole map.
private struct CanonicalMemoryAtlasLoadGate<Content: View>: View {
  @ObservedObject var viewModel: MemoryGraphViewModel
  @ViewBuilder var content: () -> Content

  var body: some View {
    switch MemoryAtlasSurfacePresentation.phase(
      isLoading: viewModel.isLoading,
      isEmpty: viewModel.isEmpty,
      hasProjection: viewModel.canonicalAtlasProjection != nil,
      hasAttemptedLoad: viewModel.hasAttemptedCanonicalAtlasLoad
    ) {
    case .loading:
      ZStack {
        Color.clear
        ProgressView()
          .controlSize(.regular)
          .tint(Ink.secondary)
      }
      .frame(maxWidth: .infinity, maxHeight: .infinity)
      .accessibilityIdentifier("canonical_memory_atlas_loading")
    case .empty:
      VStack(spacing: OmiSpacing.sm) {
        Image(systemName: "brain")
          .scaledFont(size: OmiType.heading)
          .foregroundColor(Ink.secondary)
        Text("Brain map will appear once enough linked memories are available.")
          .scaledFont(size: 12.5)
          .foregroundColor(Ink.secondary)
          .multilineTextAlignment(.center)
      }
      .padding(OmiSpacing.lg)
      .frame(maxWidth: .infinity, maxHeight: .infinity)
      .accessibilityIdentifier("canonical_memory_atlas_empty")
    case .ready:
      content()
    }
  }
}

struct CanonicalMemoryAtlasPage: View {
  @ObservedObject var viewModel: MemoryGraphViewModel
  let onBack: () -> Void
  let evidenceProvider: ([String]) async -> [MemoryAtlasEvidence]
  /// Opens a cited memory on the Memories surface this page came from.
  let onOpenMemory: (String) -> Void

  /// Reads the memoized snapshot drawn below, so the counts cannot drift.
  private var headerCountLabel: String {
    if let projection = viewModel.canonicalAtlasProjection {
      return MemoryAtlasLayoutEngine.countLabel(
        entities: projection.snapshot.nodes.filter { !$0.isCatalog }.count,
        memories: projection.snapshot.nodes.filter(\.isCatalog).count,
        connections: projection.snapshot.edges.count)
    }
    return MemoryAtlasLayoutEngine.countLabel(
      entities: viewModel.graphResponse.atlasNodes.count,
      memories: viewModel.graphResponse.catalogNodes?.count,
      connections: viewModel.graphResponse.edges.count)
  }

  var body: some View {
    VStack(spacing: 0) {
      HStack(spacing: 12) {
        Button(action: onBack) {
          Label("Memories", systemImage: "chevron.left")
            .scaledFont(size: 12, weight: .semibold)
            .foregroundColor(Ink.secondary)
            .padding(.horizontal, 10)
            .frame(height: 30)
            .glassChip()
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("memory_atlas_back_to_memories")

        // "Brain Map" everywhere the user can see it: the atlas replaces the
        // legacy graph on the destination that already had that name, so
        // introducing a second name for the same place only splits the domain
        // vocabulary. "Atlas" survives in type and symbol names only.
        Text("Brain Map")
          .scaledFont(size: 17, weight: .semibold)
          .foregroundColor(Ink.primary)

        Spacer()

        // Show the semantic map and the complete canonical-memory catalog as
        // distinct counts; catalog records are visible but never fake edges.
        Text(headerCountLabel)
          .scaledFont(size: 12)
          .foregroundColor(Ink.secondary)
          .accessibilityIdentifier("memory_atlas_header_counts")
      }
      .padding(.horizontal, 18)
      .frame(height: 44)
      .background(Ink.rowFill)

      Divider().overlay(Ink.separator.opacity(0.25))

      CanonicalMemoryAtlasLoadGate(viewModel: viewModel) {
        CanonicalMemoryAtlasSurface(
          graph: viewModel.canonicalAtlasProjection?.graph ?? viewModel.graphResponse,
          projection: viewModel.canonicalAtlasProjection,
          compact: false,
          evidenceProvider: evidenceProvider,
          onOpenMemory: onOpenMemory,
          onRebuild: { Task { await viewModel.rebuildCanonicalAtlas() } },
          isRebuilding: viewModel.isRebuilding,
          onLeave: onBack
        )
      }
    }
    .background(Color.clear)
    .accessibilityIdentifier("canonical_memory_atlas_page")
    .task { await viewModel.prepareCanonicalAtlas() }
    .onAppear {
      memoryAtlasLogger.info(
        "Atlas page opened nodes=\(viewModel.graphResponse.atlasNodes.count, privacy: .public) edges=\(viewModel.graphResponse.edges.count, privacy: .public)"
      )
    }
  }
}

/// Memory hub presentation of the atlas.
///
/// The hub already owns navigation chrome (the Memory menu selects the
/// destination), so this variant renders the surface full-bleed instead of
/// stacking the page's own back/title bar underneath the hub bar. It is the
/// assertion-backed counterpart to `MemoryGraphPage`, which fills the same tab
/// for users still on the legacy graph.
struct CanonicalMemoryAtlasTabView: View {
  @ObservedObject var viewModel: MemoryGraphViewModel
  let evidenceProvider: ([String]) async -> [MemoryAtlasEvidence]
  /// Opens a cited memory on the hub's Memories destination.
  let onOpenMemory: (String) -> Void
  @Binding var searchText: String
  var showsSearchField = true
  /// Where Escape goes once the map has nothing of its own left to undo.
  var onLeave: (() -> Void)?

  var body: some View {
    CanonicalMemoryAtlasLoadGate(viewModel: viewModel) {
      CanonicalMemoryAtlasSurface(
        graph: viewModel.canonicalAtlasProjection?.graph ?? viewModel.graphResponse,
        projection: viewModel.canonicalAtlasProjection,
        compact: false,
        evidenceProvider: evidenceProvider,
        onOpenMemory: onOpenMemory,
        onRebuild: { Task { await viewModel.rebuildCanonicalAtlas() } },
        isRebuilding: viewModel.isRebuilding,
        externalSearchText: $searchText,
        showsSearchField: showsSearchField,
        onLeave: onLeave
      )
    }
    .background(Color.clear)
    .accessibilityIdentifier("canonical_memory_atlas_tab")
    .task { await viewModel.prepareCanonicalAtlas() }
    .onAppear {
      memoryAtlasLogger.info(
        "Atlas tab opened nodes=\(viewModel.graphResponse.atlasNodes.count, privacy: .public) edges=\(viewModel.graphResponse.edges.count, privacy: .public)"
      )
    }
  }
}

// MARK: - Interactive Atlas Surface

private struct CanonicalMemoryAtlasSurface: View {
  let graph: KnowledgeGraphResponse
  /// Normal app surfaces pass the prebuilt projection from their view model.
  /// Export previews retain the lightweight fallback so they remain
  /// self-contained fixtures.
  let projection: MemoryAtlasProjection?
  let compact: Bool
  /// Resolves the memory ids an entity cites into readable evidence for the
  /// inspector. The surface stays independent of the memories layer; callers
  /// that have no memories to offer (offscreen exports) return nothing.
  ///
  /// Asynchronous because resolving a citation is a cache read, not a scan of
  /// whatever the memories list happens to be showing.
  let evidenceProvider: ([String]) async -> [MemoryAtlasEvidence]
  /// Leaves the atlas for a cited memory. Absent on surfaces with nowhere to
  /// go (offscreen exports, the inline preview).
  let onOpenMemory: ((String) -> Void)?
  /// Regenerating the server-side graph. Absent on surfaces that have no
  /// view model to drive it (the inline preview, offscreen export renders).
  let onRebuild: (() -> Void)?
  let isRebuilding: Bool
  var externalSearchText: Binding<String>? = nil
  var showsSearchField = true
  /// Where Escape goes once the map itself has nothing left to undo. Absent on
  /// surfaces with nowhere to go, which is how those keep passing the key on.
  let onLeave: (() -> Void)?
  private let snapshot: MemoryAtlasSnapshot
  private let renderPlanCache: MemoryAtlasRenderPlanCache
  /// The cursor at which each relationship can first be painted. Precomputing
  /// this avoids walking every edge again on every 30 Hz replay frame.
  private let connectionBirthFractions: [Double]
  /// Deterministic offscreen renders (ViewExporter QA) pin the time cursor and
  /// suppress auto-play so the timeline captures a stable frame.
  private let previewTimeCursor: Double?
  private let previewEvidence: [MemoryAtlasEvidence]

  @State private var localSearchText = ""
  @State private var selectedNodeID: String?
  /// Set when the user clicked a painted connection rather than an entity.
  /// `selectedNodeID` still holds one endpoint so the map keeps its existing
  /// neighborhood emphasis; this only redirects the inspector to the
  /// relationship itself.
  @State private var selectedEdgeID: String?
  /// Entities the user followed connections away from, most recent last.
  @State private var selectionTrail: [String] = []
  @State private var evidence: [MemoryAtlasEvidence] = []
  @State private var evidenceIsLoading = false
  /// The ids the current evidence answers, so "how many are missing" compares
  /// against what was actually asked for rather than the live selection.
  @State private var requestedEvidenceIDs: [String] = []
  /// The neighbourhood the user went into, if any.
  ///
  /// Entering a place is a mode, not just a camera move. Inside one, the map
  /// stops drawing everyone else's coastline and gives the entities their names
  /// back — which is the trade the territory layer makes in the first place:
  /// names are hidden under a caption while you are reading the map as a whole,
  /// and handed back the moment you pick somewhere to look.
  @State private var enteredRegionID: Int?
  /// The zoom at which the user counts as having zoomed back out of the place
  /// they went into. Set from the camera entering actually used, because a
  /// fixed threshold throws the user out of any island big enough to be framed
  /// below it — which is every island on a map with only a few regions on it.
  @State private var departureZoom: CGFloat?
  @State private var zoom: CGFloat = 1
  @State private var settledZoom: CGFloat = 1
  @State private var pan: CGSize = .zero
  @State private var settledPan: CGSize = .zero
  @State private var viewportSize: CGSize = .zero
  @State private var isCameraMoving = false
  @State private var matchingNodeIDs: Set<String>? = nil
  @State private var matchingEdges: [MemoryAtlasEdgePlacement]? = nil
  /// Normalized as-of position on the time axis, 1 == now (show everything).
  @State private var timeCursor: Double = 1
  @State private var isTimePlaying = false
  @State private var didAutoplay = false
  @State private var playbackTask: Task<Void, Never>? = nil
  @FocusState private var searchIsFocused: Bool
  /// Persisted: once the user pauses or scrubs the timeline, the atlas stops
  /// auto-playing its growth animation on open. Playing all the way through is
  /// the delightful default; interrupting it is an explicit opt-out.
  @AppStorage("memory_atlas_timeline_autoplay") private var autoplayEnabled = true
  @Environment(\.accessibilityReduceMotion) private var reduceMotion

  init(
    graph: KnowledgeGraphResponse,
    projection: MemoryAtlasProjection? = nil,
    compact: Bool,
    evidenceProvider: @escaping ([String]) async -> [MemoryAtlasEvidence] = { _ in [] },
    onOpenMemory: ((String) -> Void)? = nil,
    onRebuild: (() -> Void)? = nil,
    isRebuilding: Bool = false,
    externalSearchText: Binding<String>? = nil,
    showsSearchField: Bool = true,
    onLeave: (() -> Void)? = nil,
    previewTimeCursor: Double? = nil,
    /// Deterministic offscreen renders open the inspector, which is otherwise
    /// only reachable by tapping the canvas.
    previewSelectedNodeID: String? = nil,
    /// Selecting a connection, for the render that has to prove the
    /// relationship inspector exists.
    previewSelectedEdgeID: String? = nil,
    /// Offscreen renders capture a frame before an asynchronous cache read
    /// could land, so the export seeds the inspector's evidence directly
    /// instead of photographing a spinner.
    previewEvidence: [MemoryAtlasEvidence] = []
  ) {
    self.graph = graph
    self.projection = projection
    self.compact = compact
    self.evidenceProvider = evidenceProvider
    self.onOpenMemory = onOpenMemory
    self.onRebuild = onRebuild
    self.isRebuilding = isRebuilding
    self.externalSearchText = externalSearchText
    self.showsSearchField = showsSearchField
    self.onLeave = onLeave
    self.previewTimeCursor = previewTimeCursor
    self.previewEvidence = previewEvidence
    _timeCursor = State(initialValue: previewTimeCursor ?? 1)
    _selectedNodeID = State(initialValue: previewSelectedNodeID)
    _selectedEdgeID = State(initialValue: previewSelectedEdgeID)
    _evidence = State(initialValue: previewEvidence)
    _requestedEvidenceIDs = State(initialValue: previewEvidence.map(\.id))
    let atlasSnapshot: MemoryAtlasSnapshot
    if let projection {
      atlasSnapshot = projection.snapshot
    } else {
      let givenName = AuthService.shared.givenName.trimmingCharacters(in: .whitespacesAndNewlines)
      let displayName = AuthService.shared.displayName.trimmingCharacters(in: .whitespacesAndNewlines)
      let ownerName = givenName.isEmpty ? displayName : givenName
      atlasSnapshot = MemoryAtlasSnapshotCache.shared.snapshot(
        for: graph,
        userName: ownerName.isEmpty ? nil : ownerName
      )
    }
    snapshot = atlasSnapshot
    renderPlanCache = projection?.renderPlanCache ?? MemoryAtlasRenderPlanCache(snapshot: atlasSnapshot)
    if let projection {
      connectionBirthFractions = projection.connectionBirthFractions
    } else if let timeline = atlasSnapshot.timeline {
      connectionBirthFractions = atlasSnapshot.edges.map { placement in
        let endpointBirth =
          [placement.edge.sourceId, placement.edge.targetId].map { nodeID in
            nodeID == atlasSnapshot.anchorNodeID ? 0 : (timeline.playbackFractionByNodeID[nodeID] ?? 1)
          }.max() ?? 1
        return max(timeline.fraction(for: placement.edge.createdAt), endpointBirth)
      }
      .sorted()
    } else {
      connectionBirthFractions = []
    }
  }

  private var selectedNode: MemoryAtlasNodePlacement? {
    guard let selectedNodeID else { return nil }
    return snapshot.nodeByID[selectedNodeID]
  }

  private var selectedEdges: [MemoryAtlasEdgePlacement] {
    guard let selectedNodeID else { return [] }
    return snapshot.edgesByNodeID[selectedNodeID] ?? []
  }

  /// Selecting an edge always anchors `selectedNodeID` to one of its endpoints,
  /// so the lookup stays within that node's degree instead of the whole graph.
  private var selectedEdge: MemoryAtlasEdgePlacement? {
    guard let selectedEdgeID else { return nil }
    return selectedEdges.first { $0.id == selectedEdgeID }
  }

  /// The memory ids the current selection cites, newest-relationship-first and
  /// de-duplicated. An edge answers for itself; an entity answers for all of
  /// its connections.
  private var citedMemoryIDs: [String] {
    if let selectedEdge { return selectedEdge.edge.memoryIds }
    var seen = Set<String>()
    var ordered: [String] = []
    // Seed from the selected entity's own memory IDs first. The backend
    // writes memory_ids directly onto every extracted node independently of
    // its edges, so isolated entities — and memories that mention an entity
    // without producing a relationship — show no evidence if only edge IDs
    // are collected.
    if let selectedNode {
      for id in selectedNode.node.memoryIds where seen.insert(id).inserted {
        ordered.append(id)
      }
    }
    for id in selectedEdges.flatMap(\.edge.memoryIds) where seen.insert(id).inserted {
      ordered.append(id)
    }
    return ordered
  }

  /// Changing either half of the selection is a new evidence question.
  private var evidenceSelectionKey: String {
    "\(selectedNodeID ?? "")|\(selectedEdgeID ?? "")"
  }

  private var unresolvedEvidenceCount: Int {
    evidenceIsLoading ? 0 : max(0, requestedEvidenceIDs.count - evidence.count)
  }

  private var recentConnectionCount: Int {
    let threshold = Date().addingTimeInterval(-7 * 24 * 60 * 60)
    return graph.edges.filter { $0.createdAt >= threshold }.count
  }

  private var timeline: MemoryAtlasTimeline? { snapshot.timeline }

  /// The active as-of date, or `nil` when the cursor is parked at "now" (which
  /// means: render the whole atlas, no time filtering).
  private var asOfDate: Date? {
    guard let timeline, timeCursor < 0.9995 else { return nil }
    return timeline.date(atFraction: timeCursor)
  }

  private var visibleEntityCount: Int {
    guard let timeline, timeCursor < 0.9995 else { return snapshot.nodes.count }
    let anchorIsOutsideCursor = snapshot.anchorNodeID.map { !timeline.isVisible(nodeID: $0, at: timeCursor) } ?? false
    return timeline.visibleNodeCount(at: timeCursor) + (anchorIsOutsideCursor ? 1 : 0)
  }

  private var visibleConnectionCount: Int {
    guard timeline != nil, timeCursor < 0.9995 else { return snapshot.edges.count }
    return firstConnectionBirthIndex(after: timeCursor)
  }

  private func firstConnectionBirthIndex(after fraction: Double) -> Int {
    var lower = 0
    var upper = connectionBirthFractions.count
    while lower < upper {
      let middle = lower + (upper - lower) / 2
      if connectionBirthFractions[middle] > fraction {
        upper = middle
      } else {
        lower = middle + 1
      }
    }
    return lower
  }

  private var recentConnectionLabel: String {
    recentConnectionCount > 99 ? "99+ new connections" : "\(recentConnectionCount) new connections"
  }

  private var searchBinding: Binding<String> {
    externalSearchText ?? $localSearchText
  }

  private var searchText: String {
    searchBinding.wrappedValue
  }

  var body: some View {
    // The inspector is a sibling of the whole map, not an overlay on it: the
    // canvas keeps its full height and the map simply narrows, so opening an
    // entity never hides the part of the map you were looking at.
    HStack(spacing: 0) {
      mapColumn

      if !compact, let selectedNode {
        inspector(anchoredAt: selectedNode)
          .transition(.move(edge: .trailing).combined(with: .opacity))
      }
    }
    .animation(OmiMotion.gated(.easeOut(duration: 0.18)), value: selectedNodeID)
    .onChange(of: searchText) { _, query in
      updateSearchMatches(query)
    }
    .task(id: evidenceSelectionKey) { await loadEvidence() }
    .onEscapeKey(priority: .content) {
      guard !compact else { return false }
      return dismissTopmostState()
    }
  }

  @ViewBuilder
  private func inspector(anchoredAt placement: MemoryAtlasNodePlacement) -> some View {
    if let selectedEdge {
      relationshipPanel(for: selectedEdge, anchor: placement)
    } else {
      detailPanel(for: placement)
    }
  }

  /// Resolves the selection's citations through the provider.
  ///
  /// Stale evidence is cleared before the read rather than after it, so
  /// switching entities never shows the previous entity's memories under the
  /// new entity's name while the lookup is in flight.
  private func loadEvidence() async {
    guard previewEvidence.isEmpty else { return }
    let ids = citedMemoryIDs
    guard !ids.isEmpty else {
      evidence = []
      requestedEvidenceIDs = []
      evidenceIsLoading = false
      return
    }
    evidence = []
    requestedEvidenceIDs = ids
    evidenceIsLoading = true
    let resolved = await evidenceProvider(ids)
    guard !Task.isCancelled else { return }
    evidence = resolved
    evidenceIsLoading = false
  }

  private var mapColumn: some View {
    VStack(spacing: 0) {
      atlasToolbar

      GeometryReader { proxy in
        let plan = renderPlanCache.makePlan(
          viewportSize: proxy.size,
          zoom: zoom,
          pan: pan,
          compact: compact,
          selectedNodeID: selectedNodeID,
          matchingNodeIDs: matchingNodeIDs,
          matchingEdges: matchingEdges,
          asOf: asOfDate,
          timeline: timeline,
          timeCursor: timeCursor,
          isCameraMoving: isCameraMoving
        )

        // One placement pass per frame, shared by the tint the canvas paints
        // and the buttons laid over it, so the two cannot disagree about where
        // a region's name is.
        let (regions, quietened) = territory(in: proxy.size, plan: plan)

        ZStack {
          Color.black  // The mat. See `.glassMediaMat` on `.clipped()` below.

          atlasCanvas(size: proxy.size, plan: plan, regions: regions, quietened: quietened)
            // Camera gestures belong to the painted atlas only. Keeping them
            // off the enclosing ZStack prevents a click on zoom, playback, or
            // the selection strip from also selecting a node behind the control.
            .contentShape(Rectangle())
            .gesture(panGesture)
            .simultaneousGesture(magnificationGesture(in: proxy.size))
            .simultaneousGesture(
              SpatialTapGesture().onEnded { value in
                selectAtlasElement(at: value.location, in: proxy.size, plan: plan)
              }
            )

          if !isCameraMoving {
            ForEach(plan.interactiveNodes) { placement in
              nodeButton(
                placement,
                size: proxy.size,
                relatedNodeIDs: plan.relatedNodeIDs,
                showLabel: plan.labelNodeIDs.contains(placement.id)
                  && !quietened.contains(placement.id),
                labelAbove: plan.labelAboveNodeIDs.contains(placement.id)
              )
            }

            // Above the entities: a region name that an entity's own label
            // could cover would be the one label on the map with nothing
            // underneath it to explain itself.
            neighbourhoodCaptions(regions: regions)
          }

          if hasNoSearchMatches {
            searchEmptyState
              .allowsHitTesting(false)
          }

          zoomControls
            .padding(compact ? 8 : 12)
            .padding(.bottom, selectedNode == nil ? 0 : (compact ? 50 : 56))
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomLeading)

          // Compact surfaces have no room for a side panel, so they keep the
          // strip. Wide surfaces use the inspector instead.
          if compact, let selectedNode {
            selectionStrip(for: selectedNode)
              .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottom)
          }

          if !compact {
            MemoryAtlasInputMonitor(
              onScroll: { delta, location in
                scrollZoom(by: delta, anchoredAt: location, in: proxy.size)
              },
              onFocusSearch: { searchIsFocused = true }
            )
            .accessibilityHidden(true)
          }
        }
        .onAppear { viewportSize = proxy.size }
        .onChange(of: proxy.size) { _, newSize in viewportSize = newSize }
        // Zooming back out is leaving the place you were in, pressed or not. Without this the
        // map keeps hiding every other coastline long after the user stopped looking at one,
        // and the only way back is a control they have no reason to know about.
        .onChange(of: zoom) { _, level in
          guard enteredRegionID != nil, let departureZoom, level < departureZoom else { return }
          leaveNeighbourhood()
        }
        // A neighbourhood id belongs to the snapshot that detected it: rebuild and the same
        // ground can return under a different number, or not at all. Being inside a place that
        // no longer exists is a mode with nothing on screen to explain it and no way out.
        .onChange(of: snapshot.neighbourhoods.map(\.id)) { _, regions in
          guard let entered = enteredRegionID, !regions.contains(entered) else { return }
          leaveNeighbourhood()
        }
        // The one dark surface a content page may draw: the map is emissive (light nodes, haloes
        // and labels, like a star chart) and vanished on the panel's near-white ground. The mat
        // also flips the environment so `Ink` resolves *up* for the chrome laid over it.
        .clipped().glassMediaMat()
      }

      VStack(spacing: 0) {
        if !compact, timeline != nil {
          timelineBar
        } else if !compact {
          // No meaningful timestamp spread — keep the legacy legend so the
          // level indicator and type key stay available.
          atlasLegend
        }
      }
    }
    .background(Color.clear)
    .accessibilityElement(children: .contain)
    .accessibilityIdentifier("canonical_memory_atlas")
    .onAppear(perform: maybeAutoplayTimeline)
    .onDisappear { stopPlayback(userInitiated: false) }
    .onReceive(NotificationCenter.default.publisher(for: .desktopAutomationMemoryAtlasViewportRequested)) {
      notification in
      let target = notification.userInfo?["target"] as? String ?? "page"
      let isInlineTarget = target == "inline"
      guard isInlineTarget == compact else { return }
      if notification.userInfo?["reset"] as? Bool == true {
        resetViewport()
        clearSelection()
        return
      }
      if let requestedZoom = notification.userInfo?["zoom"] as? Double {
        updateZoom(CGFloat(requestedZoom))
        memoryAtlasLogger.debug(
          "Automation viewport target=\(target, privacy: .public) zoom=\(requestedZoom, privacy: .public)"
        )
      }
      let requestedPanX = notification.userInfo?["pan_x"] as? Double
      let requestedPanY = notification.userInfo?["pan_y"] as? Double
      if requestedPanX != nil || requestedPanY != nil {
        pan = CGSize(
          width: CGFloat(requestedPanX ?? Double(pan.width)),
          height: CGFloat(requestedPanY ?? Double(pan.height))
        )
        settledPan = pan
      }
    }
    .onReceive(
      NotificationCenter.default.publisher(for: .desktopAutomationMemoryAtlasRegionRequested)
    ) { notification in
      let target = notification.userInfo?["target"] as? String ?? "page"
      guard (target == "inline") == compact else { return }
      if notification.userInfo?["leave"] as? Bool == true { return leaveNeighbourhood() }
      guard let wanted = notification.userInfo?["caption"] as? String,
        let match = snapshot.neighbourhoods.first(where: {
          $0.caption.localizedCaseInsensitiveContains(wanted)
        })
      else { return }
      // Its biggest island, which is the one a person would have pressed.
      let biggest =
        match.coastline
        .enumerated()
        .max { frame(of: $0.element)?.1 ?? 0 < frame(of: $1.element)?.1 ?? 0 }
      enter(
        MemoryAtlasNeighbourhoodLabels.Placed(
          regionID: match.id, index: biggest?.offset ?? 0, caption: match.caption, rect: .zero,
          ring: biggest?.element ?? []))
    }
    .onReceive(
      NotificationCenter.default.publisher(for: .desktopAutomationMemoryAtlasSelectRequested)
    ) { notification in
      let target = notification.userInfo?["target"] as? String ?? "page"
      guard (target == "inline") == compact else { return }
      if notification.userInfo?["clear"] as? Bool == true {
        clearSelection()
        return
      }
      // Drives the same state a canvas click would, so an automated check
      // exercises the real inspector rather than a parallel preview path.
      if let edgeID = notification.userInfo?["edge_id"] as? String,
        let edge = snapshot.edges.first(where: { $0.id == edgeID }),
        snapshot.nodeByID[edge.edge.sourceId] != nil
      {
        selectionTrail.removeAll()
        adoptSelection(edge.edge.sourceId, edgeID: edgeID)
        return
      }
      // By name as well as by id, because an entity's id is a server key
      // nothing on screen shows. Selecting the entity a QA step is actually
      // talking about otherwise means clicking a dot by pixel — which is not
      // reachable from a headless check, and on a multi-display machine is not
      // reliably reachable from a cursor either.
      let named = (notification.userInfo?["label"] as? String).flatMap { wanted in
        snapshot.nodes.first { $0.node.label.localizedCaseInsensitiveCompare(wanted) == .orderedSame }
          ?? snapshot.nodes.first { $0.node.label.localizedCaseInsensitiveContains(wanted) }
      }
      if let nodeID = (notification.userInfo?["node_id"] as? String).flatMap({
        snapshot.nodeByID[$0] != nil ? $0 : nil
      }) ?? named?.id {
        selectionTrail.removeAll()
        adoptSelection(nodeID)
      }
    }
    .onReceive(NotificationCenter.default.publisher(for: .desktopAutomationMemoryAtlasTimeRequested)) {
      notification in
      let target = notification.userInfo?["target"] as? String ?? "page"
      guard (target == "inline") == compact else { return }
      if notification.userInfo?["reset"] as? Bool == true {
        stopPlayback(userInitiated: true)
        withAnimation(.easeOut(duration: 0.2)) { timeCursor = 1 }
        return
      }
      if let fraction = notification.userInfo?["fraction"] as? Double {
        stopPlayback(userInitiated: true)
        timeCursor = min(max(fraction, 0), 1)
        clearSelectionIfHiddenAtCurrentTime()
      }
      if let play = notification.userInfo?["play"] as? Bool {
        if play {
          startPlayback(resetToStart: notification.userInfo?["reset_to_start"] as? Bool ?? false)
        } else {
          stopPlayback(userInitiated: true)
        }
      }
      memoryAtlasLogger.debug(
        "Automation timeline target=\(target, privacy: .public) cursor=\(timeCursor, privacy: .public) playing=\(isTimePlaying, privacy: .public)"
      )
    }
  }

  private var atlasToolbar: some View {
    HStack(spacing: 12) {
      if showsSearchField {
        HStack(spacing: 8) {
          Image(systemName: "magnifyingglass")
            .scaledFont(size: 12)
            .foregroundColor(Ink.secondary)

          TextField("Search your entities", text: searchBinding)
            .textFieldStyle(.plain)
            .focused($searchIsFocused)
            .scaledFont(size: 12)
            .foregroundColor(Ink.primary)
            .onSubmit { selectFirstSearchResult() }
            .accessibilityLabel("Search entities")
            .accessibilityIdentifier("memory_atlas_search")

          if !searchText.isEmpty {
            Button {
              searchBinding.wrappedValue = ""
            } label: {
              Image(systemName: "xmark.circle.fill")
                .scaledFont(size: 11)
                .foregroundColor(Ink.secondary)
            }
            .buttonStyle(.plain)
            .help("Clear search (Esc)")
            .accessibilityLabel("Clear search")
          }
        }
        .padding(.horizontal, 12)
        .frame(width: compact ? 250 : 320, height: 30)
        .glassChip()
      }

      Spacer()

      if !compact {
        typeKey
      }

      if recentConnectionCount > 0 {
        HStack(spacing: 6) {
          Circle()
            .fill(snapshot.activeClusters.first?.color ?? Ink.secondary)
            .frame(width: 6, height: 6)
          Text(recentConnectionLabel)
            .scaledFont(size: 11, weight: .medium)
        }
        .foregroundColor(Ink.secondary)
      }

      // The legacy Brain Map carried a rebuild control; without it a thin or
      // stale server graph has no recovery path from inside the atlas.
      if let onRebuild {
        Menu {
          Button(action: onRebuild) {
            Label(
              isRebuilding ? "Rebuilding Brain Map…" : "Rebuild Brain Map…",
              systemImage: "arrow.clockwise")
          }
          .disabled(isRebuilding)
        } label: {
          PageQueryActionLabel(icon: "ellipsis", title: "More")
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
        .help("More Brain Map actions")
        .accessibilityLabel("More Brain Map actions")
        .accessibilityIdentifier("memory_atlas_more_actions")
      }
    }
    .padding(.horizontal, compact ? 12 : 18)
    .frame(height: compact ? 40 : 44)
    .background(Color.clear)
    .accessibilityHint("Press Command-F to search. Press Return to select the first visible result.")
  }

  private var hasNoSearchMatches: Bool {
    !searchText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
      && matchingNodeIDs?.isEmpty == true
      && !snapshot.nodes.isEmpty
  }

  private var searchEmptyState: some View {
    VStack(spacing: OmiSpacing.sm) {
      Image(systemName: "magnifyingglass")
        .scaledFont(size: OmiType.heading)
        .foregroundStyle(Ink.surface)
      Text(
        "No entities match \u{201c}\(searchText.trimmingCharacters(in: .whitespacesAndNewlines))\u{201d}"
      )
      .scaledFont(size: OmiType.body, weight: .semibold)
      .foregroundStyle(Ink.surface)
      .multilineTextAlignment(.center)
      Text("Try a different search or clear the search above.")
        .scaledFont(size: OmiType.caption)
        .foregroundStyle(Ink.surface.opacity(0.78))
        .multilineTextAlignment(.center)
    }
    .padding(.horizontal, OmiSpacing.lg)
    .accessibilityElement(children: .combine)
    .accessibilityLabel(
      "No entities match \(searchText.trimmingCharacters(in: .whitespacesAndNewlines))"
    )
    .accessibilityHint("Try a different search or clear the search above.")
  }

  /// Which colour means which kind of entity.
  ///
  /// This used to be printed on the canvas at each type's centre. That made
  /// sense when a type owned a region; now that entities are placed by what
  /// they relate to, a type's mean position is often somewhere none of its
  /// entities actually are — and on a real account the "Places" caption landed
  /// on top of the Singapore node's own name. A key states the same thing
  /// without claiming a location for it.
  private var typeKey: some View {
    HStack(spacing: 11) {
      Text("Legend")
        .scaledFont(size: 10, weight: .semibold)
        .foregroundColor(Ink.primary)

      ForEach(snapshot.activeClusters) { cluster in
        HStack(spacing: 5) {
          Circle().fill(cluster.color).frame(width: 5, height: 5)
          Text(cluster.title)
            .scaledFont(size: 10)
            .foregroundColor(Ink.secondary)
        }
      }
    }
    // The key identifies the map's colors; it is intentionally not a filter. Naming that contract
    // keeps the dots from presenting a false affordance to pointer-free users.
    .accessibilityElement(children: .combine)
    .accessibilityLabel("Brain Map legend")
    .accessibilityValue(
      snapshot.activeClusters.map { "\($0.title), color coded" }.joined(separator: "; ")
    )
    .accessibilityHint("Legend only; these items are not interactive filters.")
    .accessibilityIdentifier("memory_atlas_type_key")
  }

  private func atlasCanvas(
    size: CGSize, plan: MemoryAtlasRenderPlan,
    regions: [MemoryAtlasNeighbourhoodLabels.Placed],
    quietened: Set<String>
  ) -> some View {
    Canvas(opaque: false, colorMode: .linear) { context, _ in
      drawTerritories(context: &context, size: size, regions: regions)
      drawEdges(context: &context, size: size, plan: plan)
      drawNodes(context: &context, size: size, plan: plan)
      drawCanvasLabels(context: &context, size: size, plan: plan, quietened: quietened)
    }
    .accessibilityHidden(true)
  }

  /// What the map draws as territory right now, and whose names it hides to do
  /// it.
  ///
  /// One function because the two answers depend on each other. An entity
  /// standing on a named island loses its label to that island's caption, so
  /// the caption must not be pushed off its own ground avoiding a name that is
  /// about to disappear — which is what left most territories unnamed, and
  /// therefore undrawn, when the two were computed separately.
  private func territory(
    in size: CGSize, plan: MemoryAtlasRenderPlan
  ) -> (islands: [MemoryAtlasNeighbourhoodLabels.Placed], quietened: Set<String>) {
    // The replay and live camera gestures deliberately suppress SwiftUI
    // labels/targets. Re-solving caption placement during those frames would
    // still walk every visible entity against every coastline, despite none of
    // those captions being shown. Keep the camera/replay path to Canvas-only
    // work; territories return as soon as the frame settles.
    guard !isCameraMoving, !compact, matchingNodeIDs == nil,
      MemoryAtlasNeighbourhoodLabels.areVisible(
        detailLevel: plan.detailLevel, hasSelection: selectedNodeID != nil,
        isInsideNeighbourhood: enteredRegionID != nil)
    else { return ([], []) }

    let found = MemoryAtlasNeighbourhoodLabels.islands(
      snapshot.neighbourhoods,
      in: size,
      project: { point(for: $0, in: size) },
      focused: enteredRegionID)

    let captions = Dictionary(lastWriteWins: snapshot.neighbourhoods.map { ($0.id, $0.caption) })
    let budget = enteredRegionID == nil ? MemoryAtlasNeighbourhoodLabels.limit : Int.max

    // The entity names on the canvas, as boxes to stay out of. They hang below
    // their mark, and their width tracks the same estimate the canvas labeller
    // uses.
    func nameBoxes(hiding hidden: Set<String>) -> [CGRect] {
      plan.visibleNodes
        .filter { plan.labelNodeIDs.contains($0.id) && !hidden.contains($0.id) }
        .map { placement in
          let mark = point(for: placement.normalizedPosition, in: size)
          let width = min(160, max(48, CGFloat(placement.node.label.count) * 6.4 + 16))
          let above = plan.labelAboveNodeIDs.contains(placement.id)
          return CGRect(
            x: mark.x - width / 2, y: mark.y + (above ? -30 : 8), width: width, height: 20)
        }
    }

    /// Entities standing on ground the map has named. Inside a place, its own
    /// entities are the subject and they keep their names.
    ///
    /// Every visible entity against every island's outline is a hundred
    /// thousand edge crossings a frame, and this runs twice. The bounding box
    /// settles almost all of it in four comparisons: a territory covers a small
    /// part of the map, so nearly every entity is nowhere near nearly every
    /// island.
    func standingOn(_ islands: [MemoryAtlasNeighbourhoodLabels.Placed]) -> Set<String> {
      guard enteredRegionID == nil else { return [] }
      let bounded = islands.compactMap { island -> (CGRect, [CGPoint])? in
        guard let first = island.ring.first else { return nil }
        var minimum = first
        var maximum = first
        for vertex in island.ring {
          minimum = CGPoint(x: min(minimum.x, vertex.x), y: min(minimum.y, vertex.y))
          maximum = CGPoint(x: max(maximum.x, vertex.x), y: max(maximum.y, vertex.y))
        }
        return (
          CGRect(
            x: minimum.x, y: minimum.y, width: maximum.x - minimum.x,
            height: maximum.y - minimum.y), island.ring
        )
      }

      var hidden: Set<String> = []
      for placement in plan.visibleNodes
      where placement.id != snapshot.anchorNodeID && placement.id != selectedNodeID {
        let position = placement.normalizedPosition
        if bounded.contains(where: {
          $0.0.contains(position) && memoryAtlasCoastlineContains([$0.1], position)
        }) {
          hidden.insert(placement.id)
        }
      }
      return hidden
    }

    // Placed twice, because the two answers define each other: which names to
    // hide depends on which islands are drawn, and which islands can be drawn
    // depends on which names are in the way. The first pass finds the islands
    // by dodging every name; the second re-places them now that the names
    // standing on them are gone.
    //
    // One pass either way is wrong, and both ways were tried. Dodging every
    // name pushes captions off their own island for labels that are about to
    // disappear. Dodging none of them puts a caption on top of an entity that
    // then keeps its label, which is how "X (TWITTER)" ended up printed across
    // "Ho Chi Minh City".
    let candidates = MemoryAtlasNeighbourhoodLabels.place(
      found, captions: captions, in: size, avoiding: nameBoxes(hiding: []), limit: budget)
    let placed = MemoryAtlasNeighbourhoodLabels.place(
      found, captions: captions, in: size,
      avoiding: nameBoxes(hiding: standingOn(candidates)), limit: budget,
      insisting: enteredRegionID != nil)
    return (placed, standingOn(placed))
  }

  /// The land each neighbourhood holds, drawn under everything.
  ///
  /// Deliberately colourless. Type already owns hue on this canvas, and a
  /// second colour scale over the top of it would leave the user decoding two
  /// palettes at once — with thirty-odd regions to distinguish, one of them
  /// unwinnable. A region reads as a patch of ground, not as a category.
  ///
  /// And deliberately quiet. The wiring between entities is what says how the
  /// map is organised; territory is the annotation over it. Painted any
  /// stronger, the two layers compete and the result is neither a graph nor a
  /// map. The coast carries most of what little weight this layer has, because
  /// a line is legible at a fraction of the ink a fill needs.
  private func drawTerritories(
    context: inout GraphicsContext,
    size: CGSize,
    regions: [MemoryAtlasNeighbourhoodLabels.Placed]
  ) {
    for region in regions {
      guard region.ring.count >= 3 else { continue }
      var shape = Path()
      shape.move(to: point(for: region.ring[0], in: size))
      for vertex in region.ring.dropFirst() { shape.addLine(to: point(for: vertex, in: size)) }
      shape.closeSubpath()
      // The place the user went into is the one thing on the map they chose,
      // so it is drawn as chosen. Not loudly — a shade more ink than the
      // others is enough when it is also the only coast still on screen, and
      // it is what keeps the island reading as the frame once an entity
      // inside it is selected and the inspector takes over the right-hand
      // side.
      let entered = region.regionID == enteredRegionID
      // Even-odd, so an enclave inside a territory is drawn as the hole it is
      // rather than being filled over.
      context.fill(
        shape, with: .color(Ink.primary.opacity(entered ? 0.07 : 0.05)),
        style: FillStyle(eoFill: true))
      context.stroke(
        shape, with: .color(Ink.primary.opacity(entered ? 0.5 : 0.34)), lineWidth: 1)
    }
  }

  /// Region names as real controls rather than painted text.
  ///
  /// There are at most eight, so the cost of a view each is nothing, and it
  /// buys the two things a canvas cannot: a press that lands exactly where the
  /// caption is drawn, and a name VoiceOver can read. A territory you can see
  /// but not enter would be a worse map than one with no territories on it.
  @ViewBuilder
  private func neighbourhoodCaptions(
    regions: [MemoryAtlasNeighbourhoodLabels.Placed]
  ) -> some View {
    ForEach(regions) { region in
      MemoryAtlasNeighbourhoodCaption(
        caption: region.caption,
        size: region.rect.size,
        enter: { enter(region) }
      )
      .position(x: region.rect.midX, y: region.rect.midY)
      .help(enteredRegionID == region.regionID ? "Leave this neighbourhood" : "Go to \(region.caption)")
      .accessibilityLabel("Neighbourhood around \(region.caption)")
      .accessibilityHint(
        enteredRegionID == region.regionID
          ? "Returns to the whole map" : "Goes to this neighbourhood and names its entities"
      )
      .accessibilityIdentifier("memory_atlas_neighbourhood_\(region.regionID)")
    }
  }

  /// Takes the camera into a region: close enough that its entities are named,
  /// far enough that you can still see its edges.
  private func enter(_ region: MemoryAtlasNeighbourhoodLabels.Placed) {
    // Pressing the place you are already in is the way back out, because it is
    // the control the user's attention is already on. Without it, leaving means
    // guessing that the zoom-out button also drops the mode.
    guard enteredRegionID != region.regionID else { return leaveNeighbourhood() }
    guard viewportSize.width > 0, viewportSize.height > 0,
      let neighbourhood = snapshot.neighbourhoods.first(where: { $0.id == region.regionID })
    else { return }

    // Framed on the island that was pressed, not on the average of the group's
    // members. For a neighbourhood spread over two pieces of ground the average
    // is the water between them: entering one sent the camera to open sea, with
    // the island itself off the side of the canvas and nothing on screen to say
    // where the user had just arrived.
    let framed = frame(of: region.ring) ?? (neighbourhood.center, neighbourhood.radius)
    let camera = MemoryAtlasNeighbourhoodLabels.entering(
      center: framed.0,
      radius: framed.1,
      viewport: viewportSize,
      zoomRange: MemoryAtlasZoomPolicy.minimumZoom...maximumZoom)
    departureZoom = MemoryAtlasNeighbourhoodLabels.departureZoom(
      enteredAt: camera.zoom, neighbourhoodZoom: MemoryAtlasZoomPolicy.neighborhoodZoom,
      minimumZoom: MemoryAtlasZoomPolicy.minimumZoom)
    withAnimation(OmiMotion.gated(.easeOut(duration: 0.26))) {
      enteredRegionID = region.regionID
      zoom = camera.zoom
      settledZoom = camera.zoom
      pan = camera.pan
      settledPan = camera.pan
    }
  }

  /// The middle of an island and how far it reaches, in normalized map
  /// coordinates. Half the diagonal rather than half a side, so a long thin
  /// island is framed by its length and not cropped to its width.
  private func frame(of ring: [CGPoint]) -> (CGPoint, CGFloat)? {
    guard let first = ring.first else { return nil }
    var minimum = first
    var maximum = first
    for vertex in ring {
      minimum = CGPoint(x: min(minimum.x, vertex.x), y: min(minimum.y, vertex.y))
      maximum = CGPoint(x: max(maximum.x, vertex.x), y: max(maximum.y, vertex.y))
    }
    return (
      CGPoint(x: (minimum.x + maximum.x) / 2, y: (minimum.y + maximum.y) / 2),
      hypot(maximum.x - minimum.x, maximum.y - minimum.y) / 2
    )
  }

  /// Back out to the whole map, without moving the camera.
  ///
  /// Deliberately not a zoom-out. The user came in to look at something and is
  /// probably still looking at it; snapping the camera away would undo the
  /// thing they asked for. Only the mode ends — every coastline comes back and
  /// the captions take their entities' names again.
  private func leaveNeighbourhood() {
    departureZoom = nil
    withAnimation(OmiMotion.gated(.easeOut(duration: 0.2))) { enteredRegionID = nil }
  }

  private func drawEdges(
    context: inout GraphicsContext,
    size: CGSize,
    plan: MemoryAtlasRenderPlan
  ) {
    let paintBounds = canvasPaintBounds(for: size)
    let anchorID = snapshot.anchorNodeID
    let spokesAreBackground = MemoryAtlasLayoutEngine.anchorConnectionsRecede(
      anchorID: anchorID, selectedNodeID: selectedNodeID)

    for cluster in snapshot.activeClusters {
      var path = Path()
      var within = Path()
      var spokes = Path()
      for placement in plan.visibleEdges where placement.cluster == cluster {
        let source = point(for: placement.source, in: size)
        let target = point(for: placement.target, in: size)
        let segmentBounds = CGRect(
          x: min(source.x, target.x) - 1,
          y: min(source.y, target.y) - 1,
          width: max(abs(source.x - target.x), 2),
          height: max(abs(source.y - target.y), 2)
        )
        // The rendered segment lies inside its bounding box, so a disjoint
        // box cannot cross the viewport. This is paint-only culling: the plan
        // and its stable entity cohort remain unchanged.
        guard segmentBounds.intersects(paintBounds) else { continue }
        let touchesAnchor =
          placement.edge.sourceId == anchorID || placement.edge.targetId == anchorID
        if spokesAreBackground && touchesAnchor {
          spokes.move(to: source)
          spokes.addLine(to: target)
        } else if placement.withinNeighbourhood && selectedNodeID == nil {
          within.move(to: source)
          within.addLine(to: target)
        } else {
          path.move(to: source)
          path.addLine(to: target)
        }
      }
      // Hairlines. With the whole mesh drawn rather than a few dozen of it,
      // the per-connection weight that used to read as one relationship now
      // has to read as texture — at the old 0.25 the map was a wall of lines.
      // A connection crossing between two neighbourhoods is drawn fainter than
      // one inside a neighbourhood, so density falls off at a group's edge the
      // way the graph says it does.
      if !path.isEmpty {
        context.stroke(
          path,
          with: .color(cluster.color.opacity(selectedNodeID == nil ? 0.055 : 0.74)),
          lineWidth: selectedNodeID == nil ? 0.6 : 1.7
        )
      }
      if !within.isEmpty {
        context.stroke(within, with: .color(cluster.color.opacity(0.14)), lineWidth: 0.7)
      }
      // The account holder's own spokes, fainter again — and much fainter than
      // they were, because the budget that used to let only a few dozen lines
      // onto the map was holding this back by accident. Drawn in full at the
      // old weight, eight hundred tethers to the middle of the map buried every
      // other connection under a starburst. "You are connected to this" is the
      // least informative thing the map can say, so it is the first thing that
      // gives way.
      if !spokes.isEmpty {
        context.stroke(
          spokes,
          with: .color(cluster.color.opacity(selectedNodeID == nil ? 0.028 : 0.16)),
          lineWidth: 0.5
        )
      }
    }
  }

  private func drawNodes(
    context: inout GraphicsContext,
    size: CGSize,
    plan: MemoryAtlasRenderPlan
  ) {
    // While the time cursor is engaged, an entity that was just "born" blooms
    // briefly as the playhead sweeps past its creation date, then settles into
    // the constellation — the atlas visibly grows rather than snapping in.
    let replayCursor = timeCursor < 0.9995 ? timeCursor : nil
    let paintBounds = canvasPaintBounds(for: size)

    var catalogPrimaryPath = Path()
    var catalogMutedPath = Path()
    for placement in plan.visibleNodes where placement.isCatalog && placement.id != selectedNodeID {
      let related = selectedNodeID == nil || plan.relatedNodeIDs.contains(placement.id)
      let matches = matchingNodeIDs == nil || matchingNodeIDs?.contains(placement.id) == true
      let radius = nodeRadius(for: placement)
      let center = point(for: placement.normalizedPosition, in: size)
      guard
        paintBounds.intersects(
          CGRect(x: center.x - radius, y: center.y - radius, width: radius * 2, height: radius * 2)
        )
      else { continue }
      let rect = CGRect(x: center.x - radius, y: center.y - radius, width: radius * 2, height: radius * 2)
      if related && matches {
        catalogPrimaryPath.addEllipse(in: rect)
      } else {
        catalogMutedPath.addEllipse(in: rect)
      }
    }
    if !catalogPrimaryPath.isEmpty {
      context.fill(catalogPrimaryPath, with: .color(Ink.secondary.opacity(0.28)))
    }
    if !catalogMutedPath.isEmpty {
      context.fill(catalogMutedPath, with: .color(Ink.secondary.opacity(0.055)))
    }

    for cluster in snapshot.activeClusters {
      var primaryPath = Path()
      var mutedPath = Path()
      for placement in plan.visibleNodes where placement.cluster == cluster {
        guard placement.id != selectedNodeID else { continue }
        let related = selectedNodeID == nil || plan.relatedNodeIDs.contains(placement.id)
        let matches = matchingNodeIDs == nil || matchingNodeIDs?.contains(placement.id) == true
        var radius = nodeRadius(for: placement)
        let center = point(for: placement.normalizedPosition, in: size)

        // Canvas otherwise builds paths for every deep-zoom entity, including
        // those far outside the clipped viewport. Culling here keeps maximum
        // zoom scalable without changing which nodes exist or can appear as
        // the user pans back to them.
        guard
          paintBounds.intersects(
            CGRect(
              x: center.x - radius,
              y: center.y - radius,
              width: radius * 2,
              height: radius * 2
            ))
        else { continue }

        var pop = 0.0
        if let replayCursor, let timeline {
          pop = timeline.spawnProgress(nodeID: placement.id, at: replayCursor)
        }
        if pop > 0 {
          radius *= CGFloat(1 + 0.9 * pop)
          let bloom = radius * 2.6
          context.fill(
            Path(
              ellipseIn: CGRect(
                x: center.x - bloom / 2, y: center.y - bloom / 2, width: bloom, height: bloom
              )),
            with: .color(cluster.color.opacity(0.3 * pop))
          )
        }

        let rect = CGRect(
          x: center.x - radius,
          y: center.y - radius,
          width: radius * 2,
          height: radius * 2
        )
        if related && matches {
          primaryPath.addEllipse(in: rect)
        } else {
          mutedPath.addEllipse(in: rect)
        }
      }
      if !primaryPath.isEmpty {
        context.fill(primaryPath, with: .color(cluster.color.opacity(0.78)))
      }
      if !mutedPath.isEmpty {
        context.fill(mutedPath, with: .color(cluster.color.opacity(0.1)))
      }
    }

    if let anchorNodeID = snapshot.anchorNodeID,
      let anchor = plan.visibleNodes.first(where: { $0.id == anchorNodeID })
    {
      drawSpecialNode(
        anchor,
        radius: compact ? 6 : (isInspectMode ? 18 : (isFocusMode ? 12 : 7)),
        color: Ink.primary,
        opacity: selectedNodeID == nil || plan.relatedNodeIDs.contains(anchor.id) ? 0.86 : 0.16,
        context: &context,
        size: size
      )
    }

    if let selectedNode {
      drawSpecialNode(
        selectedNode,
        radius: compact ? 7 : (isInspectMode ? 26 : (isFocusMode ? 18 : 9)),
        color: selectedNode.cluster?.color ?? Ink.primary,
        opacity: 0.95,
        context: &context,
        size: size
      )
    }
  }

  private func drawSpecialNode(
    _ placement: MemoryAtlasNodePlacement,
    radius: CGFloat,
    color: Color,
    opacity: Double,
    context: inout GraphicsContext,
    size: CGSize
  ) {
    let center = point(for: placement.normalizedPosition, in: size)
    let rect = CGRect(
      x: center.x - radius,
      y: center.y - radius,
      width: radius * 2,
      height: radius * 2
    )
    context.fill(Path(ellipseIn: rect), with: .color(color.opacity(opacity)))
  }

  private func drawCanvasLabels(
    context: inout GraphicsContext,
    size: CGSize,
    plan: MemoryAtlasRenderPlan,
    /// Entities standing on a named territory, whose name the caption is
    /// currently speaking for.
    quietened: Set<String>
  ) {
    guard plan.usesCanvasLabels else { return }

    // From the density-aware inspection threshold onward, every dot on this
    // canvas gets a label. Skip labels outside the clipped canvas before
    // resolving Text, which makes a 10k-node graph cost proportional to the
    // current viewport rather than the total graph size.
    let visibleBounds = CGRect(origin: .zero, size: size)
    for placement in plan.canvasLabelNodes where !quietened.contains(placement.id) {
      let center = point(for: placement.normalizedPosition, in: size)
      guard visibleBounds.contains(center) else { continue }

      let color = placement.cluster?.color ?? Ink.primary
      let rawLabel = placement.node.label.trimmingCharacters(in: .whitespacesAndNewlines)
      let displayLabel =
        rawLabel.count > 80
        ? String(rawLabel.prefix(79)).trimmingCharacters(in: .whitespacesAndNewlines) + "…"
        : rawLabel
      let estimatedLabelWidth = min(
        152.0,
        max(44.0, CGFloat(displayLabel.count) * 6.4 + 18)
      )
      let labelCenterX = min(
        max(center.x, estimatedLabelWidth / 2),
        size.width - estimatedLabelWidth / 2
      )
      let text = Text(displayLabel)
        .font(.system(size: 11, weight: placement.id == snapshot.anchorNodeID ? .semibold : .medium))
        .foregroundStyle(Ink.primary)
      let labelOffset: CGFloat =
        if placement.id == selectedNodeID {
          34
        } else if placement.id == snapshot.anchorNodeID {
          24
        } else {
          nodeRadius(for: placement) + 5
        }
      context.draw(text, at: CGPoint(x: labelCenterX, y: center.y + labelOffset), anchor: .top)

      // A small leading color marker keeps labels scannable while preserving
      // the neutral text treatment used elsewhere in the Atlas.
      context.fill(
        Path(ellipseIn: CGRect(x: center.x - 3, y: center.y + labelOffset + 4, width: 3, height: 3)),
        with: .color(color)
      )
    }
  }

  private var isSmallAtlas: Bool {
    !compact && snapshot.nodes.count <= MemoryAtlasZoomPolicy.smallAtlasCeiling
  }

  private func nodeRadius(for placement: MemoryAtlasNodePlacement) -> CGFloat {
    MemoryAtlasNodeVisualPolicy.radius(
      clusterRank: placement.clusterRank,
      zoom: zoom,
      compact: compact,
      isFullyLabelled: isFullyLabelledMode,
      isInspect: isInspectMode,
      isFocus: isFocusMode,
      isSmallAtlas: isSmallAtlas
    )
  }

  private func nodeLabel(
    _ placement: MemoryAtlasNodePlacement,
    selected: Bool
  ) -> some View {
    Text(placement.node.label)
      .scaledFont(
        size: compact ? 9.5 : (isInspectMode ? 14 : (isFocusMode ? 13 : 11)),
        weight: selected ? .semibold : .medium
      )
      .foregroundColor(Ink.primary)
      .lineLimit(1)
      .truncationMode(.tail)
      .multilineTextAlignment(.center)
      .fixedSize()
      .frame(maxWidth: compact ? 110 : 150)
      .allowsHitTesting(false)
  }

  private func nodeButton(
    _ placement: MemoryAtlasNodePlacement,
    size: CGSize,
    relatedNodeIDs: Set<String>,
    showLabel: Bool,
    labelAbove: Bool
  ) -> some View {
    let selected = selectedNodeID == placement.id
    let related = selectedNodeID == nil || relatedNodeIDs.contains(placement.id)
    let matches = matchingNodeIDs == nil || matchingNodeIDs?.contains(placement.id) == true
    let color = placement.cluster?.color ?? Ink.primary
    let diameter = nodeDiameter(placement, selected: selected)

    // Keeping the label out of the laid-out frame is what makes the ring land
    // on the node. A VStack of ring-over-label is centered by `.position`, so
    // the ring floats above the point while the Canvas paints the dot on it —
    // two marks per entity, visibly offset once dots are more than a few px.
    let hitDiameter = max(diameter, 24)

    return Button {
      if selected {
        clearSelection(resetCamera: true)
      } else {
        selectionTrail.removeAll()
        adoptSelection(placement.id)
      }
    } label: {
      ZStack {
        if selected {
          Circle()
            .stroke(color.opacity(0.22), lineWidth: 7)
            .frame(width: diameter + 14, height: diameter + 14)
        }
        Circle()
          .fill(Ink.rowFill)
          .overlay(Circle().stroke(color, lineWidth: selected ? 2.2 : 1.4))
          .frame(width: diameter, height: diameter)
        if placement.id == snapshot.anchorNodeID {
          Image(systemName: "person.fill")
            .scaledFont(size: max(9, diameter * 0.38))
            .foregroundColor(Ink.primary)
        }
      }
      .frame(width: hitDiameter, height: hitDiameter)
      // Both overlays hang the name outside the laid-out frame, so the frame
      // stays centered on the entity's own position. `.top`/`.bottom` anchor
      // the opposite edge of the text, which is what makes the same gap read
      // identically whether the name sits under the mark or over it.
      .overlay(alignment: .top) {
        if showLabel && !labelAbove {
          nodeLabel(placement, selected: selected)
            .offset(y: hitDiameter / 2 + diameter / 2 + 5)
        }
      }
      .overlay(alignment: .bottom) {
        if showLabel && labelAbove {
          nodeLabel(placement, selected: selected)
            .offset(y: -(hitDiameter / 2 + diameter / 2 + 5))
        }
      }
      .contentShape(Rectangle())
      .opacity((related && matches) ? 1 : 0.2)
    }
    .buttonStyle(.plain)
    .position(point(for: placement.normalizedPosition, in: size))
    .help(placement.node.label)
    .accessibilityLabel(placement.node.label)
    .accessibilityValue(placement.node.nodeType.rawValue)
  }

  /// `nil` collapses the header's back affordance; the ternary needs the
  /// explicit optional-closure type to stay unambiguous.
  private var backAction: (() -> Void)? {
    selectionTrail.isEmpty ? nil : { goBack() }
  }

  private func detailPanel(for placement: MemoryAtlasNodePlacement) -> some View {
    let relationships: [MemoryAtlasRelationshipRow] = selectedEdges.compactMap { edge in
      let otherID = edge.edge.sourceId == placement.id ? edge.edge.targetId : edge.edge.sourceId
      guard let other = snapshot.nodeByID[otherID] else { return nil }
      return MemoryAtlasRelationshipRow(
        id: edge.id,
        otherNodeID: otherID,
        otherLabel: other.node.label,
        relationship: MemoryAtlasLayoutEngine.combinedRelationshipDisplayName(edge.relationshipLabels),
        accent: other.cluster?.color ?? Ink.secondary
      )
    }

    return MemoryAtlasDetailPanel(
      subject: .entity(
        title: placement.node.label,
        typeName: placement.cluster?.title,
        connectionSummary: "\(placement.degree) connection\(placement.degree == 1 ? "" : "s")"
      ),
      accent: placement.cluster?.color ?? Ink.primary,
      related: relationships,
      evidence: evidence,
      evidenceIsLoading: evidenceIsLoading,
      unresolvedEvidenceCount: unresolvedEvidenceCount,
      onOpenRelated: openRelated,
      onOpenMemory: openCitedMemory,
      onBack: backAction,
      onFocus: { focus(on: placement) },
      onClose: { clearSelection(resetCamera: true) }
    )
  }

  /// Inspector for a single connection: which two entities it joins, and the
  /// memories that produced that specific claim rather than everything either
  /// endpoint happens to be involved in.
  private func relationshipPanel(
    for edge: MemoryAtlasEdgePlacement,
    anchor: MemoryAtlasNodePlacement
  ) -> some View {
    let source = snapshot.nodeByID[edge.edge.sourceId]
    let target = snapshot.nodeByID[edge.edge.targetId]
    let endpoints: [MemoryAtlasRelationshipRow] = [source, target].compactMap { endpoint in
      guard let endpoint else { return nil }
      return MemoryAtlasRelationshipRow(
        id: "endpoint-\(endpoint.id)",
        otherNodeID: endpoint.id,
        otherLabel: endpoint.node.label,
        relationship: endpoint.cluster?.title ?? "Entity",
        accent: endpoint.cluster?.color ?? Ink.secondary
      )
    }

    return MemoryAtlasDetailPanel(
      subject: .relationship(
        sourceLabel: source?.node.label ?? edge.edge.sourceId,
        targetLabel: target?.node.label ?? edge.edge.targetId,
        verb: MemoryAtlasLayoutEngine.combinedRelationshipDisplayName(edge.relationshipLabels)
      ),
      accent: edge.cluster.color,
      related: endpoints,
      evidence: evidence,
      evidenceIsLoading: evidenceIsLoading,
      unresolvedEvidenceCount: unresolvedEvidenceCount,
      onOpenRelated: openRelated,
      onOpenMemory: openCitedMemory,
      onBack: backAction,
      onFocus: { focus(on: anchor) },
      onClose: { clearSelection(resetCamera: true) }
    )
  }

  /// A cited memory is readable here, but acting on it — editing, checking its
  /// provenance, deleting it — belongs on the Memories page. Opening it there
  /// with its detail panel showing is the one hop that does not lose the thread.
  private func openCitedMemory(_ item: MemoryAtlasEvidence) {
    onOpenMemory?(item.id)
  }

  private func openRelated(_ row: MemoryAtlasRelationshipRow) {
    guard snapshot.nodeByID[row.otherNodeID] != nil else { return }
    if let current = selectedNodeID, current != row.otherNodeID {
      selectionTrail.append(current)
    }
    adoptSelection(row.otherNodeID)
  }

  private func goBack() {
    guard let previous = selectionTrail.popLast() else { return }
    adoptSelection(previous)
  }

  private func adoptSelection(_ nodeID: String, edgeID: String? = nil) {
    selectedEdgeID = edgeID
    selectedNodeID = nodeID
    SearchAnalytics.resultOpened(surface: .brainMap, searchIsActive: DebouncedSearchCoordinator.isActive(searchText))
    if let placement = snapshot.nodeByID[nodeID] {
      focus(on: placement)
    }
  }

  private func clearSelection(resetCamera: Bool = false) {
    selectionTrail.removeAll()
    selectedEdgeID = nil
    selectedNodeID = nil
    if resetCamera { resetViewport(preservingNeighbourhood: true) }
  }

  private func selectionStrip(for placement: MemoryAtlasNodePlacement) -> some View {
    let primaryEdge = selectedEdges.first
    let sourceNode = primaryEdge.flatMap { snapshot.nodeByID[$0.edge.sourceId] }
    let targetNode = primaryEdge.flatMap { snapshot.nodeByID[$0.edge.targetId] }
    let evidenceIds = citedMemoryIDs
    let relationshipText: String = {
      guard let primaryEdge, let sourceNode, let targetNode else {
        return "\(placement.degree) connection\(placement.degree == 1 ? "" : "s")"
      }
      return
        "\(sourceNode.node.label) \(MemoryAtlasLayoutEngine.combinedRelationshipDisplayName(primaryEdge.relationshipLabels)) \(targetNode.node.label)"
    }()

    return HStack(spacing: 14) {
      Circle()
        .fill((placement.cluster?.color ?? Ink.primary).opacity(0.14))
        .overlay(Circle().stroke(placement.cluster?.color ?? Ink.primary, lineWidth: 1.5))
        .frame(width: 34, height: 34)

      VStack(alignment: .leading, spacing: 2) {
        Text(placement.node.label)
          .scaledFont(size: compact ? 12 : 14, weight: .semibold)
          .foregroundColor(Ink.primary)
        Text(relationshipText)
          .scaledFont(size: compact ? 10 : 12)
          .foregroundColor(Ink.secondary)
          .lineLimit(1)
      }

      Spacer()

      if !compact {
        Button {
          focus(on: placement)
        } label: {
          Label("Focus", systemImage: "scope")
            .scaledFont(size: 11, weight: .medium)
            .foregroundColor(Ink.secondary)
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("memory_atlas_focus_selection")
      }

      // Compact surfaces cannot fit the inspector, so the strip reports the
      // evidence count rather than offering a jump that would leave the map.
      Text(
        evidenceIds.isEmpty
          ? "Source details are still being linked"
          : "\(evidenceIds.count) source memor\(evidenceIds.count == 1 ? "y" : "ies")"
      )
      .scaledFont(size: 10)
      .foregroundColor(Ink.secondary)

      Button {
        clearSelection(resetCamera: true)
      } label: {
        Image(systemName: "xmark")
          .scaledFont(size: 10, weight: .semibold)
          .foregroundColor(Ink.secondary)
          .frame(width: 24, height: 24)
          .contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      .help("Clear selection (Esc)")
      .accessibilityLabel("Clear selection")
      .accessibilityIdentifier("memory_atlas_clear_selection")
    }
    .padding(.horizontal, compact ? 12 : 18)
    .frame(height: compact ? 50 : 56)
    .background(Ink.rowFill)
    .overlay(alignment: .top) {
      Divider().overlay(Ink.separator.opacity(0.24))
    }
  }

  private var atlasLegend: some View {
    HStack(spacing: 18) {
      Text(atlasLevelLabel)
        .scaledFont(size: 11, weight: .medium)
        .foregroundColor(Ink.secondary)

      Spacer()
    }
    .padding(.horizontal, 18)
    .frame(height: 36)
    .background(Ink.rowFill)
  }

  // MARK: - Time axis

  /// Two tight rows: state on top, scrubber below. Everything here is
  /// secondary to the atlas itself, so the bar stays a footer and never takes
  /// canvas away from the graph.
  private var timelineBar: some View {
    VStack(spacing: 5) {
      HStack(spacing: 8) {
        Button(action: togglePlayback) {
          ZStack {
            Circle().fill(Ink.primary).frame(width: 22, height: 22)
            Image(systemName: isTimePlaying ? "pause.fill" : "play.fill")
              .scaledFont(size: 9, weight: .bold)
              .foregroundColor(Ink.surface)
              .offset(x: isTimePlaying ? 0 : 1)
          }
        }
        .buttonStyle(.plain)
        .help(isTimePlaying ? "Pause" : "Play your memory forward")
        .accessibilityLabel(isTimePlaying ? "Pause memory timeline" : "Play memory timeline")
        .accessibilityIdentifier("memory_atlas_timeline_play")

        Text(asOfLabel)
          .scaledFont(size: 11, weight: .semibold)
          .foregroundColor(Ink.primary)
          .lineLimit(1)

        Text(
          MemoryAtlasLayoutEngine.countLabel(
            entities: visibleEntityCount, connections: visibleConnectionCount)
        )
        .scaledFont(size: 10)
        .foregroundColor(Ink.secondary)
        .monospacedDigit()
        .lineLimit(1)

        Spacer(minLength: 8)

        Text(atlasLevelLabel)
          .scaledFont(size: 10, weight: .medium)
          .foregroundColor(Ink.secondary)
          .lineLimit(1)

        if timeCursor < 0.9995 {
          Button(action: jumpToNow) {
            Text("Now")
              .scaledFont(size: 10, weight: .semibold)
              .foregroundColor(Ink.secondary)
              .padding(.horizontal, 8)
              .frame(height: 18)
              .glassChip()
          }
          .buttonStyle(.plain)
          .accessibilityIdentifier("memory_atlas_timeline_now")
        }
      }

      // The range endpoints flank the scrubber instead of taking a third row.
      HStack(spacing: 8) {
        Text(shortDate(timeline?.start))
          .scaledFont(size: 9)
          .foregroundColor(Ink.secondary)
          .lineLimit(1)

        timelineTrack

        Text(timeline?.hasChronologicalRange == true ? "Now" : "Imported")
          .scaledFont(size: 9)
          .foregroundColor(Ink.secondary)
          .lineLimit(1)
      }
    }
    .padding(.horizontal, 18)
    .padding(.vertical, 8)
    .background(Ink.rowFill)
    .overlay(alignment: .top) {
      Divider().overlay(Ink.separator.opacity(0.24))
    }
    .accessibilityIdentifier("memory_atlas_timeline")
  }

  private var timelineTrack: some View {
    GeometryReader { geo in
      Canvas(opaque: false, colorMode: .linear) { context, size in
        drawTimeline(context: &context, size: size)
      }
      .contentShape(Rectangle())
      .gesture(
        DragGesture(minimumDistance: 0)
          .onChanged { value in scrub(to: value.location.x / max(geo.size.width, 1)) }
      )
    }
    .frame(height: 20)
    .accessibilityIdentifier("memory_atlas_timeline_track")
    .accessibilityElement()
    .accessibilityLabel("Memory timeline")
    .accessibilityValue(asOfLabel)
    .accessibilityHint("Adjust to replay the atlas over time")
    .accessibilityAdjustableAction { direction in
      let step = 0.05
      switch direction {
      case .increment:
        scrub(to: min(timeCursor + step, 1))
      case .decrement:
        scrub(to: max(timeCursor - step, 0))
      @unknown default:
        break
      }
    }
  }

  private func drawTimeline(context: inout GraphicsContext, size: CGSize) {
    guard let timeline else { return }
    let buckets = timeline.buckets
    let maxCount = CGFloat(max(buckets.max() ?? 1, 1))
    let barWidth = size.width / CGFloat(max(buckets.count, 1))
    let cursorX = CGFloat(timeCursor) * size.width
    let baseY = size.height - 6

    for (index, count) in buckets.enumerated() {
      let barHeight = CGFloat(count) / maxCount * (size.height - 12)
      let x = CGFloat(index) * barWidth
      let born = (x + barWidth / 2) <= cursorX
      let rect = CGRect(
        x: x + 1, y: baseY - barHeight, width: max(barWidth - 2, 1), height: max(barHeight, 0.5)
      )
      context.fill(
        Path(roundedRect: rect, cornerRadius: 1),
        with: .color(Ink.primary.opacity(born ? 0.3 : 0.08))
      )
    }

    var baseline = Path()
    baseline.move(to: CGPoint(x: 0, y: baseY))
    baseline.addLine(to: CGPoint(x: size.width, y: baseY))
    context.stroke(baseline, with: .color(Ink.separator.opacity(0.5)), lineWidth: 1)

    var filled = Path()
    filled.move(to: CGPoint(x: 0, y: baseY))
    filled.addLine(to: CGPoint(x: cursorX, y: baseY))
    context.stroke(filled, with: .color(Ink.primary.opacity(0.85)), lineWidth: 1.5)

    var playhead = Path()
    playhead.move(to: CGPoint(x: cursorX, y: 0))
    playhead.addLine(to: CGPoint(x: cursorX, y: size.height))
    context.stroke(playhead, with: .color(Ink.primary.opacity(0.85)), lineWidth: 1.5)

    context.fill(
      Path(ellipseIn: CGRect(x: cursorX - 5, y: baseY - 5, width: 10, height: 10)),
      with: .color(Ink.primary)
    )
  }

  private var asOfLabel: String {
    guard let asOf = asOfDate else { return "Now — the whole map" }
    guard MemoryAtlasPlayback.isCredible(asOf) else { return "Import replay" }
    let formatter = DateFormatter()
    formatter.dateStyle = .medium
    formatter.timeStyle = .none
    if timeline?.hasChronologicalRange == false {
      return "Import replay · \(formatter.string(from: asOf))"
    }
    return "Replay · \(formatter.string(from: asOf))"
  }

  private func shortDate(_ date: Date?) -> String {
    guard let date, MemoryAtlasPlayback.isCredible(date) else { return "" }
    let formatter = DateFormatter()
    formatter.dateFormat = "MMM d, yyyy"
    return formatter.string(from: date)
  }

  private func maybeAutoplayTimeline() {
    guard previewTimeCursor == nil else { return }
    guard !compact, timeline != nil, autoplayEnabled, !didAutoplay, !reduceMotion else { return }
    didAutoplay = true
    startPlayback(resetToStart: true)
  }

  private func togglePlayback() {
    if isTimePlaying {
      stopPlayback(userInitiated: true)
    } else {
      startPlayback(resetToStart: timeCursor >= 0.9995)
    }
  }

  private func startPlayback(resetToStart: Bool) {
    guard timeline != nil else { return }
    playbackTask?.cancel()
    if resetToStart || timeCursor >= 0.9995 {
      timeCursor = 0
      clearSelectionIfHiddenAtCurrentTime()
    }
    isTimePlaying = true
    // Suppress the interactive overlay + floating titles for a clean, smooth
    // growth animation; restored the moment playback ends.
    isCameraMoving = true
    playbackTask = Task { @MainActor in
      var last = Date()
      let totalSeconds = MemoryAtlasPlayback.duration(entityCount: snapshot.nodes.count)
      while !Task.isCancelled {
        try? await Task.sleep(nanoseconds: 33_000_000)
        if Task.isCancelled { return }
        let now = Date()
        let delta = now.timeIntervalSince(last)
        last = now
        let next = timeCursor + delta / totalSeconds
        if next >= 1 {
          timeCursor = 1
          finishPlaybackNaturally()
          return
        }
        timeCursor = next
      }
    }
  }

  /// Playing to the end is not an opt-out — the delightful default survives.
  private func finishPlaybackNaturally() {
    playbackTask = nil
    isTimePlaying = false
    isCameraMoving = false
  }

  private func stopPlayback(userInitiated: Bool) {
    playbackTask?.cancel()
    playbackTask = nil
    if isTimePlaying { isCameraMoving = false }
    isTimePlaying = false
    if userInitiated { autoplayEnabled = false }
  }

  private func scrub(to fraction: Double) {
    if isTimePlaying || playbackTask != nil {
      stopPlayback(userInitiated: true)
    } else {
      // Grabbing the timeline is an explicit opt-out of auto-play on open.
      autoplayEnabled = false
    }
    timeCursor = min(max(fraction, 0), 1)
    clearSelectionIfHiddenAtCurrentTime()
  }

  private func jumpToNow() {
    stopPlayback(userInitiated: true)
    withAnimation(.easeOut(duration: 0.25)) { timeCursor = 1 }
  }

  private var zoomControls: some View {
    HStack(spacing: 1) {
      Button {
        zoomOut()
      } label: {
        Image(systemName: "minus").frame(width: 28, height: 28)
      }
      .accessibilityIdentifier("memory_atlas_zoom_out")
      .accessibilityLabel("Zoom out")
      Button {
        resetViewport()
      } label: {
        Text("\(Int(zoom * 100))%")
          .scaledFont(size: 9, weight: .medium)
          .frame(width: 40, height: 28)
      }
      .help("Return to overview")
      .accessibilityIdentifier("memory_atlas_reset_viewport")
      .accessibilityLabel("Reset Brain Map viewport")
      .accessibilityValue("\(Int(zoom * 100)) percent")
      Button {
        zoomIn()
      } label: {
        Image(systemName: "plus").frame(width: 28, height: 28)
      }
      .disabled(zoom >= maximumZoom)
      .help(compact ? "Open the Brain Map for deeper exploration" : "Zoom in (accelerates for large maps)")
      .accessibilityIdentifier("memory_atlas_zoom_in")
      .accessibilityLabel("Zoom in")
    }
    .scaledFont(size: 10)
    .foregroundColor(Ink.secondary)
    .glassChip()
    .buttonStyle(.plain)
  }

  private var panGesture: some Gesture {
    DragGesture(minimumDistance: 3)
      .onChanged { value in
        isCameraMoving = true
        pan = CGSize(
          width: settledPan.width + value.translation.width,
          height: settledPan.height + value.translation.height
        )
      }
      .onEnded { _ in
        settledPan = pan
        isCameraMoving = false
      }
  }

  private func magnificationGesture(in size: CGSize) -> some Gesture {
    MagnifyGesture()
      .onChanged { value in
        isCameraMoving = true
        let nextZoom = min(
          max(settledZoom * value.magnification, MemoryAtlasZoomPolicy.minimumZoom),
          maximumZoom
        )
        let ratio = nextZoom / settledZoom
        let anchor = CGPoint(
          x: value.startAnchor.x * size.width,
          y: value.startAnchor.y * size.height
        )
        zoom = nextZoom
        pan = CGSize(
          width: (1 - ratio) * (anchor.x - size.width / 2) + ratio * settledPan.width,
          height: (1 - ratio) * (anchor.y - size.height / 2) + ratio * settledPan.height
        )
      }
      .onEnded { _ in
        settledZoom = zoom
        settledPan = pan
        isCameraMoving = false
      }
  }

  private func scrollZoom(by delta: CGFloat, anchoredAt pointer: CGPoint, in size: CGSize) {
    guard delta != 0, size.width > 0, size.height > 0 else { return }
    let nextZoom = min(
      max(zoom * CGFloat(exp(Double(delta))), MemoryAtlasZoomPolicy.minimumZoom),
      maximumZoom
    )
    guard nextZoom != zoom else { return }

    let ratio = nextZoom / zoom
    pan = CGSize(
      width: (1 - ratio) * (pointer.x - size.width / 2) + ratio * pan.width,
      height: (1 - ratio) * (pointer.y - size.height / 2) + ratio * pan.height
    )
    zoom = nextZoom
    settledZoom = nextZoom
    settledPan = pan
  }

  private var maximumZoom: CGFloat {
    MemoryAtlasZoomPolicy.maximumZoom(nodeCount: snapshot.nodes.count, compact: compact)
  }

  private var isFullyLabelledMode: Bool {
    !compact && zoom >= maximumZoom
  }

  private var isFocusMode: Bool {
    !compact && zoom >= MemoryAtlasZoomPolicy.focusModeZoom
  }

  private var isInspectMode: Bool {
    !compact && zoom >= MemoryAtlasZoomPolicy.inspectModeZoom
  }

  private var atlasLevelLabel: String {
    if isFullyLabelledMode { return "All labelled" }
    if isInspectMode { return "Inspect" }
    if isFocusMode { return "Focus" }
    if zoom < MemoryAtlasZoomPolicy.neighborhoodZoom { return "Overview" }
    if zoom < 1.9 { return "Neighborhood" }
    return "Detail"
  }

  private func point(for normalized: CGPoint, in size: CGSize) -> CGPoint {
    MemoryAtlasRenderPlanner.renderedPoint(
      for: normalized, viewportSize: size, zoom: zoom, pan: pan)
  }

  private func canvasPaintBounds(for size: CGSize) -> CGRect {
    CGRect(x: -28, y: -28, width: size.width + 56, height: size.height + 56)
  }

  private func nodeDiameter(_ placement: MemoryAtlasNodePlacement, selected: Bool) -> CGFloat {
    if isInspectMode {
      if selected { return 64 }
      if placement.id == snapshot.anchorNodeID { return 50 }
      if placement.isCatalog { return 34 }
      if placement.clusterRank == 0 { return 42 }
      return 34
    }
    if selected { return compact ? 28 : (isFocusMode ? 50 : 34) }
    if placement.id == snapshot.anchorNodeID { return compact ? 24 : (isFocusMode ? 38 : 29) }
    if placement.isCatalog { return compact ? 10 : (isFocusMode ? 22 : 13) }
    if placement.clusterRank == 0 { return compact ? 19 : (isFocusMode ? 32 : 23) }
    return compact ? 10 : (isFocusMode ? 22 : 13)
  }

  private func nodeMatchesSearch(_ node: KnowledgeGraphNode) -> Bool {
    guard !searchText.isEmpty else { return true }
    return node.label.localizedCaseInsensitiveContains(searchText)
      || node.aliases.contains { $0.localizedCaseInsensitiveContains(searchText) }
  }

  /// The replay filters membership by its density-aware axis. Hit testing and
  /// keyboard search use the same predicate so a future entity cannot be
  /// selected while it is still absent from the canvas.
  private func nodeIsVisibleAtCurrentTime(_ placement: MemoryAtlasNodePlacement) -> Bool {
    guard let timeline, timeCursor < 0.9995 else { return true }
    return placement.id == snapshot.anchorNodeID || timeline.isVisible(nodeID: placement.id, at: timeCursor)
  }

  private func clearSelectionIfHiddenAtCurrentTime() {
    guard let selectedNodeID, let placement = snapshot.nodeByID[selectedNodeID], !nodeIsVisibleAtCurrentTime(placement)
    else {
      return
    }
    clearSelection()
  }

  private func updateSearchMatches(_ query: String) {
    guard !query.isEmpty else {
      matchingNodeIDs = nil
      matchingEdges = nil
      return
    }
    let matches = Set(
      snapshot.nodes.lazy.filter { placement in
        placement.node.label.localizedCaseInsensitiveContains(query)
          || placement.node.aliases.contains { $0.localizedCaseInsensitiveContains(query) }
      }.map(\.id))
    matchingNodeIDs = matches
    matchingEdges = snapshot.rankedEdges.filter {
      matches.contains($0.edge.sourceId) || matches.contains($0.edge.targetId)
    }
    SearchAnalytics.scheduleQueryEntered(surface: .brainMap, query: query) { matches.count }
  }

  private func selectFirstSearchResult() {
    guard let matchingNodeIDs, !matchingNodeIDs.isEmpty else { return }
    guard
      let nodeID = snapshot.nodes.first(where: {
        matchingNodeIDs.contains($0.id) && nodeIsVisibleAtCurrentTime($0)
      })?.id
    else { return }
    selectionTrail.removeAll()
    adoptSelection(nodeID)
  }

  /// Routes a click on the canvas to whatever it landed on.
  ///
  /// Entities are tested first and win outright: every dot sits on at least one
  /// line, so letting a line take the hit near a dot would make dots feel
  /// unclickable at the exact places they matter most.
  private func selectAtlasElement(at location: CGPoint, in size: CGSize, plan: MemoryAtlasRenderPlan) {
    if let node = nearestNode(to: location, in: size, visibleNodes: plan.visibleNodes) {
      // Reaching for something on the canvas starts a fresh trail; only
      // following a listed connection extends one.
      selectionTrail.removeAll()
      adoptSelection(node.id)
      return
    }

    let segments = plan.visibleEdges.map {
      MemoryAtlasHitTesting.Segment(
        id: $0.id,
        start: point(for: $0.source, in: size),
        end: point(for: $0.target, in: size)
      )
    }
    guard
      let hitID = MemoryAtlasHitTesting.nearestSegment(
        to: location,
        among: segments,
        within: MemoryAtlasHitTesting.connectionTolerance
      ),
      let hit = plan.visibleEdges.first(where: { $0.id == hitID }),
      // The inspector anchors to an endpoint for map emphasis, so a connection
      // whose endpoint is not in the snapshot cannot be presented.
      snapshot.nodeByID[hit.edge.sourceId] != nil
    else { return }
    selectionTrail.removeAll()
    adoptSelection(hit.edge.sourceId, edgeID: hit.id)
  }

  private func nearestNode(to location: CGPoint, in size: CGSize, visibleNodes: [MemoryAtlasNodePlacement] = [])
    -> MemoryAtlasNodePlacement?
  {
    let hitRadius = max(12, 18 / zoom)
    var nearest: (placement: MemoryAtlasNodePlacement, distance: CGFloat)?
    // Hit-test only nodes in the current render plan. On graphs larger than
    // the current detail-level node budget, the canvas paints only visible
    // nodes, but searching every node in the snapshot would let a tap on an
    // apparently blank area select an omitted node and open its inspector.
    let visibleIDs = visibleNodes.isEmpty ? nil : Set(visibleNodes.map { $0.id })
    for placement in snapshot.nodes where nodeIsVisibleAtCurrentTime(placement) {
      if let visibleIDs, !visibleIDs.contains(placement.id) { continue }
      let rendered = point(for: placement.normalizedPosition, in: size)
      let distance = hypot(rendered.x - location.x, rendered.y - location.y)
      if distance <= hitRadius && (nearest.map { distance < $0.distance } ?? true) {
        nearest = (placement, distance)
      }
    }
    return nearest?.placement
  }

  private func updateZoom(_ value: CGFloat) {
    let nextZoom = min(max(value, MemoryAtlasZoomPolicy.minimumZoom), maximumZoom)
    // Buttons, automation, and selection focus zoom around the atlas center.
    // Scaling pan by the same ratio keeps a focused entity in place instead of
    // throwing it off-screen as deep zoom increases.
    pan = MemoryAtlasZoomPolicy.panPreservingCenterZoom(
      pan,
      from: zoom,
      to: nextZoom
    )
    settledPan = pan
    zoom = nextZoom
    settledZoom = nextZoom
  }

  private func zoomIn() {
    let increment = max(0.2, zoom * 0.25)
    updateZoom(min(zoom + increment, maximumZoom))
  }

  private func zoomOut() {
    guard zoom > MemoryAtlasZoomPolicy.minimumZoom else { return }
    let decrementedZoom = zoom > 2 ? zoom / 1.25 : zoom - 0.2
    updateZoom(max(decrementedZoom, MemoryAtlasZoomPolicy.minimumZoom))
  }

  private func focus(on placement: MemoryAtlasNodePlacement) {
    guard viewportSize.width > 0, viewportSize.height > 0 else { return }
    var positions = [placement.normalizedPosition]
    if let neighborIDs = snapshot.neighborIDsByNodeID[placement.id] {
      for neighborID in neighborIDs {
        if let neighbor = snapshot.nodeByID[neighborID] {
          positions.append(neighbor.normalizedPosition)
        }
      }
    }
    let camera = MemoryAtlasZoomPolicy.focusedNeighborhood(
      positions: positions,
      viewport: viewportSize,
      currentZoom: zoom,
      zoomRange: MemoryAtlasZoomPolicy.minimumZoom...maximumZoom
    )
    withAnimation(.easeOut(duration: 0.22)) {
      zoom = camera.zoom
      settledZoom = camera.zoom
      pan = camera.pan
      settledPan = camera.pan
    }
  }

  private func resetViewport(preservingNeighbourhood: Bool = false) {
    if preservingNeighbourhood, enteredRegionID != nil {
      departureZoom = MemoryAtlasNeighbourhoodLabels.overviewDepartureZoom(
        neighbourhoodZoom: MemoryAtlasZoomPolicy.neighborhoodZoom,
        minimumZoom: MemoryAtlasZoomPolicy.minimumZoom)
    }
    withAnimation(.easeOut(duration: 0.2)) {
      zoom = 1
      settledZoom = 1
      pan = .zero
      settledPan = .zero
    }
  }

  /// Undo the innermost thing the user has done, and say whether there was
  /// one. A press the map has no use for is handed back so the page around it
  /// can take the user out of the map.
  private func dismissTopmostState() -> Bool {
    switch MemoryAtlasDismissal.next(
      isSearching: searchIsFocused || !searchText.isEmpty,
      hasSelection: selectedNodeID != nil || selectedEdgeID != nil,
      hasTrail: !selectionTrail.isEmpty,
      isInsideNeighbourhood: enteredRegionID != nil)
    {
    case .search:
      searchIsFocused = false
      searchBinding.wrappedValue = ""
      matchingNodeIDs = nil
      matchingEdges = nil
    case .selectionStep:
      goBack()
    case .selection:
      clearSelection(resetCamera: true)
    case .neighbourhood:
      leaveNeighbourhood()
    case .passThrough:
      // The last layer is the map itself. Handing the key back to the window
      // instead was the tidy-looking version and it did nothing: the atlas is
      // a canvas, so there is no focused control for a cancel to travel up
      // from, and Escape on a page with nothing selected was simply swallowed.
      guard let onLeave else { return false }
      onLeave()
    }
    return true
  }
}

/// SwiftUI has no view-local scroll-wheel gesture on the macOS 14 deployment
/// floor. This passive bridge observes the Atlas viewport without entering the
/// hit-test chain, so normal dragging, tapping, and control interaction remain
/// owned by SwiftUI.
private struct MemoryAtlasInputMonitor: NSViewRepresentable {
  let onScroll: (CGFloat, CGPoint) -> Void
  let onFocusSearch: () -> Void

  func makeCoordinator() -> Coordinator {
    Coordinator(onScroll: onScroll, onFocusSearch: onFocusSearch)
  }

  func makeNSView(context: Context) -> PassiveEventView {
    let view = PassiveEventView()
    let coordinator = context.coordinator
    view.geometryDidChange = { [weak coordinator] windowNumber, frameInWindow in
      coordinator?.windowNumber = windowNumber
      coordinator?.frameInWindow = frameInWindow
    }
    context.coordinator.installMonitor()
    return view
  }

  func updateNSView(_ nsView: PassiveEventView, context: Context) {
    context.coordinator.onScroll = onScroll
    context.coordinator.onFocusSearch = onFocusSearch
  }

  static func dismantleNSView(_ nsView: PassiveEventView, coordinator: Coordinator) {
    nsView.geometryDidChange = nil
    coordinator.removeMonitor()
  }

  final class PassiveEventView: NSView {
    var geometryDidChange: ((Int?, CGRect) -> Void)?

    override var isFlipped: Bool { true }
    override func hitTest(_ point: NSPoint) -> NSView? { nil }

    override func viewDidMoveToWindow() {
      super.viewDidMoveToWindow()
      publishGeometry()
    }

    override func layout() {
      super.layout()
      publishGeometry()
    }

    private func publishGeometry() {
      guard let window else {
        geometryDidChange?(nil, .zero)
        return
      }
      geometryDidChange?(window.windowNumber, convert(bounds, to: nil))
    }
  }

  final class Coordinator {
    var onScroll: (CGFloat, CGPoint) -> Void
    var onFocusSearch: () -> Void
    fileprivate var windowNumber: Int?
    fileprivate var frameInWindow: CGRect = .zero
    private var eventMonitor: Any?

    init(
      onScroll: @escaping (CGFloat, CGPoint) -> Void,
      onFocusSearch: @escaping () -> Void
    ) {
      self.onScroll = onScroll
      self.onFocusSearch = onFocusSearch
    }

    func installMonitor() {
      eventMonitor = NSEvent.addLocalMonitorForEvents(matching: [.scrollWheel, .keyDown]) {
        [weak self] event in
        guard let self, event.windowNumber == self.windowNumber else {
          return event
        }

        if event.type == .keyDown,
          event.modifierFlags.contains(.command),
          event.charactersIgnoringModifiers?.lowercased() == "f"
        {
          self.onFocusSearch()
          return nil
        }

        guard event.type == .scrollWheel else { return event }
        let frameInWindow = self.frameInWindow
        guard frameInWindow.contains(event.locationInWindow) else { return event }
        guard abs(event.scrollingDeltaY) > abs(event.scrollingDeltaX) else { return event }

        let sensitivity: CGFloat = event.hasPreciseScrollingDeltas ? 0.012 : 0.12
        let scaledDelta = min(max(event.scrollingDeltaY * sensitivity, -0.18), 0.18)
        let location = CGPoint(
          x: event.locationInWindow.x - frameInWindow.minX,
          y: frameInWindow.maxY - event.locationInWindow.y
        )
        self.onScroll(scaledDelta, location)
        return nil
      }
    }

    func removeMonitor() {
      guard let eventMonitor else { return }
      NSEvent.removeMonitor(eventMonitor)
      self.eventMonitor = nil
    }

    deinit {
      removeMonitor()
    }
  }
}

// MARK: - Export / QA preview

/// Deterministic, data-backed atlas for offscreen `ViewExporter` renders. The
/// live atlas needs a signed-in account and a server graph, so QA has no way to
/// visually regression-test the timeline without this fixed sample. Same file as
/// the private surface so it can construct it directly.
@MainActor
enum MemoryAtlasExportPreview {
  static func surface(timeCursor: Double = 0.55) -> AnyView {
    AnyView(
      CanonicalMemoryAtlasSurface(
        graph: sampleGraph(),
        compact: false,
        evidenceProvider: { _ in [] },
        previewTimeCursor: timeCursor
      )
    )
  }

  private static func sampleGraph() -> KnowledgeGraphResponse {
    let now = Date(timeIntervalSince1970: 1_752_000_000)
    let span: TimeInterval = 120 * 24 * 60 * 60
    var seed: UInt64 = 0x9e37_79b9_7f4a_7c15
    func rand() -> Double {
      seed ^= seed << 13
      seed ^= seed >> 7
      seed ^= seed << 17
      return Double(seed % 10_000) / 10_000
    }

    let clusters: [(KnowledgeGraphNodeType, [String], Int)] = [
      (.person, ["Sarah", "Alex", "Priya", "Marcus", "Elena", "Mom"], 34),
      (.organization, ["Google Cloud", "Omi", "Stripe", "Anthropic", "Notion"], 26),
      (.place, ["New York City", "San Francisco", "Tokyo", "Blue Bottle"], 22),
      (.thing, ["Telegram", "MacBook", "iPhone", "Tesla", "AirPods"], 40),
      (.concept, ["burnout", "sleep", "running", "design", "focus", "pricing"], 48),
    ]

    var nodes: [KnowledgeGraphNode] = [
      KnowledgeGraphNode(
        id: "david", label: "David", nodeType: .person, memoryIds: ["m0"],
        createdAt: now.addingTimeInterval(-span)
      ),
      // A generic self node so the render exercises the center-collapse too.
      KnowledgeGraphNode(
        id: "user", label: "User", nodeType: .person,
        createdAt: now.addingTimeInterval(-span * 0.9)
      ),
    ]
    var edges: [KnowledgeGraphEdge] = []

    for (type, names, count) in clusters {
      for index in 0..<count {
        let id = "\(type.rawValue)-\(index)"
        let name = index < names.count ? names[index] : "\(names[index % names.count]) \(index)"
        let created = now.addingTimeInterval(-span * (1 - rand()))
        nodes.append(
          KnowledgeGraphNode(
            id: id, label: name, nodeType: type, memoryIds: ["mem-\(id)"], createdAt: created
          )
        )
        if index < 3 {
          edges.append(
            KnowledgeGraphEdge(
              id: "edge-\(id)",
              sourceId: index == 0 ? "user" : "david",
              targetId: id,
              label: "knows",
              memoryIds: ["mem-\(id)"],
              createdAt: created
            )
          )
        }
      }
    }

    return KnowledgeGraphResponse(nodes: nodes, edges: edges)
  }

  /// A one-type atlas — the shape a narrow or young account actually has, and
  /// the case that regressed into a small knot in the upper middle of an
  /// otherwise empty canvas. Kept as its own export so that layout stays
  /// reviewable without an account that happens to have only one entity type.
  static func singleTypeSurface(timeCursor: Double = 1) -> AnyView {
    AnyView(
      CanonicalMemoryAtlasSurface(
        graph: singleTypeGraph(),
        compact: false,
        evidenceProvider: { _ in [] },
        onRebuild: {},
        previewTimeCursor: timeCursor
      )
    )
  }

  /// Same sparse atlas with an entity selected, so the inspector's real
  /// layout (connections, evidence, and the map narrowing beside it) is
  /// captured rather than described.
  static func inspectorSurface() -> AnyView {
    AnyView(
      CanonicalMemoryAtlasSurface(
        graph: singleTypeGraph(),
        compact: false,
        onRebuild: {},
        previewTimeCursor: 1,
        previewSelectedNodeID: "concept-2",
        previewEvidence: Self.sampleEvidence.enumerated().map { index, content in
          MemoryAtlasEvidence(
            id: "evidence-\(index)",
            content: content,
            createdAt: Date(timeIntervalSince1970: 1_752_000_000 - Double(index) * 86_400)
          )
        }
      )
    )
  }

  /// Same atlas with a connection selected rather than an entity. Connections
  /// are clickable, so the relationship inspector is a real destination and
  /// gets a real render.
  static func connectionInspectorSurface() -> AnyView {
    AnyView(
      CanonicalMemoryAtlasSurface(
        graph: singleTypeGraph(),
        compact: false,
        onRebuild: {},
        previewTimeCursor: 1,
        previewSelectedNodeID: "david",
        previewSelectedEdgeID: "edge-concept-2",
        previewEvidence: Self.sampleEvidence.prefix(2).enumerated().map { index, content in
          MemoryAtlasEvidence(
            id: "evidence-\(index)",
            content: content,
            createdAt: Date(timeIntervalSince1970: 1_752_000_000 - Double(index) * 86_400)
          )
        }
      )
    )
  }

  private static let sampleEvidence = [
    "David runs hermes-m4 as the default agent for Multica work and prefers it over other Codex agents unless told otherwise.",
    "Debug symbol uploads to Sentry need SENTRY_AUTH_TOKEN present in the release lane, or the upload silently no-ops.",
    "Long-running agent tasks should run under tmux or screen so closing the terminal session does not kill them.",
  ]

  private static func singleTypeGraph() -> KnowledgeGraphResponse {
    let now = Date(timeIntervalSince1970: 1_752_000_000)
    let span: TimeInterval = 120 * 24 * 60 * 60
    let labels = [
      "portable mechanics", "SENTRY_AUTH_TOKEN", "hermes-m4", "debug symbol upload",
      "long-running tasks", "incident or trace", "production deploy", "403 error",
      "GitHub Discussion", "Discord Issues", "canonical pull request", "Skill Hub",
      "autonomy", "private fork bin", "break-glass hatch", "tmux", "screen",
      "deliverable", "GitHub issue", "release pointer", "worktree", "merge queue",
      "failure class", "ratchet baseline", "changelog fragment",
    ]

    var nodes: [KnowledgeGraphNode] = [
      KnowledgeGraphNode(
        id: "david", label: "David", nodeType: .person, memoryIds: ["m0"],
        createdAt: now.addingTimeInterval(-span)
      )
    ]
    var edges: [KnowledgeGraphEdge] = []

    for (index, label) in labels.enumerated() {
      let id = "concept-\(index)"
      let created = now.addingTimeInterval(-span * (1 - Double(index) / Double(labels.count)))
      nodes.append(
        KnowledgeGraphNode(
          id: id, label: label, nodeType: .concept, memoryIds: ["mem-\(id)"], createdAt: created
        )
      )
      edges.append(
        KnowledgeGraphEdge(
          id: "edge-\(id)", sourceId: "david", targetId: id, label: "relates_to",
          memoryIds: ["mem-\(id)"], createdAt: created
        )
      )
    }

    return KnowledgeGraphResponse(nodes: nodes, edges: edges)
  }
}
